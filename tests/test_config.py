import os

import pytest

from cookidoo_mcp.config import CookidooConfig, CookidooConfigStore, UnsafeConfigFileError


def test_config_store_writes_human_editable_yaml_owner_only(tmp_path):
    path = tmp_path / "config.yaml"
    store = CookidooConfigStore(path)

    store.save(
        CookidooConfig(
            country="ch",
            locale="de-CH",
            label="Switzerland - German",
            cookie_file="~/.cookidoo-recipes/cookies.json",
        )
    )

    text = path.read_text(encoding="utf-8")
    assert text.startswith("site:\n")
    assert "country: ch\n" in text
    assert "locale: de-CH\n" in text
    assert "label: Switzerland - German\n" in text
    assert "cookies:\n" in text
    assert "file: ~/.cookidoo-recipes/cookies.json\n" in text
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert store.load() == CookidooConfig(
        country="ch",
        locale="de-CH",
        label="Switzerland - German",
        cookie_file="~/.cookidoo-recipes/cookies.json",
    )


def test_config_store_rejects_group_readable_file(tmp_path):
    path = tmp_path / "config.yaml"
    store = CookidooConfigStore(path)
    store.save(
        CookidooConfig(
            country="de",
            locale="de-DE",
            label="Germany - German",
            cookie_file="~/.cookidoo-recipes/cookies.json",
        )
    )
    os.chmod(path, 0o640)

    with pytest.raises(UnsafeConfigFileError):
        store.load()
