import json
from pathlib import Path
from typing import Any, Mapping, cast

try:
    import toml  # type: ignore
except ImportError:
    toml = None  # type: ignore

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore


def load_config(config_file: Path) -> dict[str, Any]:
    if not config_file.exists():
        raise FileNotFoundError(f'Config file not found: {config_file}')

    config = None
    text = config_file.read_text(encoding='utf-8')
    suffix = config_file.suffix.lower()
    match suffix:
        case '.yaml' | '.yml':
            if yaml is None:
                raise RuntimeError('PyYAML is required to load YAML config files')
            config = yaml.safe_load(text)
        case '.json':
            config = json.loads(text)
        case '.toml':
            if toml is None:
                raise RuntimeError('tomllib (py3.11) or toml package required for TOML files')
            # tomllib exposes loads, while toml (3rd party) also exposes loads
            config = toml.loads(text)  # type: ignore
        case _:
            raise RuntimeError(
                f'Unsupported config file type: {suffix}, supported extensions: .yaml, .yml, .json, .toml'
            )

    if not isinstance(config, Mapping):
        raise RuntimeError('Config file must contain a mapping at the top level')

    return dict(cast(Mapping[str, Any], config))


def save_config(config: Mapping[str, Any], config_file: Path) -> None:
    config_file.parent.mkdir(exist_ok=True)
    suffix = config_file.suffix.lower()
    match suffix:
        case '.yaml' | '.yml':
            if yaml is None:
                raise RuntimeError('PyYAML is required for YAML files')
            with open(config_file, 'w') as handle:
                yaml.safe_dump(config, handle)
        case '.json':
            with open(config_file, 'w') as handle:
                json.dump(config, handle, indent=4, ensure_ascii=False)
        case '.toml':
            if toml is None:
                raise RuntimeError('toml package is required for TOML files')
            # tomllib exposes loads, while toml (3rd party) also exposes loads
            with open(config_file, 'w') as handle:
                toml.dump(config, handle)
        case _:
            raise RuntimeError(
                f'Unsupported config file type: {suffix}, supported extensions: .yaml, .yml, .json, .toml'
            )
