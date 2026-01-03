from typing import Any, Protocol

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
    dm = DependencyManager()
    dm.register(Service)
    dm.register(Service, allow_override=True)

    with pytest.raises(RuntimeError):
        dm.register(Service, allow_override=False)


def test_inject_name_mismatch_raises():
    dm = DependencyManager()

    def fn(foo):  # type: ignore
        return foo  # type: ignore

    with pytest.raises(LookupError):
        dm.prepare_injection(fn)  # type: ignore


def test_inject_type_mismatch_raises():
    dm = DependencyManager()
    dm.context.foo = 123

    def fn(foo: str):
        return foo

    with pytest.raises(LookupError):
        dm.prepare_injection(fn)


def test_inject_from_context_variables():
    dm = DependencyManager()
    dm.context.foo = 123

    def fn(foo):  # type: ignore
        return foo  # type: ignore

    kwargs = dm.prepare_injection(fn)  # type: ignore
    assert 'foo' in kwargs
    assert kwargs['foo'] == 123

    def fn(foo: int):
        return foo

    kwargs = dm.prepare_injection(fn)
    assert 'foo' in kwargs
    assert kwargs['foo'] == 123


def test_inject_from_config():
    dm = DependencyManager(
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

    kwargs = dm.prepare_injection(fn)  # type: ignore
    assert kwargs['foo'] == 42

    class Bar:
        def foo(self, baz: int) -> int:
            return baz

    bar = Bar()
    kwargs = dm.prepare_injection(bar.foo)
    assert kwargs['baz'] == 1

    class Baz:
        def foo(self, baz: int) -> int:
            return baz

    baz = Baz()
    kwargs = dm.prepare_injection(baz.foo)
    assert kwargs['baz'] == 3


def test_inject_default():
    dm = DependencyManager()

    def fn(foo: str = 'bar'):
        return foo

    kwargs = dm.prepare_injection(fn)
    assert 'foo' in kwargs
    foo = kwargs['foo']
    assert foo == 'bar'


def test_inject_by_type():
    dm = DependencyManager()
    dm.register(lambda: Service(value='ok'), service_class=Service)

    def fn(svc: Service):
        return svc

    kwargs = dm.prepare_injection(fn)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, Service)
    assert svc.value == 'ok'


def test_inject_by_type_with_class_register():
    dm = DependencyManager(config={'value': 'ok'})
    dm.register(Service)

    def fn(svc: Service):
        return svc

    kwargs = dm.prepare_injection(fn)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, Service)
    assert svc.value == 'ok'


def test_inject_by_protocol():
    dm = DependencyManager()
    dm.register(lambda: Service(value='ok'), service_class=FooProtocol)

    def fn(svc: FooProtocol):
        return svc

    kwargs = dm.prepare_injection(fn)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, Service)
    assert svc.value == 'ok'


def test_inject_by_subclass():
    dm = DependencyManager()
    dm.register(lambda: SubService(value='ok'), service_class=Service)

    def fn(svc: Service):
        return svc

    kwargs = dm.prepare_injection(fn)
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

    dm = DependencyManager()
    dm.register(factory)
    dm.register_singleton(GenericService(0.0), GenericService[float])
    dm.register(lambda: GenericService[bool](False), GenericService[bool])

    kwargs = dm.prepare_injection(fn_int)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, GenericService)
    assert svc.foo == 0  # type: ignore

    kwargs = dm.prepare_injection(fn_float)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, GenericService)
    assert svc.foo == 0.0  # type: ignore

    kwargs = dm.prepare_injection(fn_bool)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, GenericService)
    assert svc.foo == False  # type: ignore

    with pytest.raises(LookupError):
        kwargs = dm.prepare_injection(fn_str)


def test_inject_by_type_nested_dependency():
    dm = DependencyManager()

    class WrapperService:
        def __init__(self, svc: Service):
            self.svc = svc

    def fn(svc: WrapperService):
        return svc

    dm.register(WrapperService)
    dm.register(lambda: Service('ok'), Service)

    kwargs = dm.prepare_injection(fn)
    assert 'svc' in kwargs
    svc = kwargs['svc']
    assert isinstance(svc, WrapperService)
    assert svc.svc.value == 'ok'


def test_resolution_precedence():
    dm = DependencyManager(config={'foo': 'from-config'})

    def fn(foo):  # type: ignore
        return foo  # type: ignore

    kwargs = dm.prepare_injection(fn)  # type: ignore
    assert kwargs['foo'] == 'from-config'

    # Context variable should override container and config
    dm.context.foo = 'from-context'

    kwargs = dm.prepare_injection(fn)  # type: ignore
    assert kwargs['foo'] == 'from-context'

    def fn(foo: Service):  # type: ignore
        return foo  # type: ignore

    dm.register(lambda: Service('ok'), Service)
    kwargs = dm.prepare_injection(fn)  # type: ignore
    assert isinstance(kwargs['foo'], Service)


def test_statefulness():
    class StatefulService:
        def __init__(self, foo: int):
            self.foo = foo

        def state_dict(self) -> dict[str, Any]:
            return {'foo': self.foo}

        def load_state_dict(self, state_dict: dict[str, Any]) -> None:
            self.foo = state_dict['foo']

    dm = DependencyManager({'bar': 'baz'})
    dm.register_singleton(StatefulService(0))
    dm.context.baz = False

    def foo(service: StatefulService, bar: str, baz: bool):
        return service, bar, baz

    state_dict = dm.state_dict()
    dm_assert = DependencyManager()
    dm_assert.register_singleton(StatefulService(1))
    dm_assert.load_state_dict(state_dict)

    service, bar, baz = foo(**dm_assert.prepare_injection(foo))
    assert service.foo == 0
    assert bar == 'baz'
    assert baz == False


try:
    from dependency_injector import providers

    def test_inject_by_type_with_provider():
        dm = DependencyManager()
        dm.register(providers.Factory(Service, value='ok'))

        def fn(svc: Service):
            return svc

        kwargs = dm.prepare_injection(fn)
        assert 'svc' in kwargs
        svc = kwargs['svc']
        assert isinstance(svc, Service)
        assert svc.value == 'ok'

except ImportError:
    pass
