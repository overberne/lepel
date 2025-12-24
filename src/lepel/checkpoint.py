from pathlib import Path
from typing import Any, TypedDict

import cloudpickle as pickle  # pyright: ignore[reportMissingTypeStubs]


class Checkpoint(TypedDict):
    name: str
    state_dict: dict[str, Any]


def load_checkpoint(checkpoint_file: Path) -> Checkpoint:
    if not checkpoint_file.exists():
        raise FileNotFoundError(f'Checkpoint file not found: {checkpoint_file}')

    with open(checkpoint_file, 'rb') as handle:
        return pickle.load(handle)


def save_checkpoint(checkpoint: Checkpoint, checkpoint_dir: Path) -> None:
    checkpoint_dir.mkdir(exist_ok=True)
    checkpoint_file = checkpoint_dir / checkpoint['name']
    with open(checkpoint_file, 'wb') as handle:
        pickle.dump(checkpoint, handle)  # type: ignore
