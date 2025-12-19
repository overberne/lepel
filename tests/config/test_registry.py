from lepel.config.registry import (
    ConfigProperty,
    _REGISTRY,  # pyright: ignore[reportPrivateUsage]
    register,
    all_registered,
)


def test_register_and_all_registered_clearable():
    assert list(_REGISTRY) == []

    entry = ConfigProperty(
        key='x',
        collection_name='A',
        expected_type=int,
        fget=lambda self: 1,  # type: ignore
    )

    register(entry)

    regs = all_registered()
    assert len(regs) == 1
    assert regs[0] is entry
