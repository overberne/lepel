from typing import Any

import pytest

from lepel.config.registry import ConfigProperty, register
from lepel.config.validation import (
    ConfigValidationError,
    resolve_config_value,
    ensure_required_config_values,
)


def test_resolve_precedence_and_key_error():
    cfg: dict[str, Any] = {
        'MyClass.value': 10,
        'value': 20,
        'MyClass': {
            'value': 30,
            'nested': 40,
        },
    }

    assert resolve_config_value(config=cfg, key='value', collection_name='MyClass') == 10
    assert resolve_config_value(config=cfg, key='value') == 20
    assert resolve_config_value(config=cfg, key='MyClass.nested') == 40
    assert resolve_config_value(config=cfg, key='nested', collection_name='MyClass') == 40

    with pytest.raises(KeyError):
        resolve_config_value(config={}, key='Nope')


def test_validate_config_type_mismatch_and_missing():
    # Register two properties
    register(ConfigProperty('a', 'C', int, lambda self: 1))  # type: ignore
    register(ConfigProperty('b_renamed', 'C', str, lambda self: 'x'))  # type: ignore

    cfg_good: dict[str, Any] = {'C.a': 1, 'b_renamed': 'ok'}
    # should not raise for good config
    ensure_required_config_values(cfg_good)

    cfg_bad = {'C.a': 'not-int'}
    with pytest.raises(ConfigValidationError) as excinfo:
        ensure_required_config_values(cfg_bad)

    msg = str(excinfo.value)
    assert 'Type mismatch for C.a' in msg or 'No config value for C.b' in msg
