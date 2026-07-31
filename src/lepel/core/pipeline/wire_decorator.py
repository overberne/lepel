# pyright: reportPrivateUsage=false
from functools import wraps
from typing import Callable, Type


def wire[T](cls: Type[T]) -> Callable[[], T]:
    """
    Wraps a class, injecting all arguments via :class:`DependencyManager`.

    Class decorator that replaces the class with a zero-argument
    constructor function. All `__init__` arguments are expected to be
    provided via injection.

    Notes
    -----
    Constructors created via this decorator can only be called within
    a `run_recipe()` context where there is an active DependencyManager.
    """

    @wraps(cls)
    def constructor() -> T:
        from lepel.core.pipeline.pipeline import _active_dependency_manager

        if _active_dependency_manager is None:
            raise RuntimeError(
                f'No active DependencyManager to resolve dependencies for {cls.__name__}.'
                ' This constructor can only be called within a run_recipe() context.'
            )
        return cls(**_active_dependency_manager.prepare_injection(cls))

    return constructor
