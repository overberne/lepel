# pyright: reportPrivateUsage=false
from typing import Callable, Type, overload


@overload
def inject[T](func: Type[T]) -> T: ...
@overload
def inject[T](func: Callable[[], T]) -> T: ...


def inject[T](func: Type[T] | Callable[[], T]) -> T:
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

    from lepel.core.pipeline.pipeline import _active_dependency_manager

    if _active_dependency_manager is None:
        raise RuntimeError(
            f'No active DependencyManager to resolve dependencies for {func.__name__}.'
            ' This constructor/function can only be called from a run_recipe() context.'
        )
    return func(**_active_dependency_manager.prepare_injection(func))
