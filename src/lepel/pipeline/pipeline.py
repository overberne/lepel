# pyright: reportPrivateUsage=false
import sys
import warnings

# from logging import Logger, getLogger
from logging import getLogger
from os import PathLike
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from lepel.core import CheckpointManager, Context, DependencyManager, PipelineStep, StateManager
from lepel.core.state import Fingerprints
from lepel.extensions.cloudpickle_file_store import CloudpickleFileStore
from lepel.pipeline._checkpoint import Checkpoint
from lepel.pipeline._io import (
    copy_main_script_to_output,
    get_unique_run_subdir,
    load_and_save_configs_to_output,
)
from lepel.pipeline._reflection import all_subclasses, wrap_subclasses_method
from lepel.pipeline._state_snapshot import StateSnapshot

_CHECKPOINTS_RELPATH = Path('checkpoints')
logger = getLogger(__name__)


def run_pipeline(
    recipe: Callable[..., Any],
    *,
    output_dir: str | PathLike[str] | Path,
    config_file: str | PathLike[str] | Path | None = None,
    checkpoint: str | None = None,
    save_git: bool = False,
    auto_checkpoint: bool = True,
    auto_subdirs: bool = True,
    **config_override: Any,
) -> None:
    """Run a pipeline function with dependency injection, config and checkpoints.

    The ``recipe`` callable defines a sequence of pipeline steps and a
    preamble where dependencies can be registered on the provided
    :class:`~lepel.core.DependencyManager`; state can be
    tracked using :class:`~lepel.core.StateManager` which will be saved in
    checkpoints. This function sets up configuration, the dependency manager,
    optional checkpoint restoration, and a set of context variables,
    and then executes the pipeline. Pipeline step classes that inherit from
    :class:`PipelineStep` are detected automatically and their constructors are
    wrapped so the pipeline runner can control execution order, validation,
    and checkpoint semantics.

    Extra keyword arguments passed to this function are treated as configuration
    overrides and merged into the loaded configuration.

    Parameters
    ----------
    recipe : Callable[..., Any]
        The pipeline entry function. It will be called with its arguments
        injected from the dependency manager. Typically this function will
        import or reference pipeline step classes which are instantiated as
        part of pipeline execution.
    output_dir : str | PathLike[str] | Path
        Directory to use for pipeline outputs. The pipeline will copy the
        resolved configuration files into this directory and write artifacts
        (including checkpoints) under it.
    config_file : str | PathLike[str] | Path | None, optional
        Path to a configuration file to load. If omitted, the runner will look
        in the directory `sys.argv[0]` for a file named ``config.yaml``/
        ``config.yml``/``config.json``/``config.toml``. When provided, the
        configuration file will be copied into ``output_dir``.
    checkpoint : str | None, optional
        If provided, a checkpoint file name or the special value ``'latest'``.
        When set, the runner will attempt to load the checkpoint and resume
        execution from the next step after the matching step with the same name.
    save_git : bool, optional
        When true, saves the git status to a `/git` subdirectory.
    auto_checkpoint : bool, optional
        When true, automatically creates a checkpoint after each pipeline step.
    auto_subdirs : bool, optional
        When true, stores the run in a subdirectory `YYYYMMdd-HHmmss-{slug1}-{slug2}`
    **config_override : Any
        Additional keyword arguments are treated as configuration overrides.
        These are merged with the loaded configuration and also saved into
        ``output_dir`` as ``config_override.*`` alongside the copied
        configuration file.
    """
    # Create output path and copy recipe file
    output_dir = Path(output_dir)
    if auto_subdirs:
        output_dir = get_unique_run_subdir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    copy_main_script_to_output(output_dir)

    if save_git:
        from lepel.extensions.git import save_git_status

        save_git_status(output_dir)

    config_name, config = load_and_save_configs_to_output(output_dir, config_file, config_override)
    if config_name:
        logger.info('Configuration "%s" loaded', str(config_name))
    if config_override:
        logger.info(
            'Overriding %d configuration values:\n%s',
            len(config_override),
            _config_repr(config_override),
        )

    # Setup state, checkpointing, dependencies, and context
    context = Context()
    context.output_dir = output_dir
    context.pipeline_name = _get_pipeline_name()
    state = StateManager()
    state.track(context)
    checkpoint_dir = output_dir / _CHECKPOINTS_RELPATH
    checkpointing = CheckpointManager[StateSnapshot](checkpoint_dir, CloudpickleFileStore())
    dependencies = DependencyManager()
    _add_flat_config_items_to_dependencies(dependencies, config)
    dependencies.add_singleton(config, name='config')
    dependencies.add_singleton(config, Mapping[str, Any], name='config')
    dependencies.add_singleton(context)
    dependencies.add_singleton(state)
    dependencies.add_singleton(checkpointing)

    checkpoint_reached = True
    checkpoint_name = None
    checkpoint_data = None
    fingerprints: Fingerprints = {}
    results: list[Any] = []
    # Load checkpoint data, if any
    if checkpoint == 'latest':
        checkpoint_name, checkpoint_data = checkpointing.load_latest()

        if checkpoint_name is None or checkpoint_data is None:
            logger.warning('Checkpoint "latest" requested but no checkpoints found.')
        else:
            logger.info('Latest checkpoint found: %s', str(checkpoint_name))
    elif checkpoint:
        try:
            checkpoint_name, checkpoint_data = checkpointing.load(checkpoint)
            logger.info('Checkpoint found: %s', str(checkpoint_name))
        except FileNotFoundError:
            logger.error('Checkpoint "%s" not found', checkpoint)
            raise
    if checkpoint_data is not None:
        checkpoint_reached = False
        state.load(checkpoint_data['state_dicts'])
        fingerprints = checkpoint_data['fingerprints']
        results = checkpoint_data['step_results']

    current_step = 0

    def run_step_wrapper(original_run_step: Callable[..., Any]) -> Callable[..., Any]:
        """Wraps the __run_step__ functions of all imported PipelineStep implementations."""

        def new_run_step(self: PipelineStep) -> Any:
            nonlocal checkpoint_reached, current_step, results, fingerprints

            # Validate dependencies when running first step
            # user may have registered dependencies in the preamble of the pipeline
            if current_step == 0:
                _validate_dependencies(dependencies)

                # Save initial state as a checkpoint
                if auto_checkpoint and checkpoint_reached:
                    state_dicts, fingerprints = state.snapshot()
                    snapshot: StateSnapshot = {
                        'state_dicts': state_dicts,
                        'fingerprints': fingerprints,
                        'step_results': results,
                    }
                    checkpointing.save_full(
                        'initial',
                        snapshot,
                    )

            if isinstance(self, Checkpoint):
                if f'{current_step:04d}_{self.name}' == checkpoint_name:
                    checkpoint_reached = True
                elif checkpoint_reached:
                    logger.info('%04d Creating checkpoint "%s"', current_step, self.name)
                    state_dicts, fingerprints = state.snapshot()
                    snapshot: StateSnapshot = {
                        'state_dicts': state_dicts,
                        'fingerprints': fingerprints,
                        'step_results': results,
                    }
                    checkpointing.save_full(self.name, snapshot)
                results.append(None)
                current_step += 1
                return None

            current_step += 1
            if not checkpoint_reached:
                if current_step > len(results):
                    raise RuntimeError(
                        f'Checkpoint "{checkpoint_name}" did not contain enough stored results'
                    )
                return results[current_step - 1]
            else:
                step_name = self.__class__.__name__
                context.pipeline_step = step_name
                logger.info('%04d %s: Started', current_step, step_name)
                result = self.run(**dependencies.prepare_injection(self.run))

                if auto_checkpoint:
                    state_delta, fingerprints = state.delta(fingerprints)
                    checkpointing.save_incremental(
                        step_name,
                        {
                            'state_dicts': state_delta,
                            'fingerprints': fingerprints,
                            'step_results': [result],
                        },
                    )

                logger.info('%04d %s: Finished', current_step, step_name)
                results.append(result)
                return result

        return new_run_step

    unwrap_pipeline_steps = wrap_subclasses_method(PipelineStep, '__run_step__', run_step_wrapper)
    logger.info('Running pipeline...')
    recipe(**dependencies.prepare_injection(recipe))
    logger.info('Pipeline finished!')
    unwrap_pipeline_steps()


