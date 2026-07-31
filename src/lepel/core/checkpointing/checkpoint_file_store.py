from pathlib import Path
from typing import Any, Protocol


class CheckpointFileStore(Protocol):
    """
    Protocol for checkpoint file stores.

    A ``CheckpointFileStore`` is responsible for saving and loading checkpoint
    data to and from a persistent storage.

    Methods
    -------
    save(obj: Any, path: Path) -> None
        Save the given object to the specified path.

    load(path: Path) -> Any
        Load an object from the specified path.
    """

    def save(self, obj: Any, path: Path) -> None: ...
    def load(self, path: Path) -> Any: ...
