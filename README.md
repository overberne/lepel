# LEarning PipELine (Lepel)

Minimal utilities to author, run and resume single-machine experiment pipelines.

## Installation

- Install from source for development:

```bash
pip install git+https://github.com/overberne/lepel
```

## Concepts

- DependencyManager: simple DI container for wiring factories and singletons, resolving by type or name and holding runtime config/context variables.
- PipelineStep: abstract base for pipeline steps. Steps implement `run(self, ...)` and receive injected args (e.g. `output_dir`, `pipeline_step`, `dependencies`).
- checkpoint: small typed dict + helpers (save/load) that serialize the dependency manager state via cloudpickle.
- run_pipeline: runner that loads config, applies overrides, wires a `DependencyManager`, copies config into `output_dir`, and executes pipeline steps in order. Checkpoints can be saved and resumed.
- run_step: injects dependencies into step.run(...) and stores results for checkpointing.

## Quickstart

- Write a pipeline function that registers dependencies on a `DependencyManager` and imports/uses `PipelineStep` subclasses. Example sketch:

```python
from lepel import DependencyManager, PipelineStep, checkpoint, run_pipeline, run_step
from my_library import MyPipelineStep

def pipeline(dependencies: DependencyManager):
    # Preamble: register factories/singletons on dependencies
    dependencies.register(...)
    # Pipeline body
    result = run_step(MyPipelineStep(**options))
    checkpoint('first')
    run_step(MyPipelineStep(**options))

if __name__ == '__main__':
    run_pipeline(pipeline, output_dir='output', config_file='config.yaml')
```

### CLI helpers

- `default_argparser()` provides a standard argparse ArgumentParser with `--output-dir`, `--config` and `--checkpoint`.
- `cli_args_to_config(args: list[str])` converts `--key=value` or `--key value` style args into a dict with typed values (ints, floats, booleans).

### Configuration

- `lepel.config.load_config(path)` / `save_config(mapping, path)` support `.yaml/.yml`, `.json` and `.toml` (requires PyYAML and toml as needed).
- Config override files named `config_override.*` are supported and merged with CLI overrides.

### API Reference (core symbols)

- `lepel.DependencyManager` — register factories (`register`), register singletons (`register_singleton`), resolve dependencies (`resolve`), update context (`update_context_variables`) and persist state (`state_dict` / `load_state_dict`).
- `lepel.PipelineStep` — base class for steps; implement `run`.
- `lepel.checkpoint` (function), `lepel.Checkpoint` (class) and functions `save_checkpoint`, `load_checkpoint` in `lepel.checkpoint`.
- `lepel.run_pipeline(...)` — runs a pipeline callable with config, DI and checkpoint support.
- `lepel.default_argparser()` and `lepel.cli_args_to_config()` — small CLI helpers.

### Notes

- Checkpoint files are pickled with `cloudpickle` — ensure compatibility when loading across Python/package versions.
