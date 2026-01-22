# pyright: reportPrivateUsage=false
import tempfile
from pathlib import Path
from typing import Any, Literal

from lepel.core.checkpointing.checkpoint_file_store import CheckpointFileStore
from lepel.core.state import Fingerprints, StateManager

_CHECKPOINT_GLOB = '[0-9][0-9][0-9][0-9]*_*.*.pkl'
_CHECKPOINT_NAME_GLOB_TEMPLATE = '{name}.*.pkl'


class CheckpointManager:
    """
    Manage persistence and restoration of application state via checkpoints.

    This class coordinates with a :class:`StateManager` to produce either full
    or incremental (delta) checkpoints and delegates serialization to a
    :class:`CheckpointFileStore`. Checkpoints are written atomically and ordered
    by a monotonically increasing index embedded in the filename.

    Parameters
    ----------
    dir : str or pathlib.Path
        Directory in which checkpoint files are stored.
    state : StateManager
        State manager responsible for producing and loading state snapshots.
    file_store : CheckpointFileStore
        Backend used to serialize and deserialize checkpoint data.
    """

    def __init__(
        self,
        checkpoint_dir: str | Path,
        state: StateManager,
        file_store: CheckpointFileStore,
    ) -> None:
        self._checkpoint_dir = Path(checkpoint_dir)
        self._state = state
        self._file_store = file_store

    def save_incremental(self, name: str) -> Path:
        """
        Save an incremental (delta) checkpoint.

        The delta is computed relative to the most recent checkpoint, if one
        exists. After saving, all dirty flags in the tracked state are cleared.

        Parameters
        ----------
        name : str
            Logical name for the checkpoint (used in the filename).

        Returns
        -------
        pathlib.Path
            Path to the newly created checkpoint file.
        """
        latest_checkpoint_path = self._latest_checkpoint_path()
        fingerprints: Fingerprints = {}

        if latest_checkpoint_path:
            lastest_checkpoint = self._file_store.load(latest_checkpoint_path)
            fingerprints = lastest_checkpoint['fingerprints']

        snapshot = self._state._delta(fingerprints)
        path = self._next_checkpoint_path(name, 'delta', latest_checkpoint_path)
        _atomic_dump(self._file_store, snapshot, path)
        self._state._clear_dirty_flags()
        return path

    def save_full(self, name: str) -> Path:
        """
        Save a full checkpoint of the current state.

        A full checkpoint captures the complete state of all tracked objects
        regardless of prior checkpoints. After saving, all dirty flags in the
        tracked state are cleared.

        Parameters
        ----------
        name : str
            Logical name for the checkpoint (used in the filename).

        Returns
        -------
        pathlib.Path
            Path to the newly created checkpoint file.
        """
        snapshot = self._state._snapshot()
        path = self._next_checkpoint_path(name, 'full', self._latest_checkpoint_path())
        _atomic_dump(self._file_store, snapshot, path)
        self._state._clear_dirty_flags()
        return path

    def load_latest(self) -> str | None:
        """
        Load the most recent checkpoint into the managed state.

        All checkpoints are applied in reverse chronological order to reconstruct
        the latest state. This means the latest full checkpoint and any subsequent
        delta checkpoints are loaded.

        Returns
        -------
        str or None
            The stem (filename without extension) of the loaded checkpoint,
            or ``None`` if no checkpoints exist.
        """
        checkpoint_paths = self._all_checkpoint_paths_descending()
        if not checkpoint_paths:
            return None

        ordered_snapshots = (self._file_store.load(path) for path in checkpoint_paths)
        self._state._load_snapshots(ordered_snapshots)
        return checkpoint_paths[0].stem

    def load(self, name: str) -> None:
        """
        Load a specific checkpoint by name.

        If the named checkpoint is a full checkpoint, it is loaded directly.
        If it is a delta checkpoint, all prior checkpoints from the latest full
        checkpoint up to and including the specified delta are replayed.

        Parameters
        ----------
        name : str
            Checkpoint name or filename stem.

        Raises
        ------
        FileNotFoundError
            If no matching checkpoint file exists.
        """
        checkpoint_path = self._get_checkpoint_by_name(name)
        if not checkpoint_path:
            raise FileNotFoundError(f'Checkpoint file not found: {name}')

        if checkpoint_path.suffix == '.full.pkl':
            snapshot = self._file_store.load(checkpoint_path)
            self._state._load_snapshots([snapshot])
            return

        # Load all checkpoints up to and including the latest delta.
        latest_index = int(checkpoint_path.stem.split('_', 1)[0])
        checkpoints_subset = (
            self._file_store.load(p)
            for p in self._all_checkpoint_paths_descending()
            if int(p.stem.split('_', 1)[0]) <= latest_index
        )
        self._state._load_snapshots(checkpoints_subset)

    def _all_checkpoint_paths_descending(self) -> list[Path]:
        """
        Return all checkpoint paths sorted by descending index.

        Returns
        -------
        list[pathlib.Path]
            All matching checkpoint files, newest first.
        """
        all_checkpoints = self._checkpoint_dir.glob(_CHECKPOINT_GLOB)
        return sorted(all_checkpoints, key=lambda p: int(p.stem.split('_', 1)[0]), reverse=True)

    def _get_checkpoint_by_name(self, name: str) -> Path | None:
        """
        Resolve a checkpoint file by logical name.

        If the name does not begin with a numeric index, all matching indices
        are considered and the newest match is returned.

        Parameters
        ----------
        name : str
            Checkpoint name or partial filename stem.

        Returns
        -------
        pathlib.Path or None
            Path to the resolved checkpoint file, or ``None`` if no match exists.
        """
        parts = name.split('_', 1)

        # If the name does not start with an index, use a glob pattern to match any index.
        if not parts[0].isdigit():
            name = f'[0-9][0-9][0-9][0-9]*_{name}'

        pattern = _CHECKPOINT_NAME_GLOB_TEMPLATE.format(name=name)
        matching_checkpoints = list(self._checkpoint_dir.glob(pattern))

        if not matching_checkpoints:
            return None

        return max(matching_checkpoints, key=lambda p: int(p.stem.split('_', 1)[0]))

    def _latest_checkpoint_path(self) -> Path | None:
        """
        Return the most recent checkpoint path.

        Returns
        -------
        pathlib.Path or None
            Path to the latest checkpoint, or ``None`` if no checkpoints exist.
        """
        return next(iter(self._all_checkpoint_paths_descending()), None)

    def _next_checkpoint_path(
        self,
        name: str,
        kind: Literal['full', 'delta'],
        latest_checkpoint_path: Path | None,
    ) -> Path:
        """
        Compute the filesystem path for the next checkpoint.

        Parameters
        ----------
        name : str
            Logical checkpoint name.
        kind : {'full', 'delta'}
            Type of checkpoint being created.
        latest_checkpoint_path : pathlib.Path or None
            Path to the most recent checkpoint, if any.

        Returns
        -------
        pathlib.Path
            Path for the new checkpoint file.
        """
        if latest_checkpoint_path:
            latest_index = int(latest_checkpoint_path.stem.split('_', 1)[0])
            next_index = latest_index + 1
        else:
            next_index = 0

        filename = f'{next_index:04d}_{name}.{kind}.pkl'
        return self._checkpoint_dir / filename


def _atomic_dump(file_store: CheckpointFileStore, obj: Any, path: Path) -> None:
    """
    Atomically persist an object to disk.

    The object is first written to a temporary file in the target directory
    and then atomically renamed to the final path.

    Parameters
    ----------
    file_store : CheckpointFileStore
        Storage backend used to serialize the object.
    obj : Any
        Object to persist.
    path : pathlib.Path
        Destination file path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=str(path.parent), delete=False) as tf:
        tmp = Path(tf.name)
    try:
        file_store.save(obj, tmp)
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
