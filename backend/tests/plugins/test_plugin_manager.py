"""Tests for plugin manager loading and manifest listing helpers."""

from __future__ import annotations

from types import ModuleType
from typing import Any

import pytest

from app.plugins.base import BasePlugin, PluginManifest
from app.plugins.manager import PluginManager


def _build_plugin_class(
    manifest_name: str,
    permissions: list[str],
    lifecycle: dict[str, int] | None = None,
):
    """Create a minimal runtime plugin class for manager tests."""

    async def initialize(self) -> None:
        if lifecycle is not None:
            lifecycle["initialized"] = lifecycle.get("initialized", 0) + 1

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"inputs": inputs}

    async def cleanup(self) -> None:
        if lifecycle is not None:
            lifecycle["cleaned"] = lifecycle.get("cleaned", 0) + 1

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
            "cleanup": cleanup,
            "get_manifest": get_manifest,
        },
    )


def _plugin_module(module_name: str, plugin_class: type[BasePlugin]) -> ModuleType:
    module = ModuleType(module_name)
    plugin_class.__module__ = module_name
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
            "app.plugins.alpha",
            _build_plugin_class("alpha-plugin", ["network.http"]),
        ),
        "app.plugins.beta": _plugin_module(
            "app.plugins.beta",
            _build_plugin_class("beta-plugin", ["filesystem.read"]),
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
            "app.plugins.gamma",
            _build_plugin_class("gamma-plugin", ["network.http"]),
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
async def test_load_plugins_from_directory_respects_include_allowlist(
    tmp_path, monkeypatch
):
    (tmp_path / "alpha.py").write_text("# alpha", encoding="utf-8")
    (tmp_path / "beta.py").write_text("# beta", encoding="utf-8")

    modules = {
        "app.plugins.alpha": _plugin_module(
            "app.plugins.alpha",
            _build_plugin_class("alpha-plugin", ["network.http"]),
        ),
        "app.plugins.beta": _plugin_module(
            "app.plugins.beta",
            _build_plugin_class("beta-plugin", ["filesystem.read"]),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    loaded = await manager.load_plugins_from_directory(include_plugins=["beta.py"])

    assert loaded == ["beta-plugin"]
    assert manager.get_plugin("alpha-plugin") is None
    assert manager.get_plugin("beta-plugin") is not None


@pytest.mark.asyncio
async def test_load_plugins_from_directory_respects_exclude_denylist(
    tmp_path, monkeypatch
):
    (tmp_path / "alpha.py").write_text("# alpha", encoding="utf-8")
    (tmp_path / "beta.py").write_text("# beta", encoding="utf-8")

    modules = {
        "app.plugins.alpha": _plugin_module(
            "app.plugins.alpha",
            _build_plugin_class("alpha-plugin", ["network.http"]),
        ),
        "app.plugins.beta": _plugin_module(
            "app.plugins.beta",
            _build_plugin_class("beta-plugin", ["filesystem.read"]),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    loaded = await manager.load_plugins_from_directory(
        exclude_plugins=["app.plugins.beta"]
    )

    assert loaded == ["alpha-plugin"]
    assert manager.get_plugin("alpha-plugin") is not None
    assert manager.get_plugin("beta-plugin") is None


@pytest.mark.asyncio
async def test_load_plugins_from_directory_include_supports_glob_patterns(
    tmp_path, monkeypatch
):
    (tmp_path / "weather_tool.py").write_text("# weather", encoding="utf-8")
    (tmp_path / "slack_notifier.py").write_text("# slack", encoding="utf-8")

    modules = {
        "app.plugins.weather_tool": _plugin_module(
            "app.plugins.weather_tool",
            _build_plugin_class("weather-plugin", ["network.http"]),
        ),
        "app.plugins.slack_notifier": _plugin_module(
            "app.plugins.slack_notifier",
            _build_plugin_class("slack-plugin", ["network.http"]),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    loaded = await manager.load_plugins_from_directory(include_plugins=["*tool"])

    assert loaded == ["weather-plugin"]
    assert manager.get_plugin("weather-plugin") is not None
    assert manager.get_plugin("slack-plugin") is None


@pytest.mark.asyncio
async def test_load_plugins_from_directory_exclude_supports_glob_patterns(
    tmp_path, monkeypatch
):
    (tmp_path / "weather_tool.py").write_text("# weather", encoding="utf-8")
    (tmp_path / "slack_notifier.py").write_text("# slack", encoding="utf-8")

    modules = {
        "app.plugins.weather_tool": _plugin_module(
            "app.plugins.weather_tool",
            _build_plugin_class("weather-plugin", ["network.http"]),
        ),
        "app.plugins.slack_notifier": _plugin_module(
            "app.plugins.slack_notifier",
            _build_plugin_class("slack-plugin", ["network.http"]),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    loaded = await manager.load_plugins_from_directory(exclude_plugins=["*_tool"])

    assert loaded == ["slack-plugin"]
    assert manager.get_plugin("weather-plugin") is None
    assert manager.get_plugin("slack-plugin") is not None


@pytest.mark.asyncio
async def test_load_plugins_from_directory_rejects_include_exclude_overlap(
    tmp_path, monkeypatch
):
    (tmp_path / "alpha.py").write_text("# alpha", encoding="utf-8")

    module = _plugin_module(
        "app.plugins.alpha",
        _build_plugin_class("alpha-plugin", ["network.http"]),
    )

    def _import_module(name: str):
        if name == "app.plugins.alpha":
            return module
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))

    with pytest.raises(
        ValueError,
        match="Plugins cannot be both included and excluded: alpha",
    ):
        await manager.load_plugins_from_directory(
            include_plugins=["alpha"],
            exclude_plugins=["app.plugins.alpha"],
        )


@pytest.mark.asyncio
async def test_load_plugins_from_directory_filters_by_required_permissions(
    tmp_path, monkeypatch
):
    (tmp_path / "http_plugin.py").write_text("# http", encoding="utf-8")
    (tmp_path / "local_plugin.py").write_text("# local", encoding="utf-8")

    modules = {
        "app.plugins.http_plugin": _plugin_module(
            "app.plugins.http_plugin",
            _build_plugin_class("http-plugin", ["network.http", "filesystem.read"]),
        ),
        "app.plugins.local_plugin": _plugin_module(
            "app.plugins.local_plugin",
            _build_plugin_class("local-plugin", ["filesystem.read"]),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    loaded = await manager.load_plugins_from_directory(
        required_permissions=["network.http"]
    )

    assert loaded == ["http-plugin"]
    assert manager.get_plugin("http-plugin") is not None
    assert manager.get_plugin("local-plugin") is None


@pytest.mark.asyncio
async def test_load_plugins_from_directory_filters_by_required_permission_glob(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "http_plugin.py").write_text("# http", encoding="utf-8")
    (tmp_path / "local_plugin.py").write_text("# local", encoding="utf-8")

    modules = {
        "app.plugins.http_plugin": _plugin_module(
            "app.plugins.http_plugin",
            _build_plugin_class("http-plugin", ["network.http", "filesystem.read"]),
        ),
        "app.plugins.local_plugin": _plugin_module(
            "app.plugins.local_plugin",
            _build_plugin_class("local-plugin", ["filesystem.read"]),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    loaded = await manager.load_plugins_from_directory(
        required_permissions=["network.*"]
    )

    assert loaded == ["http-plugin"]
    assert manager.get_plugin("http-plugin") is not None
    assert manager.get_plugin("local-plugin") is None


@pytest.mark.asyncio
async def test_load_plugins_from_directory_required_permissions_validates_payload(
    tmp_path,
):
    manager = PluginManager(plugin_dir=str(tmp_path))

    with pytest.raises(
        ValueError,
        match="required_permissions must contain only strings",
    ):
        await manager.load_plugins_from_directory(
            required_permissions=["network.http", 1]
        )

    with pytest.raises(
        ValueError,
        match="required_permissions cannot contain blank values",
    ):
        await manager.load_plugins_from_directory(required_permissions=["   "])


@pytest.mark.asyncio
async def test_list_plugins_filters_by_required_permissions(tmp_path, monkeypatch):
    (tmp_path / "http_plugin.py").write_text("# http", encoding="utf-8")
    (tmp_path / "local_plugin.py").write_text("# local", encoding="utf-8")

    modules = {
        "app.plugins.http_plugin": _plugin_module(
            "app.plugins.http_plugin",
            _build_plugin_class("http-plugin", ["network.http", "filesystem.read"]),
        ),
        "app.plugins.local_plugin": _plugin_module(
            "app.plugins.local_plugin",
            _build_plugin_class("local-plugin", ["filesystem.read"]),
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


@pytest.mark.asyncio
async def test_list_plugins_filters_by_required_permission_glob(tmp_path, monkeypatch):
    (tmp_path / "http_plugin.py").write_text("# http", encoding="utf-8")
    (tmp_path / "local_plugin.py").write_text("# local", encoding="utf-8")

    modules = {
        "app.plugins.http_plugin": _plugin_module(
            "app.plugins.http_plugin",
            _build_plugin_class("http-plugin", ["network.http", "filesystem.read"]),
        ),
        "app.plugins.local_plugin": _plugin_module(
            "app.plugins.local_plugin",
            _build_plugin_class("local-plugin", ["filesystem.read"]),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugins_from_directory()

    filtered = manager.list_plugins(required_permissions=["network.*"])

    assert [item["name"] for item in filtered] == ["http-plugin"]


@pytest.mark.asyncio
async def test_list_plugins_supports_include_and_exclude_selectors(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "weather_tool.py").write_text("# weather", encoding="utf-8")
    (tmp_path / "slack_notifier.py").write_text("# slack", encoding="utf-8")

    modules = {
        "app.plugins.weather_tool": _plugin_module(
            "app.plugins.weather_tool",
            _build_plugin_class("weather-plugin", ["network.http"]),
        ),
        "app.plugins.slack_notifier": _plugin_module(
            "app.plugins.slack_notifier",
            _build_plugin_class("slack-plugin", ["network.http"]),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugins_from_directory()

    included = manager.list_plugins(include_plugins=["app.plugins.weather_tool"])
    assert [item["name"] for item in included] == ["weather-plugin"]

    excluded = manager.list_plugins(exclude_plugins=["weather_*"])
    assert [item["name"] for item in excluded] == ["slack-plugin"]


@pytest.mark.asyncio
async def test_list_plugins_rejects_include_exclude_overlap(tmp_path, monkeypatch):
    (tmp_path / "weather_tool.py").write_text("# weather", encoding="utf-8")

    module = _plugin_module(
        "app.plugins.weather_tool",
        _build_plugin_class("weather-plugin", ["network.http"]),
    )

    def _import_module(name: str):
        if name == "app.plugins.weather_tool":
            return module
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugins_from_directory()

    with pytest.raises(
        ValueError,
        match="Plugins cannot be both included and excluded: weather_tool",
    ):
        manager.list_plugins(
            include_plugins=["app.plugins.weather_tool"],
            exclude_plugins=["weather_tool.py"],
        )


@pytest.mark.asyncio
async def test_list_plugins_required_permissions_validates_payload(tmp_path):
    manager = PluginManager(plugin_dir=str(tmp_path))

    with pytest.raises(
        ValueError,
        match="required_permissions must contain only strings",
    ):
        manager.list_plugins(required_permissions=["network.http", 1])

    with pytest.raises(
        ValueError,
        match="required_permissions cannot contain blank values",
    ):
        manager.list_plugins(required_permissions=["   "])


@pytest.mark.asyncio
async def test_reload_plugin_reuses_existing_config_and_cleans_up_old_instance(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "reloadable.py").write_text("# reloadable", encoding="utf-8")

    lifecycle: dict[str, int] = {}
    modules = {
        "app.plugins.reloadable": _plugin_module(
            "app.plugins.reloadable",
            _build_plugin_class("reloadable-plugin", ["network.http"], lifecycle),
        )
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    first = await manager.load_plugin("app.plugins.reloadable", {"units": "metric"})

    reloaded = await manager.reload_plugin("reloadable-plugin")

    assert reloaded is not first
    assert reloaded.config == {"units": "metric"}
    assert lifecycle == {"initialized": 2, "cleaned": 1}


@pytest.mark.asyncio
async def test_reload_plugin_accepts_config_override(tmp_path, monkeypatch):
    (tmp_path / "reloadable.py").write_text("# reloadable", encoding="utf-8")

    modules = {
        "app.plugins.reloadable": _plugin_module(
            "app.plugins.reloadable",
            _build_plugin_class("reloadable-plugin", ["network.http"]),
        )
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugin("app.plugins.reloadable", {"units": "metric"})

    reloaded = await manager.reload_plugin(
        "reloadable-plugin",
        {"units": "imperial"},
    )

    assert reloaded.config == {"units": "imperial"}


@pytest.mark.asyncio
async def test_reload_plugin_raises_for_missing_plugin():
    manager = PluginManager()

    with pytest.raises(ValueError, match="Plugin not found"):
        await manager.reload_plugin("missing")


@pytest.mark.asyncio
async def test_reload_plugins_reloads_all_loaded_plugins(tmp_path, monkeypatch):
    (tmp_path / "alpha.py").write_text("# alpha", encoding="utf-8")
    (tmp_path / "beta.py").write_text("# beta", encoding="utf-8")

    alpha_lifecycle: dict[str, int] = {}
    beta_lifecycle: dict[str, int] = {}

    modules = {
        "app.plugins.alpha": _plugin_module(
            "app.plugins.alpha",
            _build_plugin_class("alpha-plugin", ["network.http"], alpha_lifecycle),
        ),
        "app.plugins.beta": _plugin_module(
            "app.plugins.beta",
            _build_plugin_class("beta-plugin", ["filesystem.read"], beta_lifecycle),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugins_from_directory(
        plugin_configs={
            "alpha": {"units": "metric"},
            "beta": {"scope": "local"},
        }
    )

    reloaded = await manager.reload_plugins()

    assert reloaded == ["alpha-plugin", "beta-plugin"]
    assert alpha_lifecycle == {"initialized": 2, "cleaned": 1}
    assert beta_lifecycle == {"initialized": 2, "cleaned": 1}
    assert manager.get_plugin("alpha-plugin").config == {"units": "metric"}
    assert manager.get_plugin("beta-plugin").config == {"scope": "local"}


@pytest.mark.asyncio
async def test_reload_plugins_supports_selectors_and_config_overrides(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "weather_tool.py").write_text("# weather", encoding="utf-8")
    (tmp_path / "slack_notifier.py").write_text("# slack", encoding="utf-8")

    weather_lifecycle: dict[str, int] = {}
    slack_lifecycle: dict[str, int] = {}

    modules = {
        "app.plugins.weather_tool": _plugin_module(
            "app.plugins.weather_tool",
            _build_plugin_class(
                "weather-plugin",
                ["network.http"],
                weather_lifecycle,
            ),
        ),
        "app.plugins.slack_notifier": _plugin_module(
            "app.plugins.slack_notifier",
            _build_plugin_class(
                "slack-plugin",
                ["network.http"],
                slack_lifecycle,
            ),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugins_from_directory(
        plugin_configs={
            "weather_tool": {"units": "metric"},
            "slack_notifier": {"channel": "alerts"},
        }
    )

    reloaded = await manager.reload_plugins(
        include_plugins=["weather*"],
        plugin_configs={"weather-plugin": {"units": "imperial"}},
    )

    assert reloaded == ["weather-plugin"]
    assert weather_lifecycle == {"initialized": 2, "cleaned": 1}
    assert slack_lifecycle == {"initialized": 1}

    assert manager.get_plugin("weather-plugin").config == {"units": "imperial"}
    assert manager.get_plugin("slack-plugin").config == {"channel": "alerts"}


@pytest.mark.asyncio
async def test_reload_plugins_validates_selector_overlap_and_config_payload(tmp_path):
    manager = PluginManager(plugin_dir=str(tmp_path))

    with pytest.raises(
        ValueError,
        match="Plugins cannot be both included and excluded: weather_tool",
    ):
        await manager.reload_plugins(
            include_plugins=["weather_tool"],
            exclude_plugins=["weather_tool.py"],
        )

    with pytest.raises(ValueError, match="plugin_configs must be a mapping"):
        await manager.reload_plugins(plugin_configs=[("weather", {"units": "metric"})])

    with pytest.raises(
        ValueError,
        match="plugin_configs values must be mapping configuration objects",
    ):
        await manager.reload_plugins(plugin_configs={"weather": "metric"})


@pytest.mark.asyncio
async def test_validate_permissions_supports_glob_patterns(tmp_path, monkeypatch):
    (tmp_path / "weather_tool.py").write_text("# weather", encoding="utf-8")

    module = _plugin_module(
        "app.plugins.weather_tool",
        _build_plugin_class("weather-plugin", ["network.http", "filesystem.read"]),
    )

    def _import_module(name: str):
        if name == "app.plugins.weather_tool":
            return module
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugins_from_directory()

    assert manager.validate_permissions("weather-plugin", ["network.*"])
    assert manager.validate_permissions(
        "weather-plugin",
        ["network.http", "filesystem.*"],
    )
    assert not manager.validate_permissions("weather-plugin", ["network.ws"])


@pytest.mark.asyncio
async def test_load_plugins_from_directory_required_permissions_supports_any_matching(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "network_only.py").write_text("# network", encoding="utf-8")
    (tmp_path / "filesystem_only.py").write_text("# filesystem", encoding="utf-8")

    modules = {
        "app.plugins.network_only": _plugin_module(
            "app.plugins.network_only",
            _build_plugin_class("network-only", ["network.http"]),
        ),
        "app.plugins.filesystem_only": _plugin_module(
            "app.plugins.filesystem_only",
            _build_plugin_class("filesystem-only", ["filesystem.read"]),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    loaded = await manager.load_plugins_from_directory(
        required_permissions=["network.http", "filesystem.read"],
        match_any_permissions=True,
    )

    assert loaded == ["filesystem-only", "network-only"]


@pytest.mark.asyncio
async def test_list_plugins_required_permissions_support_any_matching(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "network_only.py").write_text("# network", encoding="utf-8")
    (tmp_path / "filesystem_only.py").write_text("# filesystem", encoding="utf-8")

    modules = {
        "app.plugins.network_only": _plugin_module(
            "app.plugins.network_only",
            _build_plugin_class("network-only", ["network.http"]),
        ),
        "app.plugins.filesystem_only": _plugin_module(
            "app.plugins.filesystem_only",
            _build_plugin_class("filesystem-only", ["filesystem.read"]),
        ),
    }

    def _import_module(name: str):
        if name in modules:
            return modules[name]
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugins_from_directory()

    filtered = manager.list_plugins(
        required_permissions=["network.http", "filesystem.read"],
        match_any_permissions=True,
    )

    assert [item["name"] for item in filtered] == [
        "filesystem-only",
        "network-only",
    ]


@pytest.mark.asyncio
async def test_validate_permissions_supports_any_matching_mode(tmp_path, monkeypatch):
    (tmp_path / "weather_tool.py").write_text("# weather", encoding="utf-8")

    module = _plugin_module(
        "app.plugins.weather_tool",
        _build_plugin_class("weather-plugin", ["network.http", "filesystem.read"]),
    )

    def _import_module(name: str):
        if name == "app.plugins.weather_tool":
            return module
        raise ImportError(name)

    monkeypatch.setattr("app.plugins.manager.importlib.import_module", _import_module)

    manager = PluginManager(plugin_dir=str(tmp_path))
    await manager.load_plugins_from_directory()

    assert not manager.validate_permissions(
        "weather-plugin",
        ["network.ws", "filesystem.write"],
    )
    assert manager.validate_permissions(
        "weather-plugin",
        ["network.ws", "network.http"],
        match_any_permissions=True,
    )


@pytest.mark.asyncio
async def test_required_permission_any_matching_flag_must_be_boolean(tmp_path):
    manager = PluginManager(plugin_dir=str(tmp_path))

    with pytest.raises(ValueError, match="match_any_permissions must be a boolean"):
        await manager.load_plugins_from_directory(
            required_permissions=["network.http"],
            match_any_permissions="yes",  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="match_any_permissions must be a boolean"):
        manager.list_plugins(
            required_permissions=["network.http"],
            match_any_permissions="yes",  # type: ignore[arg-type]
        )
