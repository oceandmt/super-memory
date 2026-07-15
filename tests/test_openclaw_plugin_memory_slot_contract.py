import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "openclaw-plugin" / "super-memory" / "index.js"


def _run_node(script: str) -> dict:
    proc = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _cfg(plugin_config: dict) -> str:
    """Build the JS config object literal matching real OpenClaw runtime shape:
    api.config is the global config; plugin-specific settings live under
    plugins.entries['super-memory'].config (see index.js pluginCfg lookup).
    """
    return json.dumps({
        "plugins": {"entries": {"super-memory": {"config": plugin_config}}},
        **plugin_config,
    })


def test_plugin_memory_capability_guarded_by_default():
    script = f"""
const plugin = require({json.dumps(str(PLUGIN))});
const calls = {{ capabilities: 0, tools: [] }};
global.fetch = async () => {{ throw new Error('fetch should not be called during registration'); }};
plugin({{
  config: {{cfg}},
  registerMemoryCapability() {{ calls.capabilities += 1; }},
  registerTool(tool) {{ calls.tools.push(tool.name); }},
  registerMemoryCorpusSupplement() {{}},
  registerMemoryPromptSupplement() {{}},
}});
console.log(JSON.stringify(calls));
""".replace("{cfg}", _cfg({"apiBaseUrl": "http://super-memory.test"}))
    result = _run_node(script)
    assert result["capabilities"] == 0
    assert "memory_search" not in result["tools"]
    assert "memory_get" not in result["tools"]
    assert "super_memory_remember" in result["tools"]


def test_plugin_memory_slot_manager_search_and_readfile_contract():
    script = f"""
const plugin = require({json.dumps(str(PLUGIN))});
const calls = {{ capabilities: [], tools: [] }};
global.fetch = async (url, opts = {{}}) => {{
  const body = opts.body ? JSON.parse(opts.body) : {{}};
  if (String(url).endsWith('/memory-search')) {{
    return {{ ok: true, json: async () => ({{
      provider: 'super-memory',
      results: [{{
        id: 'hit-1', path: 'memory/phase8.md', startLine: 7, endLine: 9,
        score: 0.93, textScore: 0.91, snippet: 'phase8 contract memory',
        corpus: 'memory', layer: 'workspace_markdown', memory_id: 'mem-1'
      }}], citations: [], debug: {{ body }}
    }}) }};
  }}
  if (String(url).endsWith('/memory-get')) {{
    return {{ ok: true, json: async () => ({{
      path: body.path, from: body.from_line, lines: body.lines,
      content: 'phase8 exact memory content', truncated: false,
      source: 'super-memory', metadata: {{ id: 'mem-1' }}
    }}) }};
  }}
  throw new Error('unexpected url ' + url);
}};
plugin({{
  config: {{cfg}},
  registerMemoryCapability(capability) {{ calls.capabilities.push(capability); }},
  registerTool(tool) {{ calls.tools.push(tool.name); }},
  registerMemoryCorpusSupplement() {{}},
  registerMemoryPromptSupplement() {{}},
}});
(async () => {{
  const managerEnvelope = await calls.capabilities[0].runtime.getMemorySearchManager();
  const manager = managerEnvelope.manager;
  let debug = null;
  const hits = await manager.search('phase8 contract', {{ maxResults: 3, minScore: 0.2, onDebug: d => debug = d }});
  const file = await manager.readFile({{ relPath: 'memory/phase8.md', from: 7, lines: 3 }});
  console.log(JSON.stringify({{
    capabilityCount: calls.capabilities.length,
    hasLegacySearch: calls.tools.includes('memory_search'),
    hasLegacyGet: calls.tools.includes('memory_get'),
    hit: hits[0],
    file,
    debug,
    status: manager.status()
  }}));
}})().catch(err => {{ console.error(err); process.exit(1); }});
""".replace("{cfg}", _cfg({
    "apiBaseUrl": "http://super-memory.test",
    "registerExclusiveMemoryCapability": True,
    "registerLegacyMemoryShims": True,
}))
    result = _run_node(script)
    assert result["capabilityCount"] == 1
    assert result["hasLegacySearch"] is True
    assert result["hasLegacyGet"] is True
    assert result["hit"]["path"] == "memory/phase8.md"
    assert result["hit"]["startLine"] == 7
    assert result["hit"]["endLine"] == 9
    assert result["hit"]["source"] == "memory"
    assert result["hit"]["citation"] == "memory/phase8.md#7"
    assert result["file"]["text"] == "phase8 exact memory content"
    assert result["file"]["from"] == 7
    assert result["file"]["lines"] == 3
    assert result["debug"]["effectiveMode"] == "super-memory"
    assert result["status"]["provider"] == "super-memory"

