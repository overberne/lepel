# pyright: reportPrivateUsage=false
import inspect
import shutil
import warnings
from abc import ABC, abstractmethod
from logging import Logger, getLogger
from os import PathLike
from pathlib import Path
from typing import Any, Callable, Type
import sys

from lepel.checkpoint import Checkpoint as CheckpointData
from lepel.checkpoint import load_checkpoint, save_checkpoint
from lepel.config import load_config, save_config
from lepel.dependency_manager import DependencyManager

_CONFIG_EXTENSIONS = ('.yaml', '.yml', '.json', '.toml')
_CONFIG_GLOB_PATTERNS = tuple(f'config{ext}' for ext in _CONFIG_EXTENSIONS)
_CONFIG_OVERRIDE_GLOB_PATTERNS = tuple(f'config_override{ext}' for ext in _CONFIG_EXTENSIONS)
_CHECKPOINTS_RELPATH = Path('checkpoints')


class PipelineStep[T = None](ABC):
    """Abstract base class for pipeline steps.

    Subclasses should implement the ``run`` method. Pipeline steps are instantiated
    during pipeline execution and their constructor is wrapped by the pipeline to
    orchestrate ordering, checkpoint handling, and dependency injection.
    """

    def __run_step__(self) -> T:
        raise NotImplementedError('This should be wrapped/replaced by the run_pipeline() function.')

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> T:
        """Execute the pipeline step.

        Implementations of this method perform the work for a single pipeline
        step. When ``run_pipeline`` is executing, dependencies are prepared and
        injected automatically into ``run``. Common injectable arguments include
        ``output_dir`` (Path), ``pipeline_step`` (str) and ``dependencies`` (a
        :class:`~lepel.dependency_manager.DependencyManager`).

        Returns
        -------
        None
            Steps do not return a value; they are expected to have side effects
            such as saving artifacts to ``output_dir`` or updating the
            dependency manager state.
        """
        raise NotImplementedError()


class Checkpoint(PipelineStep):
    def __init__(self, name: str) -> None:
        """Create a pipeline checkpoint step.

        The checkpoint step, when reached during pipeline execution, serializes
        the current dependency manager state into a :class:`~lepel.checkpoint.Checkpoint`
        and saves it to the pipeline's ``checkpoints`` directory.

        Parameters
        ----------
        name : str
            Logical name for the checkpoint. Checkpoints saved by this step are
            written to the output ``checkpoints`` directory with this name as
            the filename. The name can later be provided to ``run_pipeline``
            via the ``checkpoint`` argument to resume execution from that
            checkpoint.
        """
        super().__init__()
        self.name = name

    def run(self, output_dir: Path, dependencies: DependencyManager) -> None:
        checkpoint = CheckpointData(name=self.name, state_dict=dependencies.state_dict())
        save_checkpoint(checkpoint, output_dir / _CHECKPOINTS_RELPATH)


