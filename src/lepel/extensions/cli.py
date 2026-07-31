import argparse
from pathlib import Path
from typing import Any


def default_argparser(
    description: str = 'Lepel experiment pipeline',
) -> argparse.ArgumentParser:
    """
    Creates a default argument parser for Lepel pipelines.

    The default parser includes the following arguments:
    - ``-o --output-dir [Path]``: Path to the output directory.
    - ``-c --config [Path]``: Optional path to a configuration file.
    - ``-k --checkpoint [str]``: Optional name of the starting checkpoint, or "latest".
    - ``-g --save-git``: Optional flag to log the git status.

    Parameters
    ----------
    description : str
        Description for the argument parser.

    Returns
    -------
    argparse.ArgumentParser
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        '-o',
        '--output-dir',
        type=Path,
        default='./out',
        help='Path to the output directory.',
    )
    parser.add_argument(
        '-c',
        '--config',
        type=Path,
        default=None,
        help='Optional, path to a configuration file (supported extensions: *.json, *.yaml/yml, *.toml)',
    )
    parser.add_argument(
        '-k',
        '--checkpoint',
        type=str,
        default=None,
        help='Optional, name of the starting checkpoint, or "latest".',
    )
    parser.add_argument(
        '-g',
        '--save-git',
        action='store_true',
        help='Optional, log the git status.',
    )

    return parser


def cli_args_to_config(args: list[str]) -> dict[str, Any]:
    """Converts a list of CLI arguments into a configuration dictionary.

    Supports arguments in the form of `--key=value` or `--key value`.
    Flags without values are interpreted as boolean `True`.
    The function attempts to convert values to `int`, `float`, or `bool`
    where appropriate; otherwise, values are treated as strings.

    Parameters
    ----------
    args : list[str]
        List of command-line arguments.

    Returns
    -------
    dict[str, Any]
        Configuration dictionary parsed from the CLI arguments.
    """
    parsed: dict[str, Any] = {}

    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith('--'):
            i += 1
            continue

        key_val = token[2:]
        if '=' in key_val:
            key, val_str = key_val.split('=', 1)
        else:
            # Look ahead for a separate value token.
            if i + 1 < len(args) and not args[i + 1].startswith('-'):
                val_str = args[i + 1]
                i += 1
            else:
                val_str = None
            key = key_val

        parsed[key] = _convert_value(val_str)
        i += 1

    return parsed


def _convert_value(val: str | None) -> Any:
    # Flag
    if val is None:
        return True

    low = val.lower()
    if low == 'true':
        return True
    if low == 'false':
        return False

    try:
        return int(val)
    except Exception:
        pass

    try:
        return float(val)
    except Exception:
        pass

    # Handle strings
    return val
