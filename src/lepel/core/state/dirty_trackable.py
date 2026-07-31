from typing import Protocol, runtime_checkable


@runtime_checkable
class DirtyTrackable(Protocol):
    """
    Protocol for objects that explicitly track whether their state has changed.

    A ``DirtyTrackable`` object maintains an internal notion of whether its
    state has been mutated since the last time the dirty flag was cleared.
    This allows fast-path change detection without computing fingerprints
    or inspecting internal state.

    The dirty flag must follow these semantics:

    - ``is_dirty()`` returns ``True`` if and only if the object has undergone
      a state mutation that may require checkpoint persistence
    - ``clear_dirty()`` resets the dirty flag to indicate a clean state
    - Once dirty, the object remains dirty until explicitly cleared

    Implementations are expected to mark themselves dirty at the point of
    mutation (e.g., optimizer steps, state loading), not retroactively.

    Notes
    -----
    This protocol provides a *performance optimization* and may be used in
    conjunction with ``Fingerprintable`` for correctness validation.

    A clean object (``is_dirty() == False``) must not report a different
    fingerprint than it did at the last clearing point.

    Methods
    -------
    is_dirty() -> bool
        Return whether the object's state has changed since it was last cleared.

    clear_dirty() -> None
        Mark the object as clean, indicating that its current state has been
        observed or persisted.
    """

    def is_dirty(self) -> bool: ...

    def clear_dirty(self) -> None: ...
