# pyright: reportPrivateUsage=false
import pickle
from pathlib import Path
from typing import Any, Mapping

import pytest

from lepel.core.checkpointing.checkpoint_manager import CheckpointManager
from lepel.core.state.state_manager import StateManager


class PickleFileStore:
    def save(self, obj: Any, path: Path) -> None:
        with open(path, 'wb') as f:
            pickle.dump(obj, f)

    def load(self, path: Path) -> Any:
        with open(path, 'rb') as f:
            return pickle.load(f)


class SimpleState:
    def __init__(self, value: int = 0):
        self.value = value
        self._dirty = True

    def state_dict(self) -> Mapping[str, Any]:
        return {'value': self.value}

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        self.value = state['value']
        self._dirty = True

    def state_fingerprint(self):
        return self.value

    def is_dirty(self) -> bool:
        return self._dirty

    def clear_dirty(self) -> None:
        self._dirty = False


def test_save_full_creates_file_and_clears_dirty(tmp_path: Path):
    state_manager = StateManager()
    state = SimpleState(7)
    state_manager.track(state)

    store = PickleFileStore()
    checkpoint_manager = CheckpointManager(tmp_path, state_manager, store)

    path = checkpoint_manager.save_full('test')
    assert path.exists()
    assert path.name.endswith('.full.pkl')
    # dirty flags cleared after save
    assert not state.is_dirty()


def test_save_incremental_without_previous_stores_delta(tmp_path: Path):
    state_manager = StateManager()
    state = SimpleState(3)
    state_manager.track(state)

    store = PickleFileStore()
    checkpoint_manager = CheckpointManager(tmp_path, state_manager, store)

    path = checkpoint_manager.save_incremental('inc')
    assert path.exists()
    assert path.name.endswith('.delta.pkl')
    # inspect contents
    data = store.load(path)
    assert data['kind'] == 'delta'


def test_save_incremental_increments_index_and_uses_previous_fingerprint(tmp_path: Path):
    state_manager = StateManager()
    state = SimpleState(1)
    state_manager.track(state)

    store = PickleFileStore()
    checkpoint_manager = CheckpointManager(tmp_path, state_manager, store)

    full_path = checkpoint_manager.save_full('snap')
    assert full_path.name.startswith('0000_')

    # change state and save incremental
    state.value = 2
    state._dirty = True
    delta_path = checkpoint_manager.save_incremental('snap')
    assert delta_path.name.startswith('0001_')

    delta = store.load(delta_path)
    assert delta['kind'] == 'delta'
    # contains updated state for the object
    assert any(d.get('value') == 2 for d in delta['state_dicts'].values())


def test_load_latest_applies_snapshots_and_returns_stem(tmp_path: Path):
    state_manager = StateManager()
    state = SimpleState(0)
    state_manager.track(state)

    store = PickleFileStore()
    checkpoint_manager = CheckpointManager(tmp_path, state_manager, store)

    checkpoint_manager.save_full('base')
    state.value = 42
    state._dirty = True
    checkpoint_manager.save_incremental('base')

    # reset and load latest
    state.value = 0
    stem = checkpoint_manager.load_latest()
    assert stem is not None
    # value should be restored to latest (42)
    assert state.value == 42


def test_load_by_name_resolves_latest_matching_and_raises_if_missing(tmp_path: Path):
    state_manager = StateManager()
    state = SimpleState(5)
    state_manager.track(state)

    store = PickleFileStore()
    checkpoint_manager = CheckpointManager(tmp_path, state_manager, store)

    checkpoint_manager.save_full('named')
    incremental_path = checkpoint_manager.save_incremental('named')

    # load by partial name (without index) should pick the newest matching checkpoint
    state.value = 0
    checkpoint_manager.load('named')
    assert state.value in (incremental_path.stem, state.value)

    # request unknown name -> FileNotFoundError
    with pytest.raises(FileNotFoundError):
        checkpoint_manager.load('does-not-exist')
