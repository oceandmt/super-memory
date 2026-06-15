# Super Memory Operator

Use this skill when installing, operating, debugging, or maintaining the Super Memory OpenClaw plugin.

## When to Use

- Setting up a fresh OpenClaw instance with Super Memory
- Debugging memory recall or tool visibility
- Migrating from local markdown memory to Super Memory
- Running memory health checks or consolidation
- Verifying OpenClaw memory slot replacement

## Core Doctrine

Super Memory is both:

1. An OpenClaw memory slot replacement
2. A rich memory tool suite for associative recall

Do not rely on Super Memory alone. Keep human-readable markdown continuity files for auditability.

## First-Run Checklist

1. Verify plugin loaded:
   - `openclaw plugins doctor`
   - `openclaw status`

2. Verify API service:
   - `curl http://127.0.0.1:8765/status`

3. Verify tool policy includes plugin tools:
   - `tools.profile: "full"`, or
   - `tools.allow` includes `"group:plugins"`

4. Verify memory slot:
   - `plugins.slots.memory: "super-memory"`

5. Install workspace templates if missing:
   - `AGENTS.md`
   - `SOUL.md`
   - `USER.md`
   - `IDENTITY.md`
   - `MEMORY.md`
   - `HEARTBEAT.md`
   - `memory/active-memory-rules.md`

## Daily Use

- Before answering prior-work questions, recall with `super_memory_recall`.
- After durable outcomes, save with `super_memory_remember`.
- For TODOs, use `super_memory_todo`.
- For health, use `super_memory_health` and `super_memory_stats`.
- For maintenance, run `super_memory_consolidate` periodically.

## Memory Write Style

Good memory:

> User prefers Vietnamese by default; technical terms can remain English.

Bad memory:

> Full raw transcript of a whole conversation.

Keep memories atomic, specific, and durable.

## Troubleshooting

### Tools not visible

Check:

```json
{
  "tools": {
    "profile": "full",
    "allow": ["*", "group:plugins"]
  }
}
```

Or use exact tool allows such as:

```json
{
  "tools": {
    "allow": ["super_memory_*", "group:plugins"]
  }
}
```

### Plugin blocked by ownership

OpenClaw may reject plugin directories owned by an unexpected UID. Fix on VPS:

```bash
chown -R root:root ~/.openclaw/plugins/super-memory ~/.openclaw/super-memory
```

### Telegram owner commands unavailable

Set command owner explicitly:

```json
{
  "commands": {
    "ownerAllowFrom": ["telegram:<OWNER_CHAT_ID>"]
  }
}
```

### Language drift

Add language policy to `SOUL.md` and `AGENTS.md` rather than using invalid config keys.
