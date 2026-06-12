from pathlib import Path
import json


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
