import argparse
from pathlib import Path
from typing import Any


def default_argparser(description: str = 'Lepel experiment pipeline') -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        '-o', '--output-dir', type=Path, default='.', help='Path to the output directory.'
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

    return parser


def cli_args_to_config(args: list[str]) -> dict[str, Any]:
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
