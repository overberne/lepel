import os
from pathlib import Path
from typing import Any, Protocol

from lepel import DependencyManager, PipelineStep, checkpoint, run_pipeline, run_step


class FooProtocol(Protocol):
    def foo(self, bar: str) -> str: ...


class TransientService:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def foo(self, bar: str) -> str:
        return bar


class SingletonService:
    def __init__(self, value: str):
        self.value = value

    def foo(self, bar: str) -> str:
        return bar

    def state_dict(self) -> dict[str, Any]:
        return {'value': self.value}

    def load_state_dict(self, state_dict: dict[str, Any]) -> None:
        print('statedict val', state_dict)
        self.value = state_dict['value']


def test_pipeline(tmp_path: Path):
    first_step: str | None = None
    foo_value: int = 0

    class SetFirstStepIfNotSet(PipelineStep):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

        def run(
            self,
            foo: int,
            dependencies: DependencyManager,
            tservice: TransientService,
            sservice: SingletonService,
        ) -> None:
            nonlocal first_step
            if first_step is None:
                first_step = self.name

    singleton = SingletonService('foo')

    def pipeline(foo: int, dependencies: DependencyManager) -> None:
        # For testing loading from checkpoints
        nonlocal foo_value
        foo_value = foo
        # Preamble
        dependencies.register(TransientService)
        dependencies.register_singleton(singleton)
        # Pipeline
        run_step(SetFirstStepIfNotSet('before-checkpoints'))
        checkpoint('first')
        run_step(SetFirstStepIfNotSet('inbetween-checkpoints'))
        checkpoint('second')
        run_step(SetFirstStepIfNotSet('after-checkpoints'))

    output_dir = tmp_path / 'output'
    output_dir.mkdir()
    config_file = tmp_path / 'config.json'
    config_file.write_text('{"foo": 1}', encoding='utf-8')

    # First run: create checkpoints and copy config into output_dir.
    run_pipeline(pipeline, output_dir=output_dir, config_file=config_file)
    assert first_step == 'before-checkpoints'
    # Assert config file has been copied over to the output directory.
    assert (output_dir / 'config.json').exists()
    # Assert initial singleton value is preserved.
    assert singleton.value == 'foo'
    assert foo_value == 1

    # Mutate singleton and restore from the first checkpoint. The pipeline looks
    # for checkpoints in the current working directory, so change cwd to the
    # output directory so the saved checkpoints are discoverable.
    orig_cwd = Path.cwd()
    try:
        os.chdir(output_dir)
        first_step = None
        singleton.value = 'bar'
        run_pipeline(pipeline, output_dir=output_dir, config_file=config_file, checkpoint='first')
        assert first_step == 'inbetween-checkpoints'
        assert singleton.value == 'foo'  # checks loading of dependencies

        # Load latest checkpoint and continue to the end.
        first_step = None
        run_pipeline(pipeline, output_dir='.', checkpoint='latest', foo=2)
        assert foo_value == 2
        assert first_step == 'after-checkpoints'
    finally:
        os.chdir(orig_cwd)
