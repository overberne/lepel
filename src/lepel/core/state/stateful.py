from typing import Any, Protocol, Mapping, runtime_checkable


@runtime_checkable
class Stateful(Protocol):
    """
    Protocol for objects that expose serializable and restorable internal state.

    A ``Stateful`` object must be able to externalize all state required to
    resume execution from a checkpoint and later restore itself from that state.

    The returned state representation must be:
    - Self-contained (no implicit external dependencies)
    - Compatible with ``load_state_dict`` produced by the same version
    - Treated as an opaque mapping by checkpointing infrastructure

    Implementations should ensure that calling ``load_state_dict`` fully
    replaces the current internal state rather than mutating it incrementally.

    Notes
    -----
    This protocol defines *persistence capability only*. It does not imply
    anything about change detection, versioning, or mutation tracking.

    The checkpoint manager must not introspect or modify the contents of the
    returned state dictionary.

    Methods
    -------
    state_dict() -> Mapping[str, Any]
        Return a complete representation of the current internal state.

    load_state_dict(state: Mapping[str, Any]) -> None
        Restore internal state from a previously produced state dictionary.
    """

    def state_dict(self) -> Mapping[str, Any]: ...
    def load_state_dict(self, state_dict: Mapping[str, Any]) -> None: ...
