# pyright: reportPrivateUsage=false
from typing import Any, Mapping

from lepel.core.state.state_manager import StateManager, StateSnapshot


class SimpleStateful:
    def __init__(self, value: Any = None):
        self.value = value

    def state_dict(self) -> Mapping[str, Any]:
        return {"value": self.value}

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        self.value = state.get("value")


class FingerprintableState(SimpleStateful):
    def state_fingerprint(self):
        return self.value


class DirtyFingerprintableState(FingerprintableState):
    def __init__(self, value: Any = None):
        super().__init__(value)
        self._dirty = True

    def is_dirty(self) -> bool:
        return self._dirty

    def clear_dirty(self) -> None:
        self._dirty = False

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        super().load_state_dict(state)
        self._dirty = True


def _type_name_for(obj: Any) -> str:
    return f"{obj.__class__.__module__}.{obj.__class__.__qualname__}"


def test_snapshot_includes_state_dicts_and_fingerprints_for_fingerprintable():
    state_manager = StateManager()
    fingerprintable = FingerprintableState(1)
    stateful = SimpleStateful(2)
    state_manager.track(fingerprintable)
    state_manager.track(stateful)

    snapshot = state_manager._snapshot()
    assert snapshot["kind"] == "full"

    # both objects appear in state_dicts
    key_a = (_type_name_for(fingerprintable), 0)
    key_b = (_type_name_for(stateful), 0)
    assert key_a in snapshot["state_dicts"]
    assert key_b in snapshot["state_dicts"]

    # only fingerprintable object has fingerprint
    assert key_a in snapshot["fingerprints"]
    assert key_b not in snapshot["fingerprints"]


def test_delta_respects_dirty_and_fingerprint_comparisons():
    state_manager = StateManager()
    # dirty+fingerprintable object
    dirty_fingerprintable = DirtyFingerprintableState(1)
    # fingerprintable but not dirty-trackable
    fingerprintable = FingerprintableState(10)
    state_manager.track(dirty_fingerprintable)
    state_manager.track(fingerprintable)

    # initial fingerprints empty -> both included
    delta = state_manager._delta({})
    keys = set(delta["state_dicts"].keys())
    assert (_type_name_for(dirty_fingerprintable), 0) in keys
    assert (_type_name_for(fingerprintable), 0) in keys

    # now compute fingerprints and call again without changes -> nothing included
    fingerprints = delta["fingerprints"].copy()
    # Clear dirty flags to simulate persisted state
    state_manager._clear_dirty_flags()

    delta2 = state_manager._delta(fingerprints)
    # dirty object was cleared; fingerprintable object unchanged -> no updates
    assert delta2["state_dicts"] == {}

    # mutate a fingerprintable object's value -> included
    fingerprintable.value = 11
    delta3 = state_manager._delta(fingerprints)
    assert (_type_name_for(fingerprintable), 0) in delta3["state_dicts"]


def test_clear_dirty_flags_clears_all_dirty_trackable_objects():
    state_manager = StateManager()
    state_1 = DirtyFingerprintableState(1)
    state_2 = DirtyFingerprintableState(2)
    state_manager.track(state_1)
    state_manager.track(state_2)

    state_manager._clear_dirty_flags()
    assert not state_1.is_dirty()
    assert not state_2.is_dirty()


def test_load_snapshots_applies_latest_delta_only_and_handles_full_snapshot():
    state_manager = StateManager()
    state = SimpleStateful(0)
    state_manager.track(state)

    key = (_type_name_for(state), 0)

    # Two delta snapshots where the first (latest) should win
    latest: StateSnapshot = {
        "kind": "delta",
        "fingerprints": {key: "fp2"},
        "state_dicts": {key: {"value": 2}},
    }

    earlier: StateSnapshot = {
        "kind": "delta",
        "fingerprints": {key: "fp1"},
        "state_dicts": {key: {"value": 1}},
    }

    fingerprints = state_manager._load_snapshots([latest, earlier])
    assert state.value == 2
    assert fingerprints == latest["fingerprints"]

    # Full snapshot should load and then stop (earlier deltas ignored)
    state.value = 0
    full: StateSnapshot = {
        "kind": "full",
        "fingerprints": {key: "fullfp"},
        "state_dicts": {key: {"value": 99}},
    }

    later_delta: StateSnapshot = {
        "kind": "delta",
        "fingerprints": {key: "delfp"},
        "state_dicts": {key: {"value": 5}},
    }

    fingerprints2 = state_manager._load_snapshots([full, later_delta])
    # full snapshot should set value to 99 and fingerprints from the full
    assert state.value == 99
    assert fingerprints2 == full["fingerprints"]


def test_load_snapshots_with_empty_iterable_returns_empty_fingerprints():
    state_manager = StateManager()
    assert state_manager._load_snapshots([]) == {}
