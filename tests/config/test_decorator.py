import pytest

from lepel.config.decorator import config_setting
from lepel.config.validation import bind_config_values
from lepel.config.registry import all_registered


def test_decorator_registers_property_and_requires_return_annotation():
    # Valid usage with return annotation
    class C:  # pyright: ignore[reportUnusedClass]
        @config_setting
        def value(self) -> int: ...

    regs = all_registered()
    assert any(r.collection_name == 'C' and r.key == 'value' for r in regs)

    # Missing return annotation should raise TypeError at decoration time
    with pytest.warns(RuntimeWarning):

        class D:  # pyright: ignore[reportUnusedClass]
            @config_setting
            def missing(self): ...


def test_property_reads_from_bound_config():  # type: ignore
    class E:
        @config_setting
        def value(self) -> int: ...
    class F:
        @config_setting
        def value(self) -> int: ...

    bind_config_values(**{'value': 0, 'E': {'value': 123}})
    e = E()
    f = F()
    assert e.value == 123
    assert f.value == 0

    # Explicit name override
    class G:
        @config_setting(name='my_name')
        def value(self) -> int: ...

    bind_config_values(my_name=7)
    assert G().value == 7
