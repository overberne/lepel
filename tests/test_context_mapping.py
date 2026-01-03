import pytest

from lepel.context import Context


def test_basic_get_set_item_and_attribute():
    ctx = Context()
    ctx['x'] = 1
    assert ctx['x'] == 1
    assert ctx.x == 1

    ctx.y = 2
    assert ctx['y'] == 2
    assert ctx.y == 2


def test_len_and_iter_and_contains():
    ctx = Context({'a': 1, 'b': 2})
    assert len(ctx) == 2
    keys = set(iter(ctx))
    assert keys == {'a', 'b'}
    assert 'a' in ctx
    assert 'c' not in ctx


def test_update_and_setdefault():
    ctx = Context({'a': 1})
    ctx.update({'b': 2, 'c': 3})
    assert ctx.b == 2
    assert ctx.c == 3

    v = ctx.setdefault('d', 4)
    assert v == 4
    assert ctx.d == 4

    # setdefault on existing key
    v2 = ctx.setdefault('a', 10)
    assert v2 == 1
    assert ctx.a == 1


def test_pop_and_popitem_and_clear():
    ctx = Context({'a': 1, 'b': 2})
    v = ctx.pop('a')
    assert v == 1
    assert 'a' not in ctx

    key, val = ctx.popitem()
    assert key == 'b'
    assert val == 2
    assert len(ctx) == 0

    ctx['x'] = 10
    ctx.clear()
    assert len(ctx) == 0


def test_del_and_delete_item():
    ctx = Context({'a': 1, 'b': 2})
    del ctx['a']
    assert 'a' not in ctx

    # attribute deletion should remove mapping entry
    del ctx['b']
    assert 'b' not in ctx


def test_del_and_delete_attr():
    ctx = Context({'a': 1, 'b': 2})
    del ctx.a
    assert 'a' not in ctx

    # attribute deletion should remove mapping entry
    del ctx.b
    assert 'b' not in ctx


def test_views_keys_items_values():
    ctx = Context({'a': 1, 'b': 2})
    k = set(ctx.keys())
    assert k == {'a', 'b'}
    v = set(ctx.values())
    assert v == {1, 2}
    items = set(ctx.items())
    assert items == {('a', 1), ('b', 2)}


def test_missing_key_raises_keyerror():
    ctx = Context()
    with pytest.raises(KeyError):
        _ = ctx['nope']

    with pytest.raises(KeyError):
        _ = ctx.nope


def test_repr_and_dir_preserve_methods():
    ctx = Context({'a': 1})
    # repr should not raise
    r = repr(ctx)
    assert 'Context' in r or r.startswith('<')
    # dir should include methods like 'keys'
    assert 'keys' in dir(ctx)
