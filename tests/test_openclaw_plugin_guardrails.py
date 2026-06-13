from pathlib import Path
import json
import re


def test_plugin_exclusive_memory_capability_is_disabled_by_default():
    manifest = json.loads(Path("openclaw-plugin/super-memory/openclaw.plugin.json").read_text())
    prop = manifest["configSchema"]["properties"]["registerExclusiveMemoryCapability"]
    assert prop["default"] is False
    shims = manifest["configSchema"]["properties"]["registerLegacyMemoryShims"]
    assert shims["default"] is False


def test_plugin_contains_development_only_exclusive_capability_guard():
    source = Path("openclaw-plugin/super-memory/index.js").read_text()
    assert "cfg.registerExclusiveMemoryCapability === true" in source
    assert "cfg.registerLegacyMemoryShims === true" in source
    assert "api.registerMemoryCapability" in source
    assert "api.registerMemoryCorpusSupplement" in source
    assert "name: 'memory_search'" in source
    assert "name: 'memory_get'" in source

def test_plugin_register_function_is_synchronous_for_openclaw_loader():
    source = Path("openclaw-plugin/super-memory/index.js").read_text()
    assert "module.exports = function superMemoryPlugin(api)" in source
    assert "module.exports = async function superMemoryPlugin" not in source

def test_manifest_contracts_declare_every_registered_tool():
    manifest = json.loads(Path("openclaw-plugin/super-memory/openclaw.plugin.json").read_text())
    declared = set(manifest["contracts"]["tools"])
    source = Path("openclaw-plugin/super-memory/index.js").read_text()
    registered = set(re.findall(r"name:\s*'([^']+)'", source))
    # Also extract names from array-format tools declared as ['tool_name', ...]
    registered.update(re.findall(r"\[\s*'(super_memory_[^']+)'\s*,", source))
    # Filter gated tools that are only registered with config flags
    gated = {'memory_search', 'memory_get', 'super_memory_mcp_tools_list'}
    registered = registered - gated
    assert registered
    assert declared == registered