def run_step[T](step: PipelineStep[T]) -> T:
    """
    Execute a single pipeline step with dependency injection.

    Must be called within a ``run_pipeline`` context so that dependencies
    can be prepared and injected.

    Parameters
    ----------
    step : PipelineStep[T]
        The pipeline step instance to execute.

    Returns
    -------
    T
        The result of the pipeline step's ``run`` method.
    """
    return step.__run_step__()


def checkpoint(name: str) -> None:
    """
    Create a pipeline checkpoint at the current location in the pipeline.

    When the pipeline execution reaches this point, the current state of the
    pipeline is serialized and saved to a checkpoint file named ``name``,
    prefixed by the step number, in the pipeline's checkpoints directory.
    """
    Checkpoint(name).__run_step__()


def _get_pipeline_name() -> str:
    return Path(sys.argv[0]).name.split('.', 1)[0]


def _config_repr(config_overrides: dict[str, Any]) -> str:
    return '\n'.join([f'  {key}={value}' for key, value in config_overrides.items()])


def _validate_dependencies(dependencies: DependencyManager) -> None:
    try:
        dependencies.validate()
    except RuntimeError as e:
        warnings.warn(str(e), RuntimeWarning, stacklevel=3)

    for cls in all_subclasses(PipelineStep):
        try:
            dependencies.throw_if_uninjectable(cls.run)
        except RuntimeError as e:
            warnings.warn(str(e), RuntimeWarning, stacklevel=3)


def _add_flat_config_items_to_dependencies(
    dependencies: DependencyManager,
    config: dict[str, Any],
    prefix: str = '',
) -> None:

    for key, value in config.items():
        if isinstance(value, dict):
            _add_flat_config_items_to_dependencies(
                dependencies,
                config=cast(dict[str, Any], value),
                prefix=f'{prefix}{key}.',
            )
        else:
            dependencies.add_singleton(value, name=f'{prefix}{key}')
