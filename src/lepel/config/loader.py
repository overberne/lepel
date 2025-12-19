import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, cast

try:
    import tomllib as _toml  # Python 3.11+
except Exception:
    try:
        import toml as _toml  # type: ignore
    except Exception:
        _toml = None  # type: ignore

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore


def load_config_file(path: str | PathLike[str] | Path) -> Mapping[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f'Config file not found: {path}')

    config = None
    text = path.read_text(encoding='utf-8')
    suffix = path.suffix.lower()
    match suffix:
        case '.yaml' | '.yml':
            if yaml is None:
                raise RuntimeError('PyYAML is required to load YAML config files')
            config = yaml.safe_load(text)
        case '.json':
            config = json.loads(text)
        case '.toml':
            if _toml is None:
                raise RuntimeError('tomllib (py3.11) or toml package required for TOML files')
            # tomllib exposes loads, while toml (3rd party) also exposes loads
            config = _toml.loads(text)  # type: ignore
        case _:
            raise RuntimeError(f'Unsupported config file type: {suffix}')

    if not isinstance(config, Mapping):
        raise RuntimeError('Config file must contain a mapping at the top level')

    return cast(Mapping[str, Any], config)
