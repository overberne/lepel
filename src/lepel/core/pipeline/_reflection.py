import inspect
from typing import Any, Callable, Type

from lepel.core.pipeline.recipe_step import RecipeStep


def all_subclasses[T](cls: Type[T]) -> list[Type[T]]:
    result: set[Type[T]] = set()
    for sub in cls.__subclasses__():
        if inspect.isabstract(sub):
            continue

        result.add(sub)
        result.update(all_subclasses(sub))

    return list(result)


def wrap_subclasses_method(
    cls: Type[Any], method_name: str, wrapper: Callable[..., Any]
) -> Callable[[], None]:
    original_methods: dict[Type[Any], Callable[..., Any]] = {}

    for cls in all_subclasses(RecipeStep):
        original_method = getattr(cls, method_name)
        original_methods[cls] = original_method
        setattr(cls, method_name, wrapper(original_method))

    def set_original_methods() -> None:
        for cls, original_method in original_methods.items():
            setattr(cls, method_name, original_method)

    return set_original_methods
