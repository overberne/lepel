from pathlib import Path

import pytest

from lepel.pipeline._config import load_config, save_config


def test_load_save_json_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    save_config({"a": 1, "b": "x"}, path)
    assert load_config(path) == {"a": 1, "b": "x"}


def test_load_raises_if_not_mapping(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text('["not", "a", "mapping"]', encoding="utf-8")
    with pytest.raises(RuntimeError):
        load_config(path)


@pytest.mark.skipif(
    pytest.importorskip("yaml", reason="PyYAML not installed") is None, reason="skip"
)
def test_load_save_yaml_roundtrip(tmp_path: Path):
    path = tmp_path / "config.yaml"
    save_config({"a": 1}, path)
    assert load_config(path) == {"a": 1}


@pytest.mark.skipif(pytest.importorskip("toml", reason="toml not installed") is None, reason="skip")
def test_toml_optional(tmp_path: Path):
    path = tmp_path / "config.toml"
    save_config({"a": 1}, path)
    assert load_config(path) == {"a": 1}
