from dataclasses import dataclass
from typing import Any, Callable, List


@dataclass(frozen=True)
class ConfigProperty:
    """Metadata for a configuration-backed property.

    Instances of this dataclass describe a single property on a class that
    can be populated from the global configuration. The registry stores
    these entries so configuration validation and value resolution can
    operate without importing concrete classes.

    Attributes
    ----------
    class_name:
        The name of the class that defines the property.
    prop_name:
        The attribute name used on the class.
    config_name:
        The name used in the configuration mapping. This may differ from
        ``prop_name`` when an explicit name override is provided.
    expected_type:
        The Python type expected for the configuration value, or ``None``
        when no type checking should be performed.
    fget:
        The original getter function used to create the property; kept for
        debugging and potential introspection.
    """

    key: str
    collection_name: str
    expected_type: type[Any] | None
    fget: Callable[..., Any]


_REGISTRY: List[ConfigProperty] = []


def register(entry: ConfigProperty) -> None:
    """Register a ``ConfigProperty`` entry in the global registry.

    This function appends ``entry`` to the module-level registry used by
    validation and resolution logic. It does not perform any uniqueness
    checks; callers are expected to avoid duplicate registrations.

    Parameters
    ----------
    entry:
        The ``ConfigProperty`` instance to register.
    """

    _REGISTRY.append(entry)


def all_registered() -> List[ConfigProperty]:
    """Return a shallow copy of all registered configuration entries.

    Returns a list copy so callers may mutate the returned sequence without
    affecting the internal registry.

    Returns
    -------
    List[ConfigProperty]
        The list of registered configuration property metadata objects.
    """

    return list(_REGISTRY)
