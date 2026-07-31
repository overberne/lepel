# Lepel - Learning Recipe Library

**Lepel** is a tiny, single-machine pipeline runner for experiment-style workflows: define a "recipe" that wires dependencies, runs ordered steps, and automatically persists/resumes state via checkpoints.

It's designed for:

- Reproducible local experiments (config captured in the output directory)
- Interruptible pipelines (resume from checkpoints)
- Lightweight dependency injection (DI) without a framework

---

## Installation

### From source (development)

```bash
pip install git+https://github.com/overberne/lepel
```

### Optional dependencies

Lepel supports YAML/TOML configs when the corresponding libraries are installed:

- YAML: `PyYAML`
- TOML: `toml` (not tomllib included with Python 3.11+, which (currently) has no writing capabilities)

---

## Core ideas

### Pipeline recipe

A **recipe** is a normal Python callable. Lepel injects its arguments from the dependency container (including config values). Inside the recipe you:

1. **Register dependencies** (singletons/transients)
1. **Track stateful objects** for checkpointing
1. **Run steps** using `run_step(...)`
1. Optionally add explicit checkpoints using `checkpoint("name")` (incremental checkpoints are automatically created after each step)

### Dependency injection

`DependencyManager` is a simple DI container that can:

- register factories (`add_transient`) and instances (`add_singleton`)
- resolve dependencies by type and/or name
- inject arguments into callables by inspecting type annotations

#### Resolution order

1. `(Type, "MethodClassName.param_name")` (class-specific binding to help prevent name collisions in configuration)
1. `(Type, "param_name")`
1. `(Type, None)` (type-only)

### Recipe steps

A recipe step is a `RecipeStep` subclass that implements `run(...)`. Lepel injects parameters of `run(...)` just like recipe parameters.

### Checkpointing & resuming

- Lepel writes checkpoints into: `output_dir/checkpoints/`
- Filenames are monotonic and include step index + logical name:
  - step checkpoints: `0000_StepClassName.delta.pkl`
  - explicit checkpoints: `0003_mid.full.pkl` (created by `checkpoint("mid")`)
- Resuming:
  - `checkpoint="latest"` restores the newest reconstructible state
  - `checkpoint="<stem or name>"` loads a specific checkpoint
- What's stored
- tracked stateful objects (via `StateManager`)
- fingerprints/dirty flags (for incremental checkpointing)
- step results (so resumed runs can skip already-computed work)

Serialization is done with `cloudpickle`.

---

## Quickstart

### 1. Define stateful objects (optional but recommended)

If you want objects to be checkpointed/resumed, implement the `Stateful` protocol:

- `state_dict() -> Mapping[str, Any]`
- `load_state_dict(state) -> None`

For efficient incremental checkpoints, optionally implement:

- `DirtyTrackable` (`is_dirty`, `clear_dirty`)
- `Fingerprintable` (`state_fingerprint`)

```python
from typing import Mapping, Any

class Counter:
    def __init__(self) -> None:
        self.value = 0
        self._dirty = True

    def inc(self, by: int) -> None:
        self.value += by
        self._dirty = True

    # Stateful
    def state_dict(self) -> Mapping[str, Any]:
        return {"value": self.value}

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        self.value = state["value"]
        self._dirty = True

    # DirtyTrackable (optional, speeds up delta checkpoints)
    def is_dirty(self) -> bool:
        return self._dirty

    def clear_dirty(self) -> None:
        self._dirty = False
```

### 2. Write steps

```python
from typing import Any, Mapping
from lepel import RecipeStep

class MyStep(RecipeStep[int]):
    def __init__(self, by: int) -> None:
        self.by = by

    def run(self, counter: Counter) -> int:
        counter.inc(self.by)
        return counter.value
```

### 3. Write a recipe and run it

```python
from pathlib import Path
from lepel import Context, DependencyManager, StateManager, checkpoint, run_recipe, run_step

def recipe(
    context: Context,
    dependencies: DependencyManager,
    state: StateManager,
    by: int,  # injected from config key "by"
) -> None:
    counter = Counter()
    dependencies.add_singleton(counter)
    state.track(counter)
    print(context.output_dir)  # Output directory is available from context

    run_step(MyStep(by))
    checkpoint("mid")
    run_step(MyStep(1))


if __name__ == "__main__":
    run_recipe(
        recipe,
        output_dir="output",
        config_file="config.yaml",
        save_git=True,
        by=2,  # optional override (also works via config / CLI parsing helper)
    )
```

