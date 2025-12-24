from typing import Any, Mapping
from types import MappingProxyType

from lepel.config_.registry import all_registered

_CONFIG_CONTEXT: dict[str, Any] = {}


class ConfigValidationError(Exception):
    """Raised when configuration validation fails.

    This exception is raised by :func:`validate_config` when one or more
    registered configuration properties are missing from the provided
    mapping or have a value of the wrong type.
    """


def bind_config_values(**kwargs: Any) -> None:
    """Bind a configuration mapping for later property resolution.

    The provided ``config`` mapping becomes the global configuration
    context that :func:`resolve_config_value` and properties decorated with
    ``config_setting`` will read from. This function replaces any
    previously bound configuration.

    Parameters
    ----------
    config:
        A mapping of configuration keys to values. Keys are plain strings
        and are matched using the precedence rules implemented by
        :func:`resolve_config_value`.
    """
    _CONFIG_CONTEXT.update(kwargs)  # pyright: ignore[reportConstantRedefinition]


def get_config() -> Mapping[str, Any]:
    """Return the currently bound configuration mapping.

    This accessor exposes the configuration bound by :func:`bind_config`.
    It is primarily used by the property decorator implementation to
    retrieve the active config at runtime.

    Raises
    ------
    RuntimeError
        If :func:`bind_config` has not been called.
    """
    return MappingProxyType(_CONFIG_CONTEXT)


def resolve_config_value(
    *, config: Mapping[str, Any] | None = None, key: str, collection_name: str | None = None
) -> Any:
    """Resolve a configuration value using string-based precedence.

    When looking up a property value the function tries keys in this
    order (first match wins):

    - ``{Class}.{explicit_name}`` (if an explicit name was provided)
    - ``{explicit_name}``
    - ``{Class}.{prop_name}``
    - ``{prop_name}``

    Parameters
    ----------
    config:
        The mapping to search for configuration values.
    key:
        The attribute name of the property on the class.
    collection_name:
        The name of the class defining the property (used to build
        class-scoped keys).
    explicit_name:
        An optional explicit configuration name provided when the
        property was declared; when present it is checked before the
        implicit property name.

    Returns
    -------
    Any
        The first matching value found in ``config``.

    Raises
    ------
    KeyError
        If none of the candidate keys are present in ``config``.
    RuntimeError
        If :func:`bind_config` has not been called.
    """
    if config is None:
        config = get_config()

    if collection_name:
        try:
            flat_key = f'{collection_name}.{key}'
            return resolve_config_value(config=config, key=flat_key)
        except KeyError:
            pass

    # Flat keys > nested keys
    if key in config:
        return config[key]

    # Handle nested keys
    parts = key.split('.', maxsplit=1)
    if len(parts) == 1:
        if parts[0] in config:
            return config[parts[0]]
    else:
        collection, restkey = parts
        if collection in config:
            return resolve_config_value(config=config[collection], key=restkey)

    raise KeyError(f'No config value for {key}')


def ensure_required_config_values(config: Mapping[str, Any] | None = None) -> None:
    """Validate a configuration mapping against registered properties.

    For each registered :class:`~lepel.config.registry.ConfigProperty` the
    function attempts to resolve a value from ``config`` using the same
    precedence rules as :func:`resolve_config_value`. If a value is
    missing or does not match the registered ``expected_type``, an error
    message is accumulated. After checking all entries, a
    :class:`ConfigValidationError` is raised when any errors were found.

    Parameters
    ----------
    config:
        The mapping to validate.

    Raises
    ------
    ConfigValidationError
        When required configuration keys are missing or when a
        type mismatch is detected for any registered property.
    RuntimeError
        If :func:`bind_config` has not been called.
    """
    if config is None:
        config = get_config()

    errors: list[str] = []

    for entry in all_registered():
        try:
            value = resolve_config_value(
                config=config,
                key=entry.key,
                collection_name=entry.collection_name,
            )
        except KeyError as exc:
            errors.append(str(exc))
            continue

        if entry.expected_type and not isinstance(value, entry.expected_type):
            errors.append(
                f'Type mismatch for {entry.collection_name}.{entry.key}: '
                f'expected {entry.expected_type.__name__}, '
                f'got {type(value).__name__}'
            )

    if errors:
        raise ConfigValidationError('Configuration validation failed:\n' + '\n'.join(errors))
