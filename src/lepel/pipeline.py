# pyright: reportPrivateUsage=false
from abc import ABC, abstractmethod
from logging import Logger, getLogger
from typing import Any, Callable, Protocol

from lepel.dependency_manager import DependencyManager


class PipelineStep(ABC):
    result: Any = None

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()


class AsyncPipelineStep(ABC):
    result: dict[str, Any] | None = None

    @abstractmethod
    async def arun(self, **kwargs: Any) -> None:
        raise NotImplementedError()


def run_pipeline(pipeline: Callable[..., Any], checkpoint: str | None = None) -> None:
    # TODO: For all implementations of pipeline step, replace run funcs
    # - When loading a save
    #   - Run up to save point with that given position
    #   - Need to get result from memory
    #     - Use a map of pipeline step to a list of results, this makes for loops also work
    #   - Only state that gets saved / loaded are config, context vars, dependencies

    # CHECKPOINT
    # if none: find latest in relative folder (if it exists)
    # if not none, find the checkpoint or throw

    # 1. Check dependencies in pipeline run functions
    # 2. Check dependencies of dependencies
    # 3. Run pipeline
    # 3a. If run with checkpoint, skip initializers
    pass


def create_checkpoint(name: str) -> None:
    """Creates a checkpoint from restorable dependencies, config and context vars"""
    # Maybe auto create checkpoints when changes are detected?
    # But how?
    # What changes?
    # - After each step compare state dicts? May be expensive
    # - Cannot capture all set_attrs because attr may be a reference with mutable data.
    pass


class Stateful(Protocol):
    def state_dict(self) -> dict[str, Any]: ...
    def load_state_dict(self, state_dict: dict[str, Any]) -> None: ...


class PipelineRunner:
    dependencies: DependencyManager
    _logger: Logger
    steps_started: int = 0

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        logger: Logger | None = None,
    ):
        self.dependencies = DependencyManager(config)
        self.dependencies.register_singleton(self)
        if Logger not in self.dependencies:
            self.dependencies.register(_pipeline_step_logger_factory)

        self._logger = logger or getLogger()

    def run(self, step: PipelineStep) -> None:
        self.steps_started += 1

        # TODO: Check whether a save point is set on the runner, then

        step_name = step.__class__.__name__
        self._logger.info('Starting pipeline step %d: %s', self.steps_started, step_name)

        self.dependencies.update_context_variables(pipeline_step=step_name)
        method = step.run
        kwargs = self.dependencies.prepare_injection(method)
        result = method(**kwargs)

        self._logger.info('Finished pipeline step %d: %s', self.steps_started, step_name)
        return result

    async def arun(self, step: AsyncPipelineStep) -> None:
        self.steps_started += 1
        step_name = step.__class__.__name__
        self._logger.info('Starting pipeline step %d: %s', self.steps_started, step_name)

        self.dependencies.update_context_variables(pipeline_step=step_name)
        method = step.arun
        kwargs = self.dependencies.prepare_injection(method)
        result = await method(**kwargs)

        self._logger.info('Finished pipeline step %d: %s', self.steps_started, step_name)
        return result


def _pipeline_step_logger_factory(pipeline_step: str) -> Logger:
    return getLogger(pipeline_step)


# Factory which allows users to pass a factory method which will have its args injected by the container


# Allows e.g. sets of learners, agents etc. to be created for each seed
class PersistentFactory:
    """Keeps track of the created objects in order of creation
    objects can also be created with a name.

    Pass the dependency manager to the persistent factories maybe?"""

    pass


class PersistentCollectionFactory:
    """Keeps track of collections of the created objects in order of creation of the collections
    collections can also be created with a name.

    Use PersitentFactory to"""

    pass


# TODO: Need to think about how objects are passed around,
# Do we have a single Learner for example?
# - An agent factory?
# - An agent repository/manager?
#   - Keeps instances under a certain name or collection
# - These repos could also handle DI via the container and settings like steprunner does
#   - Allow kwargs to be passed to get/create functions, but those + _resolve should fill all args.


# Use dynamic container, register config in it and use resolution from there instead of config
# Do better resolution so subclasses are also filled.

# Maybe remove this and just let user create an executor
# Allows us to check steps run methods for
# async def run_pipeline_async(pipeline: Callable[[Executor], None]) -> None:
#     pass