---

## Configuration

### Supported formats

Use `lepel.pipeline._config.load_config/save_config` via the `run_recipe`:

- `.yaml` / `.yml` (requires `PyYAML`)
- `.json`
- `.toml` (requires `toml`)

### How config is used

- Config is loaded and copied into the `output_dir`
- Any keyword args passed to `run_recipe(..., **overrides)` override config values
- A `config_override.*` file may be discovered alongside the main script and merged
- The full config dict is registered into DI as:
  - `config` (named singleton, `dict`)
  - `config` (named singleton, `Mapping[str, Any]`)

### Flat config injection

Top-level and nested config values are also registered as named singletons:

- `{"lr": 0.1}` -> injectable as `lr: float`
- `{"train": {"epochs": 10}}` -> injectable as `train.epochs: int` (name-based)
  - See method class name resolution in the dependency manager.
  - OR, access the config directly as injectable as `config: Mapping[str, Any]`

This makes it easy to inject individual settings directly into recipes/steps, and handle any name collisions with global / local configuration.

---

## CLI helpers

Lepel provides small helpers; you build the actual CLI wrapper yourself.

`default_argparser()`
Creates an `argparse.ArgumentParser` with:

- `-o` / `--output-dir`
- `-c` / `--config`
- `-k` / `--checkpoint` (name or `"latest"`)
- `-g` / `--save-git`

`cli_args_to_config(args: list[str])`
Parses extra `--key=value` / `--key value` arguments into a dict and tries to type values
`(int, float, bool)`, otherwise keeps strings.

Example:

```python
from lepel.extensions.cli import default_argparser, cli_args_to_config
from lepel import run_recipe

parser = default_argparser()
args, extras = parser.parse_known_args()

overrides = cli_args_to_config(extras)

run_recipe(
    recipe,
    output_dir=args.output_dir,
    config_file=args.config,
    checkpoint=args.checkpoint,
    save_git=args.save_git,
    **overrides,
)
```

---

## API reference (public)

Imported from `lepel`:

### Pipeline execution

- `run_recipe(recipe, *, output_dir, config_file=None, checkpoint=None, save_git=False, auto_checkpoint=True, auto_subdirs=True, **overrides)`
- `run_step(step)`
- `checkpoint(name)`

### Core types

- `RecipeStep` - base class for steps (implement `run`)
- `DependencyManager` - DI container
- `Context` - attribute/dict backed runtime context (tracked by default)
- `StateManager` - tracks Stateful objects and produces snapshots/deltas
- `Stateful`, `DirtyTrackable`, `Fingerprintable` - state protocols

### Checkpointing internals

- `CheckpointManager` - manages `.full.pkl` and `.delta.pkl` files
- `CheckpointFileStore` - protocol for persistence backends
- `CloudpickleFileStore` - default store used by the pipeline runner

---

## Output layout

A typical run directory looks like:

```bash
output/
  config.yaml
  config_override.yaml
  your_script.py
  checkpoints/
    0000_initial.full.pkl
    0001_StepAdd.delta.pkl
    0002_mid.full.pkl
    0003_StepAdd.delta.pkl
  git/                      # if save_git=True
    changes.txt
    branch.main
    commit.<hash>
    changes/...
```

If `auto_subdirs=True` (default), Lepel creates a unique subdirectory: `YYYYMMDD-HHMMSS-<slug>` under `output_dir`.

---

## Notes & caveats

- Checkpoints use `cloudpickle`. Loading across different Python versions or dependency versions may fail or produce subtle issues, so treat checkpoints as best-effort, same-environment artifacts.
- Dependency injection relies on type annotations (and parameter names for named bindings). Unannotated parameters typically won't be injectable.
- The runner wraps `RecipeStep` subclasses dynamically; step classes must be imported/defined before they are instantiated.
