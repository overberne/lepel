# pyright: reportPrivateUsage=false
import tempfile
from pathlib import Path
from typing import Any, Literal, Mapping, Iterable, cast

from lepel.core.checkpointing.checkpoint_file_store import CheckpointFileStore

_CHECKPOINT_GLOB = '[0-9][0-9][0-9][0-9]*_*.*.pkl'
_CHECKPOINT_NAME_GLOB_TEMPLATE = '{name}.*.pkl'


class CheckpointManager[TSnapshot: Mapping[str, Any]]:
    """
    Manage persistence and restoration of application state via checkpoints.

    The checkpoint manager produces either full or incremental (delta)
    checkpoints and delegates serialization to a :class:`CheckpointFileStore`.
    Checkpoints are written atomically and ordered by a monotonically increasing
    index embedded in the filename.

    Parameters
    ----------
    dir : str or pathlib.Path
        Directory in which checkpoint files are stored.
    file_store : CheckpointFileStore
        Backend used to serialize and deserialize checkpoint data.
    """

    def __init__(
        self,
        checkpoint_dir: str | Path,
        file_store: CheckpointFileStore,
    ) -> None:
        self._checkpoint_dir = Path(checkpoint_dir)
        self._file_store = file_store

    def save_incremental(self, name: str, delta: TSnapshot) -> Path:
        """
        Save an incremental (delta) checkpoint.

        The delta is computed relative to the most recent checkpoint, if one
        exists.

        Parameters
        ----------
        name : str
            Logical name for the checkpoint (used in the filename).
        delta : TSnapshot
            Incremental snapshot capturing changes since the last checkpoint.

        Returns
        -------
        pathlib.Path
            Path to the newly created checkpoint file.
        """
        latest_checkpoint_path = self._latest_checkpoint_path()
        path = self._next_checkpoint_path(name, 'delta', latest_checkpoint_path)
        CheckpointManager._atomic_dump(self._file_store, delta, path)
        return path

    def save_full(self, name: str, state: TSnapshot) -> Path:
        """
        Save a full checkpoint of the current state.

        A full checkpoint captures the complete state of all tracked objects
        regardless of prior checkpoints.

        Parameters
        ----------
        name : str
            Logical name for the checkpoint (used in the filename).
        state : TSnapshot
            Full snapshot capturing the complete state.

        Returns
        -------
        pathlib.Path
            Path to the newly created checkpoint file.
        """
        path = self._next_checkpoint_path(name, 'full', self._latest_checkpoint_path())
        CheckpointManager._atomic_dump(self._file_store, state, path)
        return path

    def load_latest(self) -> tuple[str, TSnapshot] | tuple[None, None]:
        """
        Load the most recent checkpoint.

        All checkpoints are applied in reverse chronological order to reconstruct
        the latest state. This means the latest full checkpoint and any subsequent
        delta checkpoints are loaded.

        Returns
        -------
        tuple[str, TSnapshot] or tuple[None, None]
            A tuple containing the stem (filename without extension) of the
            loaded checkpoint and the corresponding snapshot, or ``None`` if
            no checkpoints exist.
        """
        checkpoint_paths = self._all_checkpoint_paths_descending()
        if not checkpoint_paths:
            return None, None

        nearest_full_index = self._nearest_full_checkpoint_index(checkpoint_paths[0])
        if nearest_full_index is None:
            return None, None

        snapshot_history = (
            self._file_store.load(path)
            for path in checkpoint_paths
            if int(path.stem.split('_', 1)[0]) >= nearest_full_index
        )

        current_snapshot = self._replay_snapshots(snapshot_history)
        return checkpoint_paths[0].stem, current_snapshot

    def load(self, name: str) -> tuple[str, TSnapshot]:
        """
        Load a specific checkpoint by name.

        If the named checkpoint is a full checkpoint, it is loaded directly.
        If it is a delta checkpoint, all prior checkpoints from the latest full
        checkpoint up to and including the specified delta are replayed.

        Parameters
        ----------
        name : str
            Checkpoint name or filename stem.

        Returns
        -------
        tuple[str, TSnapshot]
            A tuple containing the stem (filename without extension) of the
            loaded checkpoint and the corresponding snapshot.

        Raises
        ------
        FileNotFoundError
            If no matching checkpoint file exists or if no full checkpoint exists.
        """
        checkpoint_path = self._get_checkpoint_by_name(name)
        if not checkpoint_path:
            raise FileNotFoundError(f'Checkpoint file not found: {name}')

        if checkpoint_path.suffix == '.full.pkl':
            snapshot = self._file_store.load(checkpoint_path)
            return checkpoint_path.stem, snapshot

        nearliest_full_index = self._nearest_full_checkpoint_index(checkpoint_path)
        if nearliest_full_index is None:
            raise FileNotFoundError(f'No full checkpoint found prior to delta: {name}')

        # Load all checkpoints from the nearest full checkpoint up to and
        # including the latest delta.
        snapshot_index = int(checkpoint_path.stem.split('_', 1)[0])
        snapshot_history = (
            self._file_store.load(p)
            for p in self._all_checkpoint_paths_descending()
            if nearliest_full_index <= int(p.stem.split('_', 1)[0]) <= snapshot_index
        )
        current_snapshot = self._replay_snapshots(snapshot_history)
        return checkpoint_path.stem, current_snapshot

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

    def _nearest_full_checkpoint_index(self, checkpoint_path: Path) -> int | None:
        """
        Find the index of the most recent full checkpoint prior or equal to
        the given checkpoint.

        Parameters
        ----------
        checkpoint_path : pathlib.Path
            Reference checkpoint path.

        Returns
        -------
        int or None
            Index of the previous full checkpoint, or ``None`` if none exists.
        """
        target_index = int(checkpoint_path.stem.split('_', 1)[0])

        for path in self._all_checkpoint_paths_descending():
            index = int(path.stem.split('_', 1)[0])
            if index > target_index:
                continue
            if path.suffix == '.full.pkl':
                return index

        return None

    def _previous_full_checkpoint_path(self, checkpoint_path: Path) -> Path | None:
        """
        Find the most recent full checkpoint prior to the given checkpoint.

        Parameters
        ----------
        checkpoint_path : pathlib.Path
            Reference checkpoint path.

        Returns
        -------
        pathlib.Path or None
            Path to the previous full checkpoint, or ``None`` if none exists.
        """
        target_index = int(checkpoint_path.stem.split('_', 1)[0])

        for path in self._all_checkpoint_paths_descending():
            index = int(path.stem.split('_', 1)[0])
            if index >= target_index:
                continue
            if path.suffix == '.full.pkl':
                return path

        return None

    def _replay_snapshots(self, snapshots: Iterable[TSnapshot]) -> TSnapshot:
        """
        Replay a sequence of state snapshots to reconstruct the latest state.

        Snapshots must be provided in reverse chronological order (latest first).

        Parameters
        ----------
        snapshots : iterable of TSnapshot
            Snapshots to replay in reverse chronological order (latest first).

        Returns
        -------
        TSnapshot
            The reconstructed latest state snapshot.
        """
        snapshots_iter = iter(snapshots)
        cumulative_snapshot = dict(next(snapshots_iter))

        # Replay snapshots, latest first.
        for snapshot in snapshots:
            for key, value in snapshot.items():
                if isinstance(value, dict):
                    if key not in cumulative_snapshot:
                        cumulative_snapshot[key] = {}
                    cumulative_snapshot[key].update(value)
                elif isinstance(value, list):
                    if key not in cumulative_snapshot:
                        cumulative_snapshot[key] = []
                    cumulative_snapshot[key].extend(value)
                else:
                    cumulative_snapshot[key] = value

        return cast(TSnapshot, cumulative_snapshot)

    @staticmethod
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
