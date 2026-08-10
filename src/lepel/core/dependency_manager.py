# pyright: reportPrivateUsage=false
import inspect
import types
from collections.abc import Callable
from typing import (
    Any,
    TypeIs,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

# Denotes whether a factory houses a singleton
_SINGLETON_ATTR = '__is_singleton__'
_ORIGINAL_FACTORY_ATTR = '__original_factory__'
_NoneType = type(None)
_ProviderKey = tuple[type, str | None]


def _is_provider_key(value: object) -> TypeIs[_ProviderKey]:
    if not isinstance(value, tuple):
        return False
    if len(value) != 2:  # pyright: ignore[reportUnknownArgumentType]
        return False

    cls, name = value  # pyright: ignore[reportUnknownVariableType]
    return isinstance(cls, type) and (isinstance(name, str) or name is None)


class DependencyManager:
    """
    A dependency manager to handle injection and resolution.

    Dependency resolution order:
    1. Type + MethodClassName.Name (if provided)
    2. Type + Name
    3. Type

    Notes
    -----
    - Supports `dependency_injector.providers` as factory methods.
    """

    def __init__(self) -> None:
        self._providers: dict[_ProviderKey, Callable[..., Any]] = {}
        self.add_singleton(self)

    def __contains__(self, dependency: Any) -> bool:
        if dependency is None:
            return False

        if _is_provider_key(dependency):
            return dependency in self._providers

        return (dependency, None) in self._providers

    def prepare_injection(
        self,
        method: Callable[..., Any] | type[Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Get injectable function arguments from the dependency container.
        """
        method_class = None
        if isinstance(method, type):
            method_class = method
            method = method.__init__
        elif hasattr(method, '__self__'):
            method_class = method.__self__.__class__  # pyright: ignore[reportFunctionMemberAccess]

        sig = inspect.signature(method)
        try:
            hints = get_type_hints(method)
        except (TypeError, ValueError):
            hints = {}

        bind_args = args
        parameters = tuple(sig.parameters.values())

        if (
            parameters
            and parameters[0].name == 'self'
            and getattr(method, '__self__', None) is None
        ):
            bind_args = (None, *args)

        bound = sig.bind_partial(*bind_args, **kwargs)
        injections = dict(kwargs)

        for name, param in sig.parameters.items():
            if (
                name == 'self'
                or name in bound.arguments
                or param.kind == param.VAR_POSITIONAL  # *args
                or param.kind == param.VAR_KEYWORD  # **kwargs
            ):
                continue

            annotation = hints.get(name, inspect._empty)
            annotation = _strip_optional(annotation)
            injections[name] = self.resolve(
                annotation,
                name,
                method_class=method_class,
                default=param.default,
            )

        return injections

    def wire[T](self, factory: Callable[..., T] | type[T]) -> Callable[[], T]:
        if isinstance(factory, type):
            factory = cast(type[T], factory)
            sig = inspect.signature(factory.__init__)
            if len(sig.parameters) == 1:
                setattr(factory, _ORIGINAL_FACTORY_ATTR, factory.__init__)
                return factory
        else:
            sig = inspect.signature(factory)
            if len(sig.parameters) == 0:
                setattr(factory, _ORIGINAL_FACTORY_ATTR, factory)
                return factory

        def wired_factory() -> T:
            return factory(**self.prepare_injection(factory))

        setattr(wired_factory, _ORIGINAL_FACTORY_ATTR, factory)
        return wired_factory

    @overload
    def add_transient[T](
        self,
        factory: Callable[..., T] | type[Any],
        *,
        name: str | None = None,
        allow_override: bool = True,
    ) -> None:
        """Register a dependency in the container. Any arguments in the factory
        function will be injected by the dependency manager.

        NOTE: Factories which return without type annotations (e.g., labmdas)
        should pass their type through the `service_class` argument.

        NOTE: If the factory contains unresolvable arguments, the dependency
        manager will raise an error on resolution.

        Parameters
        ----------
        factory : Callable[..., T] | type[Any]
            Factory function for the dependency.
        name : str | None
            The name to associate with the dependency of this type, by default None
        allow_override : bool
            When false, raises a RuntimeError when overriding a registered type,
            by default True

        Raises
        ------
        RuntimeError
            When `allow_override` is false and `T` overrides a registered type.
        """

    @overload
    def add_transient[T](
        self,
        factory: Callable[..., Any] | type[Any],
        service_class: type[T],
        *,
        name: str | None = None,
        allow_override: bool = True,
    ) -> None:
        """Register a dependency in the container under the alias of service class,
        which must be a base class or a matching protocol. Any arguments in the factory
        function will be injected by the dependency manager.

        NOTE: If the factory contains unresolvable arguments, the dependency
        manager will raise an error on resolution.

        Parameters
        ----------
        factory : Callable[..., T] | type[Any]
            Factory function for the dependency.
        service_class : type[Any]
            The alias under which to register the dependency.
        name : str | None
            The name to associate with the dependency of this type, by default None
        allow_override : bool
            When false, raises a RuntimeError when overriding a registered type,
            by default True

        Raises
        ------
        RuntimeError
            When `allow_override` is false and `T` overrides a registered type.
        """
        ...

    def add_transient[T](
        self,
        factory: Callable[..., Any] | type[Any],
        service_class: type[T] | None = None,
        *,
        name: str | None = None,
        allow_override: bool = True,
    ) -> None:
        if service_class is None:
            try:
                if isinstance(factory, type):  # Class
                    service_class = factory
                else:  # Normal callable
                    service_class = _get_callable_return_type(factory)
            except RuntimeError:
                # Fallback for third party dependency providers/factories
                # like the `dependency-injector` package.
                service_class = _try_third_party_di_type(factory)

        if service_class is None:
            raise RuntimeError('Cannot get dependency type from factory.')

        provider_key = (service_class, name)
        if not allow_override and provider_key in self._providers:
            raise RuntimeError(
                f'Dependency with type "{service_class.__name__}" already registered.'
            )

        self._providers[provider_key] = self.wire(factory)

    @overload
    def add_singleton(
        self,
        instance: Any,
        *,
        name: str | None = None,
        allow_override: bool = True,
    ) -> None:
        """Register a dependency in the container.

        NOTE: Instances of a generic class should pass the generic class
        through the `service_class` argument.

        Parameters
        ----------
        instance : Any
            The singleton instance of the dependency.
        name : str | None
            The name to associate with the dependency of this type, by default None
        allow_override : bool
            When false, raises a RuntimeError when overriding a registered type,
            by default True

        Raises
        ------
        RuntimeError
            When `allow_override` is false and `T` overrides a registered type.
        """

    @overload
    def add_singleton[T](
        self,
        instance: Any,
        service_class: type[T],
        *,
        name: str | None = None,
        allow_override: bool = True,
    ) -> None:
        """Register a dependency in the container under the alias of service class,
        which must be a base class or a matching protocol.

        Parameters
        ----------
        instance : Any
            The singleton instance of the dependency.
        service_class : type[Any]
            The alias under which to register the dependency.
        name : str | None
            The name to associate with the dependency of this type, by default None
        allow_override : bool
            When false, raises a RuntimeError when overriding a registered type,
            by default True

        Raises
        ------
        RuntimeError
            When `allow_override` is false and `T` overrides a registered type.
        """
        ...

    def add_singleton[T](
        self,
        instance: T,
        service_class: type[T] | None = None,
        *,
        name: str | None = None,
        allow_override: bool = True,
    ) -> None:
        def factory():
            return instance

        if service_class is None:
            if isinstance(instance, list):
                service_class = _infer_list_type(instance)  # pyright: ignore[reportUnknownArgumentType]
            else:
                service_class = instance.__class__

        setattr(factory, _SINGLETON_ATTR, True)
        self.add_transient(
            factory,
            service_class=service_class,
            name=name,
            allow_override=allow_override,
        )

    def resolve[T](
        self,
        annotation: type[T],
        name: str | None = None,
        *,
        method_class: type[Any] | None = None,
        default: T = inspect.Parameter.empty,
    ) -> T:
        """Resolve a dependency by type and/or name.

        Resolution order:
        1. Type + MethodClassName.Name
        2. Type + Name
        3. Type
        4. Name

        Parameters
        ----------
        annotation : type[T]
            The type of the dependency.
        name : str | None
            The name of the dependency, by default None.
        method_class: type[Any] | None
            the class owning the method, if dependency comes from a method signature.
        default : T
            A fallback value to use if the dependency is not found,
            by default `inspect.Paramter.empty`

        Returns
        -------
        T
            The resolved value.

        Raises
        ------
        LookupError
            When the dependency is not found.
        """
        provider = None
        if name and method_class:
            provider = self._providers.get(
                (annotation, f'{method_class.__name__}.{name}')
            )
        if provider is None and name:
            provider = self._providers.get((annotation, name))
        if provider is None:
            provider = self._providers.get((annotation, None))
        if provider is None:
            key = f'{method_class.__name__}.{name}' if method_class else name
            provider = next(
                (v for k, v in self._providers.items() if k[1] == key),
                None,
            )

        if provider is not None:
            return provider()

        if default != inspect.Parameter.empty:
            return default

        if name is None:
            raise LookupError(f'Cannot resolve dependency for type "{annotation}"')
        elif annotation == inspect.Parameter.empty:
            raise LookupError(f'Cannot resolve dependency for name "{name}"')
        else:
            raise LookupError(
                f'Cannot resolve dependency for type "{annotation}" and name "{name}"'
            )

    def throw_if_uninjectable(self, method: Callable[..., Any] | type[Any]):
        """
        Throw an error if any dependencies in the method signature are not injectable.

        Parameters
        ----------
        method : Callable[..., Any] | type[Any]
            The method or class to check for injectable dependencies.

        Raises
        ------
        RuntimeError
            When a dependency cannot be resolved.
        """
        sig = inspect.signature(method)
        try:
            hints = get_type_hints(method)
        except (TypeError, ValueError):
            hints = {}

        method_class = None
        if hasattr(method, '__self__'):
            method_class = method.__self__.__class__  # type: ignore

        for name, param in sig.parameters.items():
            if (
                name == 'self'
                or param.kind == param.VAR_POSITIONAL  # *args
                or param.kind == param.VAR_KEYWORD  # **kwargs
                or param.default is not inspect.Parameter.empty
            ):
                continue

            annotation = hints.get(name, inspect._empty)
            annotation = _strip_optional(annotation)
            if not self._can_resolve(annotation, name, method_class):
                name = f'{method.__name__}.{name}'
                if method_class:
                    name = f'{method_class}.{name}'
                raise RuntimeError(f'Unable to resolve dependency "{name}"')

    def validate(self) -> None:
        """
        Validate that all factories' dependencies are injectable.
        """
        for factory in self._providers.values():
            if hasattr(factory, _SINGLETON_ATTR):
                continue
            orig_factory: Callable[..., Any] = getattr(factory, _ORIGINAL_FACTORY_ATTR)
            self.throw_if_uninjectable(orig_factory)

    def _can_resolve(
        self,
        annotation: type[Any],
        name: str | None = None,
        method_class: type[Any] | None = None,
        default: Any = inspect.Parameter.empty,
    ) -> bool:
        return (
            (annotation, name) in self._providers
            or (annotation, None) in self._providers
            or (
                method_class
                and (annotation, f'{method_class.__name__}.{name}') in self._providers
            )
            or (default != inspect.Parameter.empty)
        )


def _try_third_party_di_type(factory: Callable[..., Any]) -> type[Any] | None:
    return (
        _get_dependency_injector_provider_type(factory)
        # or _get_dependency_injector_provider_type(factory)
        # or _get_dependency_injector_provider_type(factory)
    )


def _get_dependency_injector_provider_type(
    provider: Callable[..., Any],
) -> type[Any] | None:
    """For the `dependency-injector` library."""
    provides = getattr(provider, 'provides', None)

    if provides is not None:
        # Case: providers.Object(instance)
        if not isinstance(provides, type) and not callable(provides):
            return type(provides)  # pyright: ignore[reportUnknownVariableType]

        # Case: providers.Factory(Class) / Singleton(Class)
        if isinstance(provides, type):
            return provides

        # Case: providers.Callable(callable)
        if callable(provides):
            return _get_callable_return_type(provides)

    raise RuntimeError('Cannot get dependency type from provider.')


def _get_callable_return_type(func: Callable[..., Any]) -> type[Any] | None:
    """
    Extract return type from a callable using type annotations.
    """
    try:
        hints = get_type_hints(func)  # type: ignore
        return _strip_optional(hints.get('return'))
    except (TypeError, ValueError) as ex:
        raise RuntimeError('Cannot get dependency type from factory.') from ex


def _strip_optional(annotation: Any) -> Any:
    """
    If annotation is Optional[T] / T | None, return T.
    If annotation is a union with None (e.g. A | B | None),
    return the union without None.
    Otherwise return annotation unchanged.
    """
    origin = get_origin(annotation)
    if origin not in (types.UnionType, Union):  # T | U syntax
        return annotation

    type_arguments = tuple(arg for arg in get_args(annotation) if arg is not _NoneType)
    if len(type_arguments) == 0:
        return _NoneType  # was just None (rare)
    if len(type_arguments) == 1:
        return type_arguments[0]  # Optional[T] -> T

    # Rebuild a union without None, T | ... | None -> T | ...
    out = type_arguments[0]
    for arg in type_arguments[1:]:
        out = out | arg

    return out


def _infer_list_type(value: list[Any]) -> type[list[Any]]:
    if not value:
        raise TypeError('Cannot infer element type from empty list')

    element_types: set[type] = {type(item) for item in value}

    if len(element_types) != 1:
        raise TypeError(
            f'Cannot infer one element type from mixed list: {element_types}'
        )

    element_type = next(iter(element_types))
    return list[element_type]
