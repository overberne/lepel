from typing import Any, Hashable, Literal, Mapping, TypedDict

ObjectKey = tuple[str, int]
Fingerprints = dict[ObjectKey, Hashable]
StateDicts = dict[ObjectKey, Mapping[str, Any]]


class _StateSnapshotBase(TypedDict):
    fingerprints: Fingerprints
    state_dicts: StateDicts


class FullStateSnapshot(_StateSnapshotBase):
    kind: Literal['full']


class DeltaStateSnapshot(_StateSnapshotBase):
    kind: Literal['delta']


StateSnapshot = FullStateSnapshot | DeltaStateSnapshot
