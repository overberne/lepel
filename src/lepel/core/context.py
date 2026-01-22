from typing import Any, Iterator, MutableMapping


class Context(MutableMapping[str, Any]):
    """
    Lightweight attribute/dict-backed container for variables.

    The `Context` class provides a thin wrapper around a dictionary that
    allows accessing items as attributes and as mapping keys. It is
    intentionally simple: attribute access, item access, and assignment all
    delegate to an internal dictionary.

    Parameters
    ----------
    vars : dict[str, Any] | None, optional
        Initial mapping of names to values. If not provided, an empty
        dictionary is used.

    Attributes
    ----------
    _dict : dict[str, Any]
        Internal storage for the context variables. Users should treat this
        as private and prefer attribute/item access.

    Notes
    -----
    - Accessing a missing attribute or key raises a `KeyError`.
    - This class implements the mapping protocol and can be used like a
      standard mutable mapping.

    Examples
    --------
    >>> ctx = Context({'a': 1})
    >>> ctx.a
    1
    >>> ctx['b'] = 2
    >>> ctx.b
    2
    """

    _dict: dict[str, Any]

    def __init__(self, vars: dict[str, Any] | None = None) -> None:
        """
        Initialize the `Context`.

        Parameters
        ----------
        vars : dict[str, Any] | None, optional
            Optional initial mapping to populate the context.
        """
        # Use object.__setattr__ to avoid recursion into __setattr__.
        object.__setattr__(self, '_dict', vars or {})

    def __getattribute__(self, name: str) -> Any:
        # Direct access to the internal storage should bypass attribute
        # lookup logic to avoid recursion.
        if name == '_dict':
            return object.__getattribute__(self, '_dict')

        # If the attribute exists on the object/class, return it. This
        # preserves access to methods and special attributes. Otherwise
        # fall back to returning values from the internal mapping.
        try:
            return object.__getattribute__(self, name)
        except AttributeError:
            return self._dict[name]

    def __getitem__(self, name: str) -> Any:
        return self._dict[name]

    def __setattr__(self, name: str, value: Any) -> None:
        self._dict[name] = value

    def __setitem__(self, name: str, value: Any) -> None:
        self._dict[name] = value

    def __iter__(self) -> Iterator[str]:
        return iter(self._dict)

    def __len__(self) -> int:
        return len(self._dict)

    def __delitem__(self, name: str) -> None:
        del self._dict[name]

    def __delattr__(self, name: str) -> None:
        del self._dict[name]
