"""Tests for plugin manager loading and manifest listing helpers."""

from __future__ import annotations

from types import ModuleType
from typing import Any

import pytest

from app.plugins.base import BasePlugin, PluginManifest
from app.plugins.manager import PluginManager


def _build_plugin_class(manifest_name: str, permissions: list[str]):
    """Create a minimal runtime plugin class for manager tests."""

    async def initialize(self) -> None:
        return None

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"inputs": inputs}

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name=manifest_name,
            version="1.0.0",
            description=f"{manifest_name} plugin",
            author="tests",
            permissions=permissions,
            inputs={},
            outputs={"ok": "boolean"},
        )

    return type(
        f"{manifest_name.replace('-', '_').title()}Plugin",
        (BasePlugin,),
        {
            "initialize": initialize,
            "execute": execute,
            "get_manifest": get_manifest,
        },
    )


def _plugin_module(plugin_class: type[BasePlugin]) -> ModuleType:
    module = ModuleType(f"test_{plugin_class.__name__.lower()}")
    module.Plugin = plugin_class
    return module


@pytest.mark.asyncio
async def test_load_plugins_from_directory_applies_config_by_module_name(
    tmp_path, monkeypatch
):
    (tmp_path / "alpha.py").write_text("# alpha", encoding="utf-8")
    (tmp_path / "beta.py").write_text("# beta", encoding="utf-8")

    modules = {
        "app.plugins.alpha": _plugin_module(
            _build_plugin_class("alpha-plugin", ["network.http"])
        ),
        "app.plugins.beta": _plugin_module(
            _build_plugin_class("beta-plugin", ["filesystem.read"])
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    loaded = await manager.load_plugins_from_directory(
        plugin_configs={"alpha": {"units": "imperial"}}
    )

    assert loaded == ["alpha-plugin", "beta-plugin"]
    assert manager.get_plugin("alpha-plugin").config == {"units": "imperial"}
    assert manager.get_plugin("beta-plugin").config == {}


@pytest.mark.asyncio
async def test_load_plugins_from_directory_prefers_full_module_path_config(
    tmp_path, monkeypatch
):
    (tmp_path / "gamma.py").write_text("# gamma", encoding="utf-8")

    modules = {
        "app.plugins.gamma": _plugin_module(
            _build_plugin_class("gamma-plugin", ["network.http"])
        )
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugins_from_directory(
        plugin_configs={
            "gamma": {"mode": "short-key"},
            "app.plugins.gamma": {"mode": "module-path-key"},
        }
    )

    assert manager.get_plugin("gamma-plugin").config == {"mode": "module-path-key"}


@pytest.mark.asyncio
async def test_list_plugins_filters_by_required_permissions(tmp_path, monkeypatch):
    (tmp_path / "http_plugin.py").write_text("# http", encoding="utf-8")
    (tmp_path / "local_plugin.py").write_text("# local", encoding="utf-8")

    modules = {
        "app.plugins.http_plugin": _plugin_module(
            _build_plugin_class("http-plugin", ["network.http", "filesystem.read"])
        ),
        "app.plugins.local_plugin": _plugin_module(
            _build_plugin_class("local-plugin", ["filesystem.read"])
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugins_from_directory()

    filtered = manager.list_plugins(required_permissions=["network.http"])

    assert [item["name"] for item in filtered] == ["http-plugin"]
