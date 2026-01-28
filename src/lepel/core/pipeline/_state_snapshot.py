from typing import Any, TypedDict

from lepel.core.state import StateDicts, Fingerprints


class StateSnapshot(TypedDict):
    """
    Snapshot of the state of tracked objects at a specific point in time.
    """

    state_dicts: StateDicts
    fingerprints: Fingerprints
    step_results: list[Any]
