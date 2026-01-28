import os
from pathlib import Path
from typing import Any, Mapping

from lepel import DependencyManager, RecipeStep, checkpoint, run_recipe, run_step, wire
from lepel.core.state import StateManager


class Counter:
    def __init__(self) -> None:
        self.value = 0
        self._dirty = True

    def inc(self, by: int) -> None:
        self.value += by
        self._dirty = True

    # Stateful
    def state_dict(self) -> Mapping[str, Any]:
        return {'value': self.value}

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        self.value = state['value']
        self._dirty = True

    # DirtyTrackable
    def is_dirty(self) -> bool:
        return self._dirty

    def clear_dirty(self) -> None:
        self._dirty = False


class StepAdd(RecipeStep[int]):
    def __init__(self, by: int) -> None:
        super().__init__()
        self.by = by

    def run(self, counter: Counter) -> int:
        counter.inc(self.by)
        return counter.value


@wire
class WireTestClass:
    def __init__(self, counter: Counter) -> None:
        self.counter = counter


def test_run_recipe_creates_checkpoints_and_saves_config(tmp_path: Path):
    output_dir = tmp_path / 'out'
    output_dir.mkdir()

    config_file = tmp_path / 'config.json'
    config_file.write_text('{"by": 2}', encoding='utf-8')

    counter = Counter()

    def recipe(
        dependencies: DependencyManager, state: StateManager, config: Mapping[str, Any]
    ) -> None:
        dependencies.add_singleton(counter)
        state.track(counter)
        WireTestClass()  # Should not throw

        run_step(StepAdd(config['by']))  # should increment counter by 2
        checkpoint('mid')
        run_step(StepAdd(1))  # then increment by 1

    # Run from a stable cwd so checkpoints are found under output_dir/checkpoints
    original_cwd = Path.cwd()
    try:
        os.chdir(output_dir)

        run_recipe(recipe, output_dir=output_dir, config_file=config_file, auto_subdirs=False)

        # config copied
        assert (output_dir / 'config.json').exists()

        # checkpoints exist
        checkpoints_dir = output_dir / 'checkpoints'
        assert checkpoints_dir.exists()
        files = sorted(p.name for p in checkpoints_dir.glob('*.pkl'))
        assert any(name.endswith('.delta.pkl') for name in files)
        assert any(name.endswith('.full.pkl') for name in files)

        # counter should have been incremented by 2 then 1
        assert counter.value == 3
    finally:
        os.chdir(original_cwd)
