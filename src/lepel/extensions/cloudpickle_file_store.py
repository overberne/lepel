from pathlib import Path
from typing import Any
import cloudpickle as pickle  # pyright: ignore[reportMissingTypeStubs]

from lepel.core.checkpointing import CheckpointFileStore


class CloudpickleFileStore(CheckpointFileStore):
    """
    A cloudpickle-based checkpoint file store.
    """

    def save(self, obj: Any, path: Path) -> None:
        with open(path, 'wb') as file:
            pickle.dump(obj, file)  # pyright: ignore[reportUnknownMemberType]

    def load(self, path: Path) -> object:
        with open(path, 'rb') as file:
            return pickle.load(file)  # pyright: ignore[reportUnknownMemberType]
