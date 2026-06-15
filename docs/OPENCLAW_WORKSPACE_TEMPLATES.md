# OpenClaw Workspace Templates

Super Memory includes a minimal OpenClaw workspace starter pack so a fresh OpenClaw instance can operate immediately after installing the plugin.

## Included Files

Plugin directory:

```text
openclaw-plugin/super-memory/workspace-templates/
├── AGENTS.md
├── SOUL.md
├── USER.md
├── IDENTITY.md
├── MEMORY.md
├── HEARTBEAT.md
└── memory/active-memory-rules.md
```

Skill directory:

```text
openclaw-plugin/super-memory/skills/super-memory-operator/SKILL.md
```

## Purpose

These files provide:

- Persona and language policy
- User profile template
- Durable memory doctrine
- Daily-memory rules
- Super Memory operating procedures
- First-run checklist
- Troubleshooting guidance

## Install on a Fresh OpenClaw Host

From the super-memory repository root:

```bash
PLUGIN_DIR="$HOME/.openclaw/plugins/super-memory"
WORKSPACE_DIR="$HOME/.openclaw/workspace"
SKILLS_DIR="$HOME/.openclaw/workspace/skills"

mkdir -p "$WORKSPACE_DIR" "$SKILLS_DIR"
cp -n "$PLUGIN_DIR/workspace-templates/"*.md "$WORKSPACE_DIR/"
cp -rn "$PLUGIN_DIR/workspace-templates/memory" "$WORKSPACE_DIR/"
cp -rn "$PLUGIN_DIR/skills/super-memory-operator" "$SKILLS_DIR/"
```

Use `cp -n` to avoid overwriting an existing operator workspace. If you want to replace files, back up first.

## Recommended OpenClaw Config

```json
{
  "tools": {
    "profile": "full",
    "allow": ["*", "group:plugins", "message", "group:messaging"]
  },
  "plugins": {
    "load": {
      "paths": ["${REMOTE_PLUGIN_ROOT}"]
    },
    "slots": {
      "memory": "super-memory"
    },
    "entries": {
      "super-memory": {
        "enabled": true,
        "config": {
          "apiBaseUrl": "http://127.0.0.1:8765",
          "autoSyncTurns": true,
          "registerExclusiveMemoryCapability": true,
          "registerLegacyMemoryShims": true,
          "toolProfile": "normal"
        }
      }
    }
  }
}
```

## Verification

```bash
openclaw config validate
openclaw plugins doctor
openclaw status
curl -fsS http://127.0.0.1:8765/status
```

Expected:

- Config valid
- No plugin issues
- Memory enabled with plugin `super-memory`
- API returns JSON status
