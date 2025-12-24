from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def reset_config_and_registry() -> Iterator[None]:
    """Reset module-level state in the config modules before each test."""
    # reload modules to get fresh module-level variables
    import lepel.config_.registry as registry
    import lepel.config_.validation as validation

    # Clear the registry list in registry module
    if hasattr(registry, '_REGISTRY'):
        registry._REGISTRY.clear()  # pyright: ignore[reportPrivateUsage]

    # Reset validation context
    if hasattr(validation, '_CONFIG_CONTEXT'):
        validation._CONFIG_CONTEXT.clear()  # pyright: ignore[reportPrivateUsage]

    yield

    # no teardown necessary beyond module resets
