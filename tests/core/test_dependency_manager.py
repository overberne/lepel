from typing import Any

import pytest

from lepel.core import DependencyManager


class ServiceA:
    def __init__(self) -> None:
        self.value = "a"


class ServiceB:
    def __init__(self, a: ServiceA) -> None:
        self.a = a


def test_dependency_manager_registers_itself_as_singleton():
    dependencies = DependencyManager()
    assert DependencyManager in dependencies
    assert dependencies.resolve(DependencyManager) is dependencies


def test_add_singleton_and_resolve_returns_same_instance():
    dependencies = DependencyManager()
    instance = ServiceA()
    dependencies.add_singleton(instance)

    assert ServiceA in dependencies
    assert dependencies.resolve(ServiceA) is instance
    assert dependencies.resolve(ServiceA) is instance


def test_add_transient_returns_new_instances():
    dependencies = DependencyManager()
    dependencies.add_transient(ServiceA)

    a1 = dependencies.resolve(ServiceA)
    a2 = dependencies.resolve(ServiceA)
    assert isinstance(a1, ServiceA)
    assert isinstance(a2, ServiceA)
    assert a1 is not a2


def test_transient_factory_with_injection():
    dependencies = DependencyManager()
    dependencies.add_transient(ServiceA)
    dependencies.add_transient(ServiceB)

    b = dependencies.resolve(ServiceB)
    assert isinstance(b, ServiceB)
    assert isinstance(b.a, ServiceA)


def test_prepare_injection_skips_varargs_varkwargs_and_self():
    dependencies = DependencyManager()
    dependencies.add_singleton(123)

    def fn(a: int, *args: Any, **kwargs: Any):
        return a

    kwargs = dependencies.prepare_injection(fn)
    assert kwargs == {"a": 123}


def test_resolve_uses_default_if_not_registered():
    dependencies = DependencyManager()

    def fn(x: int = 7):
        return x

    kwargs = dependencies.prepare_injection(fn)
    assert kwargs["x"] == 7


def test_resolve_precedence_methodclass_dot_name_then_name_then_type():
    dependencies = DependencyManager()
    dependencies.add_singleton(1, int, name="Bar.foo")
    dependencies.add_singleton(2, int, name="foo")
    dependencies.add_singleton(3, int)

    class Bar:
        def method(self, foo: int) -> int:
            return foo

    bar = Bar()
    kwargs = dependencies.prepare_injection(bar.method)
    assert kwargs["foo"] == 1

    def fn_name(foo: int) -> int:
        return foo

    kwargs2 = dependencies.prepare_injection(fn_name)
    # no method_class but matching name => uses name
    assert kwargs2["foo"] == 2

    def fn_no_name(bar: int) -> int:
        return bar

    kwargs3 = dependencies.prepare_injection(fn_no_name)
    # no method_class or matching name => falls back to type
    assert kwargs3["bar"] == 3


def test_add_transient_disallows_override_by_default():
    dependencies = DependencyManager()
    dependencies.add_transient(ServiceA)
    with pytest.raises(RuntimeError):
        dependencies.add_transient(ServiceA)


def test_add_transient_allows_override_when_flagged():
    dependencies = DependencyManager()
    dependencies.add_transient(ServiceA)
    dependencies.add_transient(lambda: ServiceA(), service_class=ServiceA, allow_override=True)
    assert isinstance(dependencies.resolve(ServiceA), ServiceA)


def test_validate_dependencies_raises_for_uninjectable_transients():
    dependencies = DependencyManager()

    class NeedsUnknown:
        def __init__(self, missing: str):
            self.missing = missing

    dependencies.add_transient(NeedsUnknown)
    with pytest.raises(RuntimeError):
        dependencies.validate()


def test_throw_if_uninjectable_ignores_params_with_defaults():
    dependencies = DependencyManager()

    def fn(x: int = 1, y: str = ''):
        return x, y

    # defaults => should not raise
    dependencies.throw_if_uninjectable(fn)
