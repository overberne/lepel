# pyright: reportPrivateUsage=false
import inspect
from typing import (
    Any,
    Callable,
    OrderedDict,
    Protocol,
    Type,
    cast,
    get_type_hints,
    overload,
    runtime_checkable,
)

from lepel.context import Context

# Denotes whether a factory houses a singleton
_SINGLETON_ATTR = '__is_singleton__'
_ORIGINAL_FACTORY_ATTR = '__original_factory__'


@runtime_checkable
class Stateful(Protocol):
    def state_dict(self) -> dict[str, Any]: ...
    def load_state_dict(self, state_dict: dict[str, Any]) -> None: ...


class DependencyManager:
    """Dependency manager. Injects based on type and name in function signatures.
    Supports `dependency_injector.providers` as factory methods.


    Dependency resolution order:
    1. Type
    2. Context variables, by name (and type if annotated)
    3. Config, by name (and type if annotated)

    When resolving configuration values, will also look for:
    - `config[f'{method_class.__name__}.{dependency}']`
    - `config[method_class.__name__][dependency]`
    """

    _context: Context
    _config: dict[str, Any]
    type_providers: OrderedDict[type, Callable[..., Any]]

    def __init__(
        self,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._config = config or {}
        self._context = Context()
        self._type_providers: OrderedDict[type, Callable[..., Any]] = OrderedDict()

        self.register_singleton(self)
        self.register_singleton(self._context)

    def __contains__(self, dependency: Any) -> bool:
        if dependency is None:
            return False

        # Name based resolution
        if isinstance(dependency, str):
            return dependency in self._config or dependency in self._context

        return dependency in self._type_providers

    def clear_context_variables(self) -> None:
        self._context = Context()
        self.register_singleton(self._context, allow_override=True)

    def update_context_variables(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            self._context[key] = value

    def prepare_injection(self, method: Callable[..., Any] | Type[Any]) -> dict[str, Any]:
        """Get injectable function arguments from container and config"""
        if isinstance(method, type):
            method = method.__init__

        sig = inspect.signature(method)
        try:
            hints = get_type_hints(method)
        except (TypeError, ValueError):
            hints = {}

        method_class = None
        if hasattr(method, '__self__'):
            method_class = method.__self__.__class__  # pyright: ignore[reportFunctionMemberAccess]

        kwargs: dict[str, Any] = {}
        for name, param in sig.parameters.items():
            if (
                name == 'self'
                or param.kind == param.VAR_POSITIONAL  # *args
                or param.kind == param.VAR_KEYWORD  # **kwargs
            ):
                continue

            annotation = hints.get(name, inspect._empty)
            kwargs[name] = self.resolve(
                name,
                annotation,
                method_class=method_class,  # pyright: ignore[reportArgumentType]
                default=param.default,
            )

        return kwargs

    def wire[T](self, factory: Callable[..., T] | Type[T]) -> Callable[[], T]:
        if isinstance(factory, type):
            factory = cast(Type[T], factory)
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
    def register[T](
        self, factory: Callable[..., T] | Type[Any], *, allow_override: bool = False
    ) -> None:
        """Register a dependency in the container. Any arguments in the factory
        function will be injected by the dependency manager.

        NOTE: Factories which return without type annotations (e.g., labmdas)
        should pass their type through the `service_class` argument.

        NOTE: If the factory contains unresolvable arguments, the dependency
        manager will raise an error on resolution.

        Parameters
        ----------
        factory : Callable[..., T] | Type[Any]
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
        factory: Callable[..., Any] | Type[Any],
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
        factory : Callable[..., T] | Type[Any]
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
        factory: Callable[..., Any] | Type[Any],
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

        self._type_providers[service_class] = self.wire(factory)

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
        instance: T,
        service_class: Type[T] | None = None,
        *,
        allow_override: bool = False,
    ) -> None:
        def factory():
            return instance

        setattr(factory, _SINGLETON_ATTR, True)
        self.register(
            factory,
            service_class=service_class or instance.__class__,
            allow_override=allow_override,
        )

    @overload
    def resolve(self, dependency: str, *, default: Any = inspect.Parameter.empty) -> Any:
        """Resolve a dependency by name.

        Resolution order:
        1. Context variables (name only)
        2. Config (name only)

        Parameters
        ----------
        dependency : str
            The name of the dependency.
        default : Any
            A fallback value to use if the dependency is not found,
            by default `inspect.Paramter.empty`

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
    def resolve(
        self,
        dependency: str,
        *,
        method_class: Type[Any],
        default: Any = inspect.Parameter.empty,
    ) -> Any:
        """Resolve a dependency by name.

        Resolution order:
        1. Context variables (name only)
        2. Config (name only)

        When resolving configuration values, will also look for:
        - `config[f'{method_class.__name__}.{dependency}']`
        - `config[method_class.__name__][dependency]`

        Parameters
        ----------
        dependency : str
            The name of the dependency.
        method_class: Type[Any] | None
            the class owning the method, if dependency comes from a method signature.
        default : Any
            A fallback value to use if the dependency is not found,
            by default `inspect.Paramter.empty`

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
    def resolve[T](
        self,
        dependency: str,
        annotation: Type[T],
        *,
        default: T = inspect.Parameter.empty,
    ) -> T:
        """Resolve a dependency by type and/or name.

        Resolution order:
        1. Container (type only)
        2. Context variables
        3. Config

        Parameters
        ----------
        dependency : str
            The name of the dependency.
        annotation : Type[T]
            The type of the dependency.
        default : T
            A fallback value to use if the dependency is not found,
            by default `inspect.Paramter.empty`

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
    def resolve[T](
        self,
        dependency: str,
        annotation: Type[T],
        *,
        method_class: Type[Any],
        default: T = inspect.Parameter.empty,
    ) -> T:
        """Resolve a dependency by type and/or name.

        Resolution order:
        1. Type
        2. Context variables
        3. Config

        When resolving configuration values, will also look for:
        - `config[f'{method_class.__name__}.{dependency}']`
        - `config[method_class.__name__][dependency]`

        Parameters
        ----------
        dependency : str
            The name of the dependency.
        annotation : Type[T]
            The type of the dependency.
        method_class: Type[Any] | None
            the class owning the method, if dependency comes from a method signature.
        default : T
            A fallback value to use if the dependency is not found,
            by default `inspect.Paramter.empty`

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
    def resolve[T](self, dependency: Type[T], *, default: T = inspect.Parameter.empty) -> T:
        """Resolve a dependency by type.

        Parameters
        ----------
        dependency : Type[T]
            The type of the dependency.
        default : T
            A fallback value to use if the dependency is not found,
            by default `inspect.Paramter.empty`

        Returns
        -------
        T
            The resolved value or raises LookupError if not found.

        Raises
        ------
        LookupError
            When the dependency is not found,
        """

    def resolve(
        self,
        dependency: str | Type[Any],
        annotation: Type[Any] = inspect._empty,
        *,
        method_class: Type[Any] | None = None,
        default: Any = inspect.Parameter.empty,
    ) -> Any:
        # Resolve by type (annotation) from container
        if annotation and annotation is not inspect._empty:
            provider = self._type_providers.get(annotation)
            if provider is not None:
                return provider()

        # Resolve by name
        if isinstance(dependency, str):
            val: Any = None
            if dependency in self._context:
                val = self._context[dependency]
            else:
                val = self._resolve_from_config(dependency, annotation, method_class)

            if val is not None and _same_types(val, annotation):
                return val

        if default != inspect.Parameter.empty:
            return default

        raise LookupError(f'Cannot resolve dependency for parameter "{dependency}"')

    def throw_if_uninjectable(self, method: Callable[..., Any] | Type[Any]):
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
            if not self._can_resolve(name, annotation, method_class):
                name = f'{method.__name__}.{name}'
                if method_class:
                    name = f'{method_class}.{name}'
                raise RuntimeError(f'Unable to resolve dependency "{name}"')

    def validate_dependencies(self) -> None:
        """Validates that all dependencies in factory signatures
        are present in the dependency manager."""
        for factory in self._transients.values():
            orig_factory: Callable[..., Any] = getattr(factory, _ORIGINAL_FACTORY_ATTR)
            self.throw_if_uninjectable(orig_factory)

    def state_dict(self) -> dict[str, Any]:
        # Only for singletons, can be a list because _type_providers is ordered.
        state_dicts: list[dict[str, Any]] = [
            instance.state_dict()
            for cls, instance in self._singletons.items()
            if issubclass(cls, Stateful) and cls is not DependencyManager
        ]
        return {
            'state_dicts': state_dicts,
            'config': self._config,
            'context': self._context._dict,
        }

    def load_state_dict(self, state_dict: dict[str, Any]) -> None:
        # Only for singletons, can be a list because _type_providers is ordered.
        stateful_singletons: list[Stateful] = [
            instance
            for cls, instance in self._singletons.items()
            if issubclass(cls, Stateful) and cls is not DependencyManager
        ]
        # Can zip because singletons are an ordered dict
        for instance, dict_ in zip(stateful_singletons, state_dict.get('state_dicts', [])):
            instance.load_state_dict(dict_)

        self._config = state_dict.get('config', {})
        self._context = Context(state_dict.get('context', {}))
        self.register_singleton(self._context, allow_override=True)

    def _resolve_from_config(
        self,
        dependency: str,
        annotation: Type[Any] | None,
        method_class: Type[Any] | None,
    ) -> Any | None:
        # Resolve nested values first, giving preference to the true class over the alias (annotation)
        if method_class:
            class_name = method_class.__name__
            flat_name = f'{class_name}.{dependency}'
            if flat_name in self._config:
                return self._config[flat_name]
            elif class_name in self._config and dependency in self._config[class_name]:
                return self._config[class_name][dependency]

        if annotation:
            class_name = annotation.__name__
            flat_name = f'{class_name}.{dependency}'
            if flat_name in self._config:
                return self._config[flat_name]
            elif class_name in self._config and dependency in self._config[class_name]:
                return self._config[class_name][dependency]

        if dependency in self._config:
            return self._config[dependency]

        return None

    def _can_resolve(
        self,
        dependency: str | Type[Any],
        annotation: Type[Any] = inspect._empty,
        method_class: Type[Any] | None = None,
    ) -> bool:
        # Resolve by type (annotation) from container
        if annotation and annotation is not inspect._empty:
            provider = self._type_providers.get(annotation)
            if provider is not None:
                return True

        # Resolve by name
        if isinstance(dependency, str):
            val: Any = None
            if dependency in self._context:
                val = self._context[dependency]
            else:
                val = self._resolve_from_config(dependency, annotation, method_class)

            return val is not None and _same_types(val, annotation)

        return False

    @property
    def context(self) -> Context:
        return self._context

    @property
    def _singletons(self) -> dict[Type[Any], Any]:
        singletons: OrderedDict[Type[Any], Any] = OrderedDict()

        for cls, factory in self._type_providers.items():
            if hasattr(factory, _SINGLETON_ATTR):
                singletons[cls] = factory()

        return singletons

    @property
    def _transients(self) -> dict[Type[Any], Callable[..., Any]]:
        return {
            cls: factory
            for cls, factory in self._type_providers.items()
            if not hasattr(factory, _SINGLETON_ATTR)
        }


def _same_types(a: Any, b: Type[Any]) -> bool:
    return b is inspect._empty or type(a) == b or issubclass(a.__class__, b)


def _try_third_party_di_type(factory: Callable[..., Any]) -> Type[Any] | None:
    return (
        _get_dependency_injector_provider_type(factory)
        # or _get_dependency_injector_provider_type(factory)
        # or _get_dependency_injector_provider_type(factory)
    )


def _get_dependency_injector_provider_type(provider: Callable[..., Any]) -> Type[Any] | None:
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


def _get_callable_return_type(func: Callable[..., Any]) -> Type[Any] | None:
    """
    Extract return type from a callable using type annotations.
    """
    try:
        hints = get_type_hints(func)  # type: ignore
        return hints.get('return')
    except (TypeError, ValueError) as ex:
        raise RuntimeError('Cannot get dependency type from factory.') from ex