def test_plugin_admin_mode_enables_capture_without_exclusive_slot():
    script = f"""
const plugin = require({json.dumps(str(PLUGIN))});
const calls = {{ capabilities: 0, tools: [], hooks: [] }};
global.fetch = async () => {{ throw new Error('fetch should not be called during registration'); }};
plugin({{
  config: {{cfg}},
  registerMemoryCapability() {{ calls.capabilities += 1; }},
  registerTool(tool) {{ calls.tools.push(tool.name); }},
  registerMemoryCorpusSupplement() {{}},
  registerMemoryPromptSupplement() {{}},
  registerService() {{}},
  on(name) {{ calls.hooks.push(name); }},
  logger: {{ info: () => {{}}, warn: () => {{}} }}
}});
console.log(JSON.stringify(calls));
""".replace("{cfg}", _cfg({"apiBaseUrl": "http://super-memory.test", "mode": "admin"}))
    result = _run_node(script)
    assert result["capabilities"] == 0
    assert "memory_search" not in result["tools"]
    assert "memory_get" not in result["tools"]
    assert "agent_end" in result["hooks"]
    assert "super_memory_remember" in result["tools"]


def test_plugin_exclusive_mode_enables_memory_slot_and_legacy_shims():
    script = f"""
const plugin = require({json.dumps(str(PLUGIN))});
const calls = {{ capabilities: 0, tools: [] }};
global.fetch = async () => {{ throw new Error('fetch should not be called during registration'); }};
plugin({{
  config: {{cfg}},
  registerMemoryCapability() {{ calls.capabilities += 1; }},
  registerTool(tool) {{ calls.tools.push(tool.name); }},
  registerMemoryCorpusSupplement() {{}},
  registerMemoryPromptSupplement() {{}},
  registerService() {{}},
  on() {{}},
  logger: {{ info: () => {{}}, warn: () => {{}} }}
}});
console.log(JSON.stringify(calls));
""".replace("{cfg}", _cfg({"apiBaseUrl": "http://super-memory.test", "mode": "exclusive"}))
    result = _run_node(script)
    assert result["capabilities"] == 1
    assert "memory_search" in result["tools"]
    assert "memory_get" in result["tools"]


def test_plugin_manifest_and_registration_parity():
    """Verify manifest kind:memory and all tools register successfully."""
    import json
    manifest_path = ROOT / "openclaw-plugin" / "super-memory" / "openclaw.plugin.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    assert manifest.get("kind") == "memory", f"Expected kind=memory, got {manifest.get('kind')}"
    assert "jsonSchema" in manifest.get("configSchema", {})

    script = f"""
const plugin = require({json.dumps(str(PLUGIN))});
const registered = [];
global.fetch = async () => {{ throw new Error('fetch should not be called during registration'); }};
plugin({{
  config: {{ apiBaseUrl: 'http://super-memory.test' }},
  registerMemoryCapability() {{}},
  registerTool(tool) {{ registered.push(tool.name); }},
  registerMemoryCorpusSupplement() {{}},
  registerMemoryPromptSupplement() {{}},
  registerService() {{}},
  on() {{}},
  logger: {{ info: () => {{}}, warn: () => {{}} }}
}});
console.log(JSON.stringify({{ registered }}));
"""
    result = _run_node(script)
    registered_tools = set(result["registered"])

    assert len(registered_tools) >= 21, f"Expected >=21 tools, got {len(registered_tools)}: {sorted(registered_tools)}"
    assert "super_memory_remember" in registered_tools
    assert "super_memory_recall" in registered_tools
