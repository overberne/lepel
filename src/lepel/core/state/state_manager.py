from collections import defaultdict
from typing import Any, Hashable, Mapping

from lepel.core.state.dirty_trackable import DirtyTrackable
from lepel.core.state.fingerprintable import Fingerprintable
from lepel.core.state.stateful import Stateful

ObjectKey = tuple[str, int]
Fingerprints = dict[ObjectKey, Hashable]
StateDicts = dict[ObjectKey, Mapping[str, Any]]


class StateManager:
    """
    Coordinate state tracking, snapshotting, and restoration for stateful objects.

    The state manager maintains an registry of tracked objects and provides
    facilities for producing full and incremental state snapshots, as well as
    restoring state from such snapshots.
    """

    _tracked_objects: dict[str, list[Stateful]]
    _preloaded_state: dict[str, dict[int, Mapping[str, Any]]]

    def __init__(self) -> None:
        self._tracked_objects = defaultdict(list)
        self._preloaded_state = {}

    def track(self, obj: Stateful) -> None:
        """
        Register a stateful object for state tracking.

        If the object implements ``Fingerprintable`` or ``DirtyTrackable``,
        those interfaces are used to optimise incremental snapshot creation.

        Parameters
        ----------
        obj : Stateful
            Object whose state should be tracked.
        """
        type_name = _type_name(obj)
        objects = self._tracked_objects[type_name]

        if obj in objects:
            return

        object_index = len(objects)
        objects.append(obj)

        # Load any preloaded state for this object
        if type_name in self._preloaded_state:
            if object_index in self._preloaded_state[type_name]:
                obj.load_state_dict(self._preloaded_state[type_name].pop(object_index))
            if not self._preloaded_state[type_name]:
                del self._preloaded_state[type_name]

    def load(self, state_dicts: StateDicts) -> None:
        """
        Load a full state snapshot into tracked objects.

        Any state entries for untracked objects are stored for potential
        future use.

        Parameters
        ----------
        state_dicts : StateDicts
            Snapshot containing complete state dictionaries.
        """
        for (type_name, index), obj_state in state_dicts.items():
            if type_name in self._tracked_objects and index < len(self._tracked_objects[type_name]):
                obj = self._tracked_objects[type_name][index]
                obj.load_state_dict(obj_state)
            else:
                self._preloaded_state.setdefault(type_name, {})[index] = obj_state

    def delta(self, fingerprints: Fingerprints) -> tuple[StateDicts, Fingerprints]:
        """
        Compute an incremental (delta) snapshot of tracked objects.

        Objects that are not dirty or whose fingerprints have not changed
        are omitted from the resulting snapshot.

        Parameters
        ----------
        fingerprints : Fingerprints
            Previously recorded fingerprints to compare against.

        Returns
        -------
        tuple[StateDicts, Fingerprints]
            Incremental snapshot containing state delta dictionaries
            and fingerprints.
        """
        delta: StateDicts = {}
        current_fingerprints = fingerprints.copy()

        for type_name, objects in self._tracked_objects.items():
            for obj_index, obj in enumerate(objects):
                if isinstance(obj, DirtyTrackable) and not obj.is_dirty():
                    continue

                if isinstance(obj, Fingerprintable):
                    fingerprint = obj.state_fingerprint()
                    key = (type_name, obj_index)
                    if key in fingerprints and fingerprints[key] == fingerprint:
                        continue
                    current_fingerprints[key] = fingerprint

                key = (type_name, obj_index)
                delta[key] = obj.state_dict()

        return delta, current_fingerprints

    def snapshot(self) -> tuple[StateDicts, Fingerprints]:
        """
        Compute a full snapshot of all tracked objects.

        Returns
        -------
        tuple[StateDicts, Fingerprints]
            Snapshot containing complete state dictionaries and fingerprints.
        """
        return (
            {
                (type_name, obj_index): obj.state_dict()
                for type_name, objects in self._tracked_objects.items()
                for obj_index, obj in enumerate(objects)
            },
            {
                (type_name, obj_index): obj.state_fingerprint()
                for type_name, objects in self._tracked_objects.items()
                for obj_index, obj in enumerate(objects)
                if isinstance(obj, Fingerprintable)
            },
        )

    def clear_dirty_flags(self) -> None:
        """
        Clear dirty flags on all tracked dirty-trackable objects.
        """
        for objects in self._tracked_objects.values():
            for obj in objects:
                if isinstance(obj, DirtyTrackable):
                    obj.clear_dirty()


def _type_name(obj: Stateful) -> str:
    return f'{obj.__class__.__module__}.{obj.__class__.__qualname__}'