def run_pipeline(
    pipeline: Callable[..., Any],
    *,
    output_dir: str | PathLike[str] | Path,
    config_file: str | PathLike[str] | Path | None = None,
    checkpoint: str | None = None,
    dependencies: DependencyManager | None = None,
    logger: Logger = getLogger(),
    **config_override: Any,
) -> None:
    """Run a pipeline function with dependency injection, config and checkpoints.

    The ``pipeline`` callable defines a sequence of pipeline steps and a
    preamble where dependencies can be registered on the provided
    :class:`~lepel.dependency_manager.DependencyManager`. This function sets up
    configuration, the dependency manager, optional checkpoint restoration,
    and then executes the pipeline. Pipeline step classes that inherit from
    :class:`PipelineStep` are detected automatically and their constructors are
    wrapped so the pipeline runner can control execution order, validation,
    and checkpoint semantics.

    Extra keyword arguments passed to this function are treated as configuration
    overrides and merged into the loaded configuration.

    Parameters
    ----------
    pipeline : Callable[..., Any]
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
        execution from the next step after the matching :class:`Checkpoint`
        step with the same name.
    dependencies : DependencyManager, optional
        Optional :class:`~lepel.dependency_manager.DependencyManager` instance.
        If provided, this dependency manager will be used instead of creating
        a new one from the loaded configuration. The runner will update
        its internal configuration to reflect the merged configuration.
    logger : Logger, optional
        Logger instance used for informational messages. Defaults to
        ``logging.getLogger()``.
    **config_override : Any
        Additional keyword arguments are treated as configuration overrides.
        These are merged with the loaded configuration and also saved into
        ``output_dir`` as ``config_override.*`` alongside the copied
        configuration file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    _copy_pipeline_file_to_output(output_dir)

    if config_file:
        config_file = Path(config_file)
        _copy_config_file_to_output(output_dir, config_file)
        config = load_config(config_file)
        logger.info('Configuration file loaded: %s', str(config_file))
    else:
        # Look for a config file in the directory of the pipeline file.
        config_file = _find_config_file(Path(sys.argv[0]).parent)
        config: dict[str, Any] = load_config(config_file) if config_file else {}
        logger.info('Configuration file loaded: %s', str(config_file))
        config_override_file = _find_config_override_file(Path(sys.argv[0]).parent)
        if config_file:
            _copy_config_file_to_output(output_dir, config_file)
        if config_override_file:
            loaded_config_override = load_config(config_override_file)
            loaded_config_override.update(config_override)
            config_override = loaded_config_override
    if config_override:
        config.update(config_override)
        _save_config_override_to_output(output_dir, config_override, config_file)
        logger.info(
            'Overriding %d configuration values:\n%s',
            len(config_override),
            _config_repr(config_override),
        )

    if dependencies:
        dependencies._config.update(config)
    else:
        dependencies = DependencyManager(config)
    dependencies.context.output_dir = output_dir
    dependencies.context.pipeline_name = _get_pipeline_name()

    checkpoint_reached = True
    checkpoint_file = None
    checkpoint_name = None
    checkpoint_data = None
    # Load checkpoint data, if any
    if checkpoint:
        checkpoint_file = _find_checkpoint_file(checkpoint)
        checkpoint_data = load_checkpoint(checkpoint_file)
        checkpoint_name = checkpoint_data['name']
        checkpoint_reached = False
        logger.info('Checkpoint "%s" found', checkpoint_name)

    results: list[Any] = []
    dependencies.context.__results__ = results
    dependencies_validated = False
    current_step = 0

    def run_step_wrapper(original_run_step: Callable[..., Any]) -> Callable[..., Any]:
        """Wraps the __run_step__ functions of all imported PipelineStep implementations."""

        def new_run_step(self: PipelineStep) -> Any:
            nonlocal checkpoint_reached, current_step, dependencies_validated, results

            # Validate dependencies when running first step
            # user may have registered dependencies in the preamble of the pipeline
            if not dependencies_validated:
                dependencies_validated = True
                _validate_dependencies(dependencies)
                if checkpoint_data:
                    dependencies.load_state_dict(checkpoint_data['state_dict'])
                    results = dependencies.context.__results__

            if isinstance(self, Checkpoint):
                if self.name == checkpoint_name:
                    checkpoint_reached = True
                elif checkpoint_reached:
                    logger.info('Creating checkpoint %s', self.name)
                    self.run(**dependencies.prepare_injection(self.run))
                return None

            current_step += 1
            if checkpoint_reached:
                step_name = self.__class__.__name__
                dependencies.context.pipeline_step = step_name

                logger.info('Starting pipeline step %d: %s', current_step, step_name)
                result = self.run(**dependencies.prepare_injection(self.run))
                logger.info('Finished pipeline step %d: %s', current_step, step_name)

                results.append(result)
                return result
            else:
                if current_step > len(results):
                    raise RuntimeError(
                        f'Checkpoint "{checkpoint_file}" did not contain enough stored results'
                    )
                return results[current_step - 1]

        return new_run_step

    # unwrap_pipeline_steps = _wrap_subclasses_init(PipelineStep, init_wrapper)
    unwrap_pipeline_steps = _wrap_subclasses_method(PipelineStep, '__run_step__', run_step_wrapper)
    logger.info('Initiating pipeline...')
    pipeline(**dependencies.prepare_injection(pipeline))
    logger.info('Pipeline finished!')
    unwrap_pipeline_steps()


def run_step[T](step: PipelineStep[T]) -> T:
    return step.__run_step__()


def checkpoint(name: str) -> None:
    """Alias for `run_step(Checkpoint(name))`"""
    Checkpoint(name).__run_step__()


def _get_pipeline_name() -> str:
    return Path(sys.argv[0]).name.split('.', 1)[0]


def _copy_pipeline_file_to_output(output_dir: Path) -> None:
    src_path = Path(sys.argv[0])
    dst_path = output_dir / src_path.name

    if src_path == dst_path or src_path.name == 'pytest':
        return

    shutil.copy2(src_path, dst_path)


def _find_config_file(dir_path: Path) -> Path | None:
    """Find a valid configuration file matching `config.[yaml|yml|json|toml]`"""
    config_files = [path for pattern in _CONFIG_GLOB_PATTERNS for path in dir_path.glob(pattern)]
    if config_files and config_files[0].exists():
        return config_files[0]

    return None


def _find_config_override_file(dir_path: Path) -> Path | None:
    """Find a valid configuration override file matching `config_override.[yaml|yml|json|toml]`"""
    config_files = [
        path for pattern in _CONFIG_OVERRIDE_GLOB_PATTERNS for path in dir_path.glob(pattern)
    ]
    if config_files and config_files[0].exists():
        return config_files[0]

    return None


def _find_checkpoint_file(name: str) -> Path:
    """Finds the checkpoint file in the checkpoint directory. If name is "latest",
    will look for the last modified file."""
    if name != 'latest':
        return _CHECKPOINTS_RELPATH / name

    # Check for empty dir
    if not _CHECKPOINTS_RELPATH.exists() or not any(_CHECKPOINTS_RELPATH.iterdir()):
        raise RuntimeError(
            'Could not find latest checkpoint, directory is empty or does not exist.'
        )

    # Find latest checkpoint
    return max(
        (path for path in _CHECKPOINTS_RELPATH.iterdir() if path.is_file()),
        key=lambda file: file.stat().st_mtime,
    )


def _copy_config_file_to_output(output_dir: Path, config_file: Path) -> None:
    """Copies the configuration file to :param:`output_dir` with file name
    `config.[yaml|yml|json|toml]`"""
    if not config_file.suffix in _CONFIG_EXTENSIONS:
        raise ValueError(
            f'Unsupported config file format "{config_file}", '
            f'supported extensions: {', '.join(_CONFIG_EXTENSIONS)}'
        )

    destination = output_dir / f'config{config_file.suffix}'
    if config_file != destination:
        shutil.copy(config_file, destination)


def _save_config_override_to_output(
    output_dir: Path, config_override: dict[str, Any], config_file: Path | None
) -> None:
    """Copies the configuration file to :param:`output_dir` with file name
    `config.[yaml|yml|json|toml]`"""
    if not config_file:
        destination = output_dir / 'config_override.yaml'
        save_config(config_override, destination)
        return

    if not config_file.suffix in _CONFIG_EXTENSIONS:
        raise ValueError(
            f'Unsupported config file format "{config_file}", '
            f'supported extensions: {', '.join(_CONFIG_EXTENSIONS)}'
        )

    destination = output_dir / f'config_override{config_file.suffix}'
    save_config(config_override, destination)


def _config_repr(config_overrides: dict[str, Any]) -> str:
    return '\n'.join([f'  {key}={value}' for key, value in config_overrides.items()])


def _all_subclasses[T](cls: Type[T]) -> list[Type[T]]:
    result: set[Type[T]] = set()
    for sub in cls.__subclasses__():
        if inspect.isabstract(sub):
            continue

        result.add(sub)
        result.update(_all_subclasses(sub))

    return list(result)


def _wrap_subclasses_method(
    cls: Type[Any], method_name: str, wrapper: Callable[..., Any]
) -> Callable[[], None]:
    original_methods: dict[Type[Any], Callable[..., Any]] = {}

    for cls in _all_subclasses(PipelineStep):
        original_method = getattr(cls, method_name)
        original_methods[cls] = original_method
        setattr(cls, method_name, wrapper(original_method))

    def set_original_methods() -> None:
        for cls, original_method in original_methods.items():
            setattr(cls, method_name, original_method)

    return set_original_methods


def _validate_dependencies(dependencies: DependencyManager) -> None:
    try:
        dependencies.validate_dependencies()
    except RuntimeError as e:
        warnings.warn(str(e), RuntimeWarning, stacklevel=3)

    for cls in _all_subclasses(PipelineStep):
        try:
            dependencies.throw_if_uninjectable(cls.run)
        except RuntimeError as e:
            warnings.warn(str(e), RuntimeWarning, stacklevel=3)
