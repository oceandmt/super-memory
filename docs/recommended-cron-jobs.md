# Recommended Cron Jobs for Super Memory

> **Version**: 2.2.0  
> **Last updated**: 2026-06-23

These cron jobs automate Dream Engine, Self-Improvement, and daily maintenance so Super Memory stays healthy without manual intervention.

---

## Overview

| Job | Schedule | What it does | Why |
|-----|----------|-------------|-----|
| **smem-daily-maintenance** | Daily 2AM ICT | Semantic index, dedup, compression | Keep memory lean, fresh, fast |
| **smem-weekly-dream** | Sunday 3AM ICT | Dream Engine: insight → weak tie → pattern | Find latent patterns, strengthen graph |
| **smem-monthly-deep** | Day 1 4AM ICT | Drift repair + self-heal + full maintenance | Fix projection drift, deep cleanup |

---

## Prerequisites

- OpenClaw gateway with cron support
- Super Memory MCP server running (`mcp.servers.super-memory`)
- Super Memory plugin configured (`plugins.entries.super-memory`)

---

## How to Create

### 1. Daily Maintenance (2AM)

```json
{
  "name": "smem-daily-maintenance",
  "schedule": { "kind": "cron", "expr": "0 2 * * *", "tz": "Asia/Ho_Chi_Minh" },
  "payload": {
    "kind": "agentTurn",
    "message": "Run super-memory daily maintenance: POST /maintenance/run with strategy=light, dry_run=false to keep semantic index fresh, dedup clusters, and optimize compression"
  },
  "sessionTarget": "isolated"
}
```

### 2. Weekly Dream Engine (Sunday 3AM)

```json
{
  "name": "smem-weekly-dream",
  "schedule": { "kind": "cron", "expr": "0 3 * * 0", "tz": "Asia/Ho_Chi_Minh" },
  "payload": {
    "kind": "agentTurn",
    "message": "Run super-memory Dream Engine full cycle: insight_generation -> weak_tie_reinforcement -> pattern_summary with limit=200, dry_run=false to find latent patterns, strengthen weak synapses, and summarize repetitive content"
  },
  "sessionTarget": "isolated"
}
```

### 3. Monthly Deep Maintenance (Day 1 4AM)

```json
{
  "name": "smem-monthly-deep",
  "schedule": { "kind": "cron", "expr": "0 4 1 * *", "tz": "Asia/Ho_Chi_Minh" },
  "payload": {
    "kind": "agentTurn",
    "message": "Run super-memory deep monthly maintenance: 1) full_drift_repair with dry_run=false to audit and repair projection orphans, 2) check self_heal_status for embedding health, 3) run maintenance full cycle for comprehensive cleanup"
  },
  "sessionTarget": "isolated"
}
```

---

## Delivery Configuration

All jobs default to `sessionTarget: "isolated"` so they run in ephemeral sessions. Results can be delivered via:

```json
"delivery": {
  "mode": "announce",
  "channel": "discord",
  "to": "<channel-id>"
}
```

---

## Important Notes

1. **MCP server required** — These jobs call `super_memory_*` tools which are only available through the MCP server. The plugin's 102 tools do NOT include Dream Engine or Self-Improvement tools.

2. **Dry-run safety** — All Dream Engine tools default to `dry_run=true`. The cron jobs above set `dry_run=false` explicitly. Test with `dry_run=true` first on a new install.

3. **Maintenance is safe** — `POST /maintenance/run` with `strategy=light` is read-safe: it only indexes, deduplicates, and marks compression candidates without destructive actions.

4. **Timezone** — Adjust `tz` to match your local timezone. Example: `Asia/Ho_Chi_Minh`, `America/New_York`, `Europe/London`.

5. **Timeouts** — Dream Engine full cycle may take 30-120 seconds. Set `toolCallTimeoutMs: 120000` in MCP server config if needed.

---

## Verification

After creating the jobs, verify they are registered:

```bash
# List all cron jobs
cron list

# Check job IDs
cron get --id <job-id>

# View next run times from state.nextRunAtMs
```

---

## Alternative: Manual Triggers

If cron is not available, trigger maintenance manually:

```bash
# Maintenance light
curl -X POST http://127.0.0.1:8765/maintenance/run \
  -H "Content-Type: application/json" \
  -d '{"strategy": "light", "dry_run": false}'

# Full consolidation
super-memory consolidate

# Doctor check
super-memory doctor --json-out
```

---

*Part of Super Memory v2.3.6 — see [roadmap](./roadmap.md) for the full picture.*
