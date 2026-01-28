from typing import Any, Mapping

from lepel.core.state import StateManager, StateDicts


class SimpleStateful:
    def __init__(self, value: Any = None):
        self.value = value

    def state_dict(self) -> Mapping[str, Any]:
        return {'value': self.value}

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        self.value = state['value']


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


def _type_name(obj: Any) -> str:
    return f'{obj.__class__.__module__}.{obj.__class__.__qualname__}'


def test_track_deduplicates_objects():
    state = StateManager()
    obj = SimpleStateful(1)
    state.track(obj)
    state.track(obj)

    state_dicts, _ = state.snapshot()
    # only one instance tracked => index 0 only
    assert (_type_name(obj), 0) in state_dicts
    assert (_type_name(obj), 1) not in state_dicts


def test_snapshot_includes_all_state_and_only_fingerprintables_in_fingerprints():
    state = StateManager()
    a = FingerprintableState(1)
    b = SimpleStateful(2)
    state.track(a)
    state.track(b)

    state_dicts, fingerprints = state.snapshot()
    assert (_type_name(a), 0) in state_dicts
    assert (_type_name(b), 0) in state_dicts

    assert (_type_name(a), 0) in fingerprints
    assert (_type_name(b), 0) not in fingerprints


def test_delta_skips_clean_dirtytrackable_and_skips_unchanged_fingerprintables():
    state = StateManager()
    d = DirtyFingerprintableState(1)
    f = FingerprintableState(10)
    state.track(d)
    state.track(f)

    # first delta from empty => includes both
    delta1, fingerprints1 = state.delta({})
    assert (_type_name(d), 0) in delta1
    assert (_type_name(f), 0) in delta1

    # clear dirty flags => dirty object becomes clean
    state.clear_dirty_flags()

    # second delta with same fingerprints => includes nothing
    delta2, fingerprints2 = state.delta(fingerprints1)
    assert delta2 == {}
    assert fingerprints2 == fingerprints1

    # mutate fingerprintable => should appear
    f.value = 11
    delta3, fingerprints3 = state.delta(fingerprints1)
    assert (_type_name(f), 0) in delta3
    assert fingerprints3[(_type_name(f), 0)] == 11


def test_load_applies_state_to_tracked_objects_by_type_and_index():
    state = StateManager()
    a0 = SimpleStateful(0)
    a1 = SimpleStateful(0)
    state.track(a0)
    state.track(a1)

    state_dicts: StateDicts = {
        (_type_name(a0), 0): {'value': 10},
        (_type_name(a0), 1): {'value': 20},
    }
    state.load(state_dicts)

    assert a0.value == 10
    assert a1.value == 20


def test_track_applies_state_preloaded_by_load():
    state = StateManager()
    a0 = SimpleStateful(0)
    a1 = SimpleStateful(0)

    state.track(a0)

    state_dicts: StateDicts = {
        (_type_name(a0), 0): {'value': 10},
        (_type_name(a0), 1): {'value': 20},
    }
    state.load(state_dicts)

    state.track(a1)

    assert a0.value == 10
    assert a1.value == 20
