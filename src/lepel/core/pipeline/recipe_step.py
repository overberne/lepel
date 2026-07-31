from abc import ABC, abstractmethod
from typing import Any


class RecipeStep[T = None](ABC):
    """
    Abstract base class for recipe steps.

    Subclasses should implement the ``run`` method. Recipe steps are instantiated
    during recipe execution and their constructor is wrapped by the recipe to
    orchestrate ordering, checkpoint handling, and dependency injection.
    """

    def __run_step__(self) -> T:
        raise NotImplementedError('This should be wrapped/replaced by the run_recipe() function.')

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> T:
        """
        Execute the recipe step.

        Implementations of this method perform the work for a single recipe
        step. When ``run_recipe`` is executing, dependencies are prepared and
        injected automatically into ``run``. Common injectable arguments include
        ``output_dir`` (Path), ``recipe_step`` (str) and ``context`` (a
        :class:`~lepel.context.Context`).

        Returns
        -------
        T
            Steps may return a value; they are expected to have side effects
            such as saving data to ``output_dir`` or updating the
            state of stateful objects.
        """
        raise NotImplementedError()
