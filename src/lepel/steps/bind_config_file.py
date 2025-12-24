import json
from pathlib import Path
from typing import Mapping

from lepel.config_ import bind_config_values, config_setting
from lepel import PipelineStep, DependencyManager

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


class BindConfigFromDisk(PipelineStep):
    @config_setting
    def config_file(self) -> str: ...

    def run(self, dependencies: DependencyManager) -> None:
        path = Path(self.config_file)
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

        bind_config_values(**config)  # pyright: ignore[reportUnknownArgumentType]
        dependencies.update_context_variables(**config)
