from typing import Hashable, Protocol, runtime_checkable


@runtime_checkable
class Fingerprintable(Protocol):
    """
    Protocol for objects that can produce a stable fingerprint of their state.

    A ``Fingerprintable`` object provides a lightweight, hashable identifier
    that represents the *semantic state* of the object at a specific point
    in time. The fingerprint is used for change detection and incremental
    checkpointing.

    The fingerprint must satisfy the following invariants:

    - Equal fingerprints imply equivalent state for checkpointing purposes
    - Unequal fingerprints imply that persisted state may be stale
    - Fingerprint computation should be inexpensive (O(1) or proportional
      to the number of state components, not their size)

    The fingerprint does not need to be globally unique and must not be used
    for integrity verification or security-sensitive purposes.

    Notes
    -----
    Implementations are responsible for deciding which parts of the internal
    state are relevant for change detection. Large data structures (e.g.,
    tensors) should typically be represented via version counters or metadata
    rather than by hashing their full contents.

    The checkpoint manager must treat the fingerprint as an opaque value and
    only compare it for equality with previously observed fingerprints.

    Methods
    -------
    state_fingerprint() -> Hashable
        Return a hashable value representing the current semantic state.
    """

    def state_fingerprint(self) -> Hashable: ...
