from typing import Protocol

import pytest

from lepel import DependencyManager


class FooProtocol(Protocol):
    def foo(self, bar: str) -> str: ...


class Service:
    def __init__(self, value: str):
        self.value = value

    def foo(self, bar: str) -> str:
        return 'baz'


class SubService(Service):
    pass


def test_raise_on_override():
    dependencies = DependencyManager()
    dependencies.add_transient(Service)
    dependencies.add_transient(Service, allow_override=True)

    with pytest.raises(RuntimeError):
        dependencies.add_transient(Service, allow_override=False)


def test_inject_name_mismatch_raises():
    dependencies = DependencyManager()

    def fn(foo):  # type: ignore
        return foo  # type: ignore

    with pytest.raises(LookupError):
        dependencies.prepare_injection(fn)  # type: ignore


def test_inject_type_mismatch_raises():
    dependencies = DependencyManager()
    dependencies.context.foo = 123

    def fn(foo: str):
        return foo

    with pytest.raises(LookupError):
        dependencies.prepare_injection(fn)


def test_inject_from_context_variables():
    dependencies = DependencyManager()
    dependencies.context.foo = 123

    def fn(foo):  # type: ignore
        return foo  # type: ignore

    kwargs = dependencies.prepare_injection(fn)  # type: ignore
    assert 'foo' in kwargs
    assert kwargs['foo'] == 123

    def fn(foo: int):
        return foo

    kwargs = dependencies.prepare_injection(fn)
    assert 'foo' in kwargs
    assert kwargs['foo'] == 123


def test_inject_from_config():
    dependencies = DependencyManager(
        config={
            'foo': 42,
            'baz': 0,
            'Bar': {'baz': 1},
            'Baz': {'baz': 2},
            'Baz.baz': 3,
        }
    )

    def fn(foo):  # type: ignore
        return foo  # type: ignore

    kwargs = dependencies.prepare_injection(fn)  # type: ignore
    assert kwargs['foo'] == 42

    class Bar:
        def foo(self, baz: int) -> int:
            return baz

    bar = Bar()
    kwargs = dependencies.prepare_injection(bar.foo)
    assert kwargs['baz'] == 1

    class Baz:
        def foo(self, baz: int) -> int:
            return baz

    baz = Baz()
    kwargs = dependencies.prepare_injection(baz.foo)
    assert kwargs['baz'] == 3


def test_inject_default():
    dependencies = DependencyManager()

    def fn(foo: str = 'bar'):
        return foo

    kwargs = dependencies.prepare_injection(fn)
    assert 'foo' in kwargs
    foo = kwargs['foo']
    assert foo == 'bar'


def test_inject_by_type():
    dependencies = DependencyManager()
    dependencies.add_transient(lambda: Service(value='ok'), service_class=Service)

    def fn(svc: Service):
        return svc

    kwargs = dependencies.prepare_injection(fn)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, Service)
    assert svc.value == 'ok'


def test_inject_by_type_with_class_register():
    dependencies = DependencyManager(config={'value': 'ok'})
    dependencies.add_transient(Service)

    def fn(svc: Service):
        return svc

    kwargs = dependencies.prepare_injection(fn)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, Service)
    assert svc.value == 'ok'


def test_inject_by_protocol():
    dependencies = DependencyManager()
    dependencies.add_transient(lambda: Service(value='ok'), service_class=FooProtocol)

    def fn(svc: FooProtocol):
        return svc

    kwargs = dependencies.prepare_injection(fn)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, Service)
    assert svc.value == 'ok'


def test_inject_by_subclass():
    dependencies = DependencyManager()
    dependencies.add_transient(lambda: SubService(value='ok'), service_class=Service)

    def fn(svc: Service):
        return svc

    kwargs = dependencies.prepare_injection(fn)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, Service)
    assert svc.value == 'ok'


def test_inject_by_generic_type():
    class GenericService[T]:
        def __init__(self, foo: T) -> None:
            self.foo = foo

    def factory() -> GenericService[int]:
        return GenericService(0)

    def fn_int(svc: GenericService[int]):
        return svc

    def fn_float(svc: GenericService[float]):
        return svc

    def fn_bool(svc: GenericService[bool]):
        return svc

    def fn_str(svc: GenericService[str]):
        return svc

    dependencies = DependencyManager()
    dependencies.add_transient(factory)
    dependencies.add_singleton(GenericService(0.0), GenericService[float])
    dependencies.add_transient(lambda: GenericService[bool](False), GenericService[bool])

    kwargs = dependencies.prepare_injection(fn_int)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, GenericService)
    assert svc.foo == 0  # type: ignore

    kwargs = dependencies.prepare_injection(fn_float)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, GenericService)
    assert svc.foo == 0.0  # type: ignore

    kwargs = dependencies.prepare_injection(fn_bool)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, GenericService)
    assert svc.foo == False  # type: ignore

    with pytest.raises(LookupError):
        kwargs = dependencies.prepare_injection(fn_str)


def test_inject_by_type_nested_dependency():
    dependencies = DependencyManager()

    class WrapperService:
        def __init__(self, svc: Service):
            self.svc = svc

    def fn(svc: WrapperService):
        return svc

    dependencies.add_transient(WrapperService)
    dependencies.add_transient(lambda: Service('ok'), Service)

    kwargs = dependencies.prepare_injection(fn)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, WrapperService)
    assert svc.svc.value == 'ok'


def test_resolution_precedence():
    dependencies = DependencyManager(config={'foo': 'from-config'})

    def fn(foo):  # type: ignore
        return foo  # type: ignore

    kwargs = dependencies.prepare_injection(fn)  # type: ignore
    assert kwargs['foo'] == 'from-config'

    # Context variable should override container and config
    dependencies.context.foo = 'from-context'

    kwargs = dependencies.prepare_injection(fn)  # type: ignore
    assert kwargs['foo'] == 'from-context'

    def fn(foo: Service):  # type: ignore
        return foo  # type: ignore

    dependencies.add_transient(lambda: Service('ok'), Service)
    kwargs = dependencies.prepare_injection(fn)  # type: ignore
    assert isinstance(kwargs['foo'], Service)


try:
    from dependency_injector import providers

    def test_inject_by_type_with_provider():
        dependencies = DependencyManager()
        dependencies.add_transient(providers.Factory(Service, value='ok'))

        def fn(svc: Service):
            return svc

        kwargs = dependencies.prepare_injection(fn)
        assert 'svc' in kwargs
        svc = kwargs['svc']
        assert isinstance(svc, Service)
        assert svc.value == 'ok'

except ImportError:
    pass
