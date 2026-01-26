from abc import ABC, abstractmethod
from typing import Any


class PipelineStep[T = None](ABC):
    """
    Abstract base class for pipeline steps.

    Subclasses should implement the ``run`` method. Pipeline steps are instantiated
    during pipeline execution and their constructor is wrapped by the pipeline to
    orchestrate ordering, checkpoint handling, and dependency injection.
    """

    def __run_step__(self) -> T:
        raise NotImplementedError('This should be wrapped/replaced by the run_pipeline() function.')

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> T:
        """
        Execute the pipeline step.

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
