# pyright: reportPrivateUsage=false
import datetime
import shutil
import sys
from os import PathLike
from pathlib import Path
from typing import Any

from coolname import generate_slug  # pyright: ignore[reportMissingTypeStubs]

from lepel.pipeline._config import (
    CONFIG_EXTENSIONS,
    find_config_file,
    find_config_override_file,
    load_config,
    save_config,
)


def get_unique_run_subdir(output_dir: Path) -> Path:
    if output_dir == Path():
        return output_dir

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = generate_slug(2)  # e.g. "mottled-crab"
    return output_dir / f'{timestamp}-{slug}'


def copy_main_script_to_output(output_dir: Path) -> None:
    src_path = Path(sys.argv[0])
    dst_path = output_dir / src_path.name

    # No need to copy
    if src_path == dst_path:
        return
    # Do not copy when running tests
    if src_path.name == 'pytest':
        return

    shutil.copy2(src_path, dst_path)


def copy_config_file_to_output(output_dir: Path, config_file: Path) -> None:
    """Copies the configuration file to :param:`output_dir` with file name
    `config.[yaml|yml|json|toml]`"""
    if not config_file.suffix in CONFIG_EXTENSIONS:
        raise ValueError(
            f'Unsupported config file format "{config_file}", '
            f'supported extensions: {', '.join(CONFIG_EXTENSIONS)}'
        )

    destination = output_dir / f'config{config_file.suffix}'
    if config_file != destination:
        shutil.copy(config_file, destination)


def load_and_save_configs_to_output(
    output_dir: Path,
    config_file: str | PathLike[str] | Path | None,
    config_override: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    if config_file is not None:
        config_file = Path(config_file)
        copy_config_file_to_output(output_dir, config_file)
        config = load_config(config_file)
    else:  # Auto loading for continuity with existing/interrupted runs.
        # Look for a config file in the directory of the pipeline file.
        config_file = find_config_file(Path(sys.argv[0]).parent)
        config: dict[str, Any] = load_config(config_file) if config_file else {}
        config_override_file = find_config_override_file(Path(sys.argv[0]).parent)
        if config_file:
            copy_config_file_to_output(output_dir, config_file)
        if config_override_file:
            loaded_config_override = load_config(config_override_file)
            loaded_config_override.update(config_override)
            config_override = loaded_config_override
    if config_override:
        config.update(config_override)
        save_config_override_to_output(output_dir, config_override, config_file)

    return config_file.stem if config_file else None, config


def save_config_override_to_output(
    output_dir: Path, config_override: dict[str, Any], config_file: Path | None
) -> None:
    """Copies the configuration file to :param:`output_dir` with file name
    `config.[yaml|yml|json|toml]`"""
    if not config_file:
        destination = output_dir / 'config_override.yaml'
        save_config(config_override, destination)
        return

    if not config_file.suffix in CONFIG_EXTENSIONS:
        raise ValueError(
            f'Unsupported config file format "{config_file}", '
            f'supported extensions: {', '.join(CONFIG_EXTENSIONS)}'
        )

    destination = output_dir / f'config_override{config_file.suffix}'
    save_config(config_override, destination)
