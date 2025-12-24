import sys
from typing import Any

from lepel.config_ import bind_config_values
from lepel import PipelineStep


class RegisterCliArgsToConfig(PipelineStep):
    """Registers CLI arguments as configuration values.

    Supports forms: `--a 1 --b.c 2 --d=3 --flag (becomes True)`.
    """

    def run(self) -> None:
        parsed: dict[str, Any] = {}

        args = sys.argv[1:]
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

        if parsed:
            bind_config_values(**parsed)


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
    if len(val) >= 2 and ((val[0] == val[-1] == "'") or (val[0] == val[-1] == '"')):
        return val[1:-1]
    return val
