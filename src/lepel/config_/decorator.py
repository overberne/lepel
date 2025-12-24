from functools import wraps
from typing import Any, Callable, overload, get_type_hints
import warnings

from lepel.config_.registry import ConfigProperty, register
from lepel.config_.validation import resolve_config_value


class TypedProperty[T, Owner](property):
    def __init__(
        self,
        fget: Callable[[Owner], T],
        fset: Callable[[Owner, T], None] | None = None,
        fdel: Callable[[Owner], None] | None = None,
        doc: str | None = None,
    ) -> None:
        self._fget = fget
        self._fset = fset
        self._fdel = fdel
        self.__doc__ = doc

    # Descriptor protocol
    @overload
    def __get__(self, instance: None, owner: type[Owner]) -> 'TypedProperty[T, Owner]': ...
    @overload
    def __get__(self, instance: Owner, owner: type[Owner] | None = None) -> T: ...

    def __get__(
        self, instance: Owner | None, owner: type[Owner] | None = None
    ) -> T | 'TypedProperty[T, Owner]':
        if instance is None:
            return self
        return self._fget(instance)

    def __set__(self, instance: Owner, value: T) -> None:
        if self._fset is None:
            raise AttributeError('can\'t set attribute')
        self._fset(instance, value)

    def __delete__(self, instance: Owner) -> None:
        if self._fdel is None:
            raise AttributeError('can\'t delete attribute')
        self._fdel(instance)

    # Fluent decorators
    def getter(self, fget: Callable[[Owner], T]) -> 'TypedProperty[T, Owner]':
        return TypedProperty(fget, self._fset, self._fdel, self.__doc__)

    def setter(self, fset: Callable[[Owner, T], None]) -> 'TypedProperty[T, Owner]':
        '''Return a new ``TypedProperty`` with the provided setter.'''

        return TypedProperty(self._fget, fset, self._fdel, self.__doc__)

    def deleter(self, fdel: Callable[[Owner], None]) -> 'TypedProperty[T, Owner]':
        return TypedProperty(self._fget, self._fset, fdel, self.__doc__)


class Property[T](TypedProperty[T, Any]):
    pass


@overload
def config_setting[T](name: str | None = None) -> Callable[[Callable[..., T]], Property[T]]: ...
@overload
def config_setting[T](name: Callable[..., T]) -> Property[T]: ...


def config_setting[T](
    name: str | Callable[..., T] | None = None,
) -> Callable[[Callable[..., T]], Property[T]] | Property[T]:
    '''Decorator for configuration-backed properties.

    Resolution is string-based and relies only on class names.

    Parameters
    ----------
    name : str | None
        Explicit configuration key name to use instead of the
        property name. When omitted the property name is used., by default None

    Returns
    -------
    Callable[[Callable[..., T]], Property[T]]
        A decorator which converts the given function into a
        configuration-backed ``Property``.

    Raises
    ------
    TypeError
        _description_
    RuntimeError
        _description_
    '''

    explicit_name = None if callable(name) else name

    def decorator(func: Callable[..., T]) -> Property[T]:
        qual_parts = func.__qualname__.split('.')
        if len(qual_parts) >= 2:
            class_name: str = qual_parts[-2]
        else:
            class_name: str = qual_parts[0]
        prop_name: str = func.__name__

        type_hints = get_type_hints(func)
        expected_type: type[Any] | None = None
        if 'return' in type_hints:
            expected_type = type_hints['return']
        else:
            warnings.warn(
                f'Property "{class_name}.{prop_name}" cannot be type checked because it does not declare a return type',
                RuntimeWarning,
            )

        @wraps(func)
        def wrapper(self: Any) -> T:
            class_name = type(self).__name__
            value = resolve_config_value(
                key=explicit_name or prop_name,
                collection_name=class_name,
            )
            return value

        # Registration occurs at decoration time
        register(
            ConfigProperty(
                key=explicit_name or prop_name,
                collection_name=class_name,
                expected_type=expected_type,
                fget=func,
            )
        )

        return Property(wrapper)

    if callable(name):
        func = name
        return decorator(func)

    return decorator
