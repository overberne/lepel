import pytest

from lepel.core import Context


def test_context_attr_and_item_access_are_consistent():
    ctx = Context()
    ctx["a"] = 1
    assert ctx.a == 1

    ctx.b = 2
    assert ctx["b"] == 2


def test_context_missing_key_raises_keyerror():
    context = Context()
    with pytest.raises(KeyError):
        _ = context["nope"]
    with pytest.raises(KeyError):
        _ = context.nope


def test_context_mapping_protocol_len_iter_contains():
    context = Context({"a": 1, "b": 2})
    assert len(context) == 2
    assert set(iter(context)) == {"a", "b"}
    assert "a" in context
    assert "c" not in context


def test_context_deletes_affect_internal_mapping():
    context = Context({"a": 1, "b": 2})
    del context["a"]
    assert "a" not in context

    del context.b
    assert "b" not in context


def test_context_dirty_flag_semantics():
    context = Context()
    assert context.is_dirty() is True  # ctor sets dirty

    context.clear_dirty()
    assert context.is_dirty() is False

    context.x = 1
    assert context.is_dirty() is True

    context.clear_dirty()
    context["y"] = 2
    assert context.is_dirty() is True


def test_context_state_roundtrip_marks_dirty():
    context = Context({"a": 1})
    context.clear_dirty()
    assert context.is_dirty() is False

    context.load_state_dict({"b": 2})
    assert context.is_dirty() is True
    assert context.b == 2
    assert "a" not in context

    state = context.state_dict()
    assert state == {"b": 2}
    assert isinstance(state, dict)
