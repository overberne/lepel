from collections import defaultdict
from typing import Iterable

from lepel.core.state.dirty_trackable import DirtyTrackable
from lepel.core.state.fingerprintable import Fingerprintable
from lepel.core.state.state_snapshot import (
    DeltaStateSnapshot,
    FullStateSnapshot,
    StateSnapshot,
    Fingerprints,
    StateDicts,
)
from lepel.core.state.stateful import Stateful


class StateManager:
    """
    Coordinate state tracking, snapshotting, and restoration for stateful objects.

    The state manager maintains an ordered registry of tracked objects and
    provides facilities for producing full and incremental state snapshots,
    as well as restoring state from such snapshots.
    """

    _tracked_objects: dict[str, list[Stateful]]

    def __init__(self) -> None:
        self._tracked_objects = defaultdict(list)

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
        objects = self._tracked_objects[_type_name(obj)]
        if obj not in objects:
            objects.append(obj)

    def _load_snapshots(self, snapshots: Iterable[StateSnapshot]) -> Fingerprints:
        """
        Load a sequence of state snapshots into tracked objects.

        Snapshots must be provided in reverse chronological order (latest first).
        Only the most recent delta for each object is applied.

        Parameters
        ----------
        snapshots : iterable of StateSnapshot
            Snapshots to apply.

        Returns
        -------
        Fingerprints
            Latest fingerprints after applying the snapshots.
        """
        if not snapshots:
            return {}

        latest_deltas: StateDicts = {}
        latest_fingerprints: Fingerprints = {}

        # Replay snapshots, latest first.
        for snapshot in snapshots:
            if not latest_fingerprints:
                latest_fingerprints = snapshot['fingerprints']

            if snapshot['kind'] == 'full':
                self._load_full_snapshot(snapshot)
                break

            for key, state in snapshot['state_dicts'].items():
                if key not in latest_deltas:
                    latest_deltas[key] = state

        # Apply only latest deltas to tracked objects.
        for (type_name, obj_index), obj_state in latest_deltas.items():
            obj = self._tracked_objects[type_name][obj_index]
            obj.load_state_dict(obj_state)

        return latest_fingerprints

    def _load_full_snapshot(self, snapshot: FullStateSnapshot) -> None:
        """
        Load a full state snapshot into tracked objects.

        Parameters
        ----------
        snapshot : FullStateSnapshot
            Snapshot containing complete state dictionaries.
        """
        state_dicts = snapshot.get('state_dicts', {})

        for (type_name, obj_index), obj_state in state_dicts.items():
            obj = self._tracked_objects[type_name][obj_index]
            obj.load_state_dict(obj_state)

    def _delta(self, fingerprints: Fingerprints) -> DeltaStateSnapshot:
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
        DeltaStateSnapshot
            Incremental snapshot containing updated state dictionaries
            and fingerprints.
        """
        updates: StateDicts = {}
        fingerprints = fingerprints.copy()

        for type_name, objects in self._tracked_objects.items():
            for obj_index, obj in enumerate(objects):
                if isinstance(obj, DirtyTrackable) and not obj.is_dirty():
                    continue

                if isinstance(obj, Fingerprintable):
                    fingerprint = obj.state_fingerprint()
                    key = (type_name, obj_index)
                    if key in fingerprints and fingerprints[key] == fingerprint:
                        continue
                    fingerprints[key] = fingerprint

                key = (type_name, obj_index)
                updates[key] = obj.state_dict()

        return {
            'fingerprints': fingerprints,
            'state_dicts': updates,
            'kind': 'delta',
        }

    def _snapshot(self) -> FullStateSnapshot:
        """
        Compute a full snapshot of all tracked objects.

        Returns
        -------
        FullStateSnapshot
            Snapshot containing complete state dictionaries and fingerprints.
        """
        return {
            'fingerprints': {
                (type_name, obj_index): obj.state_fingerprint()
                for type_name, objects in self._tracked_objects.items()
                for obj_index, obj in enumerate(objects)
                if isinstance(obj, Fingerprintable)
            },
            'state_dicts': {
                (type_name, obj_index): obj.state_dict()
                for type_name, objects in self._tracked_objects.items()
                for obj_index, obj in enumerate(objects)
            },
            'kind': 'full',
        }

    def _clear_dirty_flags(self) -> None:
        """
        Clear dirty flags on all tracked dirty-trackable objects.
        """
        for objects in self._tracked_objects.values():
            for obj in objects:
                if isinstance(obj, DirtyTrackable):
                    obj.clear_dirty()


def _type_name(obj: Stateful) -> str:
    return f'{obj.__class__.__module__}.{obj.__class__.__qualname__}'
