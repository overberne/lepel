# pyright: reportPrivateUsage=false
import inspect
from typing import Any, Callable, Type, get_type_hints, overload

from dependency_injector import providers


class DependencyManager:
    """Dependency manager. Injects based on type and name in function signatures.
    Supports `dependency_injector.providers` as factory methods.
    """

    _context_vars: dict[str, Any]
    _config: dict[str, Any]
    type_providers: dict[type, Callable[..., Any]]

    def __init__(
        self,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._config = config or {}
        self._context_vars = {'config': self._config}
        self._type_providers: dict[type, Callable[..., Any]] = {}

        self.register_singleton(self)

    # def __contains__(self, dependency: str | Type[Any] | None) -> bool:
    def __contains__(self, dependency: Any) -> bool:
        if dependency is None:
            return False

        # Name based resolution
        if isinstance(dependency, str):
            return dependency in self._config or dependency in self._context_vars

        return dependency in self._type_providers

    def clear_context_variables(self) -> None:
        self._context_vars = {}

    def update_context_variables(self, **kwargs: Any) -> None:
        self._context_vars.update(kwargs)

    def prepare_injection(self, method: Callable[..., Any]) -> dict[str, Any]:
        """Get injectable function arguments from container and config"""
        if isinstance(method, providers.Provider):
            return {}

        sig = inspect.signature(method)
        hints = get_type_hints(method)

        kwargs: dict[str, Any] = {}
        for name, _ in sig.parameters.items():
            if name == "self":
                continue

            annotation = hints.get(name, inspect._empty)
            kwargs[name] = self.resolve(name, annotation)

        return kwargs

    def wire_class[T](self, class_: Type[T]) -> Callable[[], T]:
        sig = inspect.signature(class_.__init__)
        if len(sig.parameters) == 1:
            return class_

        def _wired_class() -> T:
            return class_(**self.prepare_injection(class_.__init__))

        return _wired_class

    def wire_factory[T](self, factory: Callable[..., T]) -> Callable[[], T]:
        sig = inspect.signature(factory)
        if len(sig.parameters) == 0:
            return factory

        def _wired_factory() -> T:
            return factory(**self.prepare_injection(factory))

        return _wired_factory

    @overload
    def register[T](self, factory: Callable[..., T], *, allow_override: bool = False) -> None:
        """Register a dependency in the container. Any arguments in the factory
        function will be injected by the dependency manager.

        NOTE: Factories which return a generic class should explicitly annotate
        their return type (e.g., lambdas), or pass it through the `service_class` argument.

        NOTE: If the factory contains unresolvable arguments, the dependency
        manager will raise an error on resolution.

        Parameters
        ----------
        factory : Callable[..., T]
            Factory function for the dependency.
        allow_override : bool
            When false, raises a RuntimeError when overriding a registered type,
            by default False

        Raises
        ------
        RuntimeError
            When `allow_override` is false and `T` overrides a registered type.
        """

    @overload
    def register[T](
        self,
        factory: Callable[..., Any],
        service_class: Type[T],
        *,
        allow_override: bool = False,
    ) -> None:
        """Register a dependency in the container under the alias of service class,
        which must be a base class or a matching protocol. Any arguments in the factory
        function will be injected by the dependency manager.

        NOTE: If the factory contains unresolvable arguments, the dependency
        manager will raise an error on resolution.

        Parameters
        ----------
        factory : Callable[..., T]
            Factory function for the dependency.
        service_class : Type[Any]
            The alias under which to register the dependency.
        allow_override : bool
            When false, raises a RuntimeError when overriding a registered type,
            by default False

        Raises
        ------
        RuntimeError
            When `allow_override` is false and `T` overrides a registered type.
        """
        ...

    def register[T](
        self,
        factory: Callable[..., Any],
        service_class: Type[T] | None = None,
        *,
        allow_override: bool = False,
    ) -> None:
        if service_class is None:
            try:
                if isinstance(factory, type):  # Class
                    service_class = factory
                else:  # Normal callable
                    service_class = _get_callable_return_type(factory)
            except:
                # Fallback for third party dependency providers/factories like `dependency-injector`.
                service_class = _try_third_party_di_type(factory)

        if service_class is None:
            raise RuntimeError('Cannot get dependency type from factory.')

        if not allow_override and service_class in self._type_providers:
            raise RuntimeError(
                f'Dependency with type "{service_class.__name__}" already registered.'
            )

        if isinstance(factory, type):
            self._type_providers[service_class] = self.wire_class(factory)
        else:
            self._type_providers[service_class] = self.wire_factory(factory)

    @overload
    def register_singleton(self, instance: Any, *, allow_override: bool = False) -> None:
        """Register a dependency in the container.

        NOTE: Instances of a generic class should pass the generic class
        through the `service_class` argument.

        Parameters
        ----------
        instance : Any
            The singleton instance of the dependency.
        allow_override : bool
            When false, raises a RuntimeError when overriding a registered type,
            by default False

        Raises
        ------
        RuntimeError
            When `allow_override` is false and `T` overrides a registered type.
        """

    @overload
    def register_singleton[T](
        self,
        instance: Any,
        service_class: Type[T],
        *,
        allow_override: bool = False,
    ) -> None:
        """Register a dependency in the container under the alias of service class,
        which must be a base class or a matching protocol.

        Parameters
        ----------
        instance : Any
            The singleton instance of the dependency.
        service_class : Type[Any]
            The alias under which to register the dependency.
        allow_override : bool
            When false, raises a RuntimeError when overriding a registered type,
            by default False

        Raises
        ------
        RuntimeError
            When `allow_override` is false and `T` overrides a registered type.
        """
        ...

    def register_singleton[T](
        self,
        instance: Any,
        service_class: Type[T] | None = None,
        *,
        allow_override: bool = False,
    ) -> None:
        def factory() -> T:
            return instance

        self.register(factory, service_class=service_class, allow_override=allow_override)  # type: ignore

    @overload
    def resolve(self, dependency: str) -> Any:
        """Resolve a dependency by name.

        Resolution order:
        1. Context variables
        2. Config

        Parameters
        ----------
        dependency : str
            The name of the dependency.

        Returns
        -------
        Any
            The resolved value or raises LookupError if not found.

        Raises
        ------
        LookupError
            When the dependency is not found,
        """

    @overload
    def resolve[T](self, dependency: str, annotation: Type[T]) -> T:
        """Resolve a dependency by type and/or name.

        Resolution order:
        1. Container (type only)
        1. Context variables
        2. Config

        Parameters
        ----------
        dependency : str
            The name of the dependency.
        annotation : Type[T]
            The type of the dependency.

        Returns
        -------
        T
            The resolved value or raises LookupError if not found.

        Raises
        ------
        LookupError
            When the dependency is not found,
        """

    @overload
    def resolve[T](self, dependency: Type[T]) -> T:
        """Resolve a dependency by type.

        Parameters
        ----------
        dependency : Type[T]
            The type of the dependency.

        Returns
        -------
        T
            The resolved value or raises LookupError if not found.

        Raises
        ------
        LookupError
            When the dependency is not found,
        """

    def resolve(self, dependency: str | Type[Any], annotation: Type[Any] = inspect._empty) -> Any:
        # Resolve by type (annotation) from container
        if annotation and annotation is not inspect._empty:
            provider = self._type_providers.get(annotation)
            if provider is not None:
                return provider()

        # Resolve by name
        val: Any = None
        if dependency in self._context_vars:
            val = self._context_vars[dependency]
        elif dependency in self._config:
            val = self._config[dependency]

        if val and _same_types(val, annotation):
            return val

        raise LookupError(f"Cannot resolve dependency for parameter '{dependency}'")


def _same_types(a: Any, b: Type[Any]) -> bool:
    return b is inspect._empty or type(a) == b


def _try_third_party_di_type(factory: Callable[..., Any]) -> Type[Any] | None:
    return (
        _get_dependency_injector_provider_type(factory)
        # or _get_dependency_injector_provider_type(factory)
        # or _get_dependency_injector_provider_type(factory)
    )


def _get_dependency_injector_provider_type(provider: Callable[..., Any]) -> Type[Any] | None:
    """For the `dependency-injector` library."""
    provides = getattr(provider, "provides", None)

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


def _get_callable_return_type(func: Callable[..., Any]) -> Type[Any] | None:
    """
    Extract return type from a callable using type annotations.
    """
    try:
        hints = get_type_hints(func)  # type: ignore
        return hints.get('return')
    except (TypeError, ValueError) as ex:
        raise RuntimeError('Cannot get dependency type from factory.') from ex
