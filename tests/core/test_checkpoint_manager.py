import pickle
from pathlib import Path
from typing import Any, Mapping

import pytest

from lepel.core.checkpointing.checkpoint_manager import CheckpointManager


class PickleFileStore:
    def save(self, obj: Any, path: Path) -> None:
        with open(path, 'wb') as f:
            pickle.dump(obj, f)

    def load(self, path: Path) -> Any:
        with open(path, 'rb') as f:
            return pickle.load(f)


def test_save_full_creates_monotonic_filenames(tmp_path: Path):
    checkpointing = CheckpointManager[Mapping[str, Any]](tmp_path, PickleFileStore())
    path0 = checkpointing.save_full('ckpt', {'a': 1})
    path1 = checkpointing.save_full('ckpt', {'a': 2})

    assert path0.exists() and path1.exists()
    assert path0.name.startswith('0000_')
    assert path1.name.startswith('0001_')
    assert path0.name.endswith('.full.pkl')
    assert path1.name.endswith('.full.pkl')


def test_save_incremental_creates_delta_file(tmp_path: Path):
    checkpointing = CheckpointManager[Mapping[str, Any]](tmp_path, PickleFileStore())
    checkpoint_path = checkpointing.save_incremental('step', {'x': 1})
    assert checkpoint_path.exists()
    assert checkpoint_path.name.startswith('0000_')
    assert checkpoint_path.name.endswith('.delta.pkl')


def test_load_latest_none_when_no_checkpoints(tmp_path: Path):
    checkpointing = CheckpointManager[Mapping[str, Any]](tmp_path, PickleFileStore())
    name, snap = checkpointing.load_latest()
    assert name is None
    assert snap is None


def test_load_by_name_raises_when_missing(tmp_path: Path):
    checkpointing = CheckpointManager[Mapping[str, Any]](tmp_path, PickleFileStore())
    with pytest.raises(FileNotFoundError):
        checkpointing.load('does-not-exist')


def test_load_latest_replays_full_plus_deltas_to_latest_state(tmp_path: Path):
    '''
    load_latest reconstructs the latest state by taking the latest full
    checkpoint and applying subsequent deltas up to the newest.
    '''
    store = PickleFileStore()
    checkpointing = CheckpointManager[Mapping[str, Any]](tmp_path, store)

    checkpointing.save_full('base', {'a': 1, 'd': {'x': 1}, 'l': [1]})
    checkpointing.save_incremental('base', {'a': 2, 'd': {'y': 2}, 'l': [2]})
    checkpointing.save_incremental('base', {'a': 3})

    stem, snap = checkpointing.load_latest()
    assert stem is not None
    assert snap is not None
    assert snap['a'] == 3
    assert snap['d'] == {'x': 1, 'y': 2}
    assert snap['l'] == [1, 2]


def test_load_specific_full_checkpoint(tmp_path: Path):
    store = PickleFileStore()
    checkpointing = CheckpointManager[Mapping[str, Any]](tmp_path, store)

    full0 = checkpointing.save_full('base', {'a': 1})
    checkpointing.save_incremental('base', {'a': 2})

    # Loading by exact stem
    stem, snap = checkpointing.load(  # pyright: ignore[reportUnusedVariable]
        full0.name.split('.', 1)[0]
    )
    assert snap['a'] == 1


def test_load_specific_delta_checkpoint_replays_from_nearest_full(tmp_path: Path):
    store = PickleFileStore()
    checkpointing = CheckpointManager[Mapping[str, Any]](tmp_path, store)

    checkpointing.save_full('base', {'a': 1})
    d1 = checkpointing.save_incremental('base', {'a': 2})
    checkpointing.save_incremental('base', {'a': 3})

    # should reconstruct up to a=2
    stem, snap = checkpointing.load(d1.name.split('.', 1)[0])
    assert stem == d1.name.split('.', 1)[0]
    assert snap['a'] == 2
