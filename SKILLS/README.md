# Super Memory Skills for OpenClaw

This directory contains skill definitions for OpenClaw agents using super-memory.
Each skill covers one usage mode/flow of super-memory.

## Skill Index

| Skill | File | Mode | Description |
|-------|------|------|-------------|
| Onboarding | `onboarding.md` | setup | Install, verify, three-way sync |
| Basic Usage | `basic-usage.md` | core | Remember, recall, search, forget, edit |
| Quality Ingest | `quality-ingest.md` | quality | MemoryEnvelope, SourceAdapter, Closets |
| Recall Arbitration | `recall-arbitration.md` | advanced | Explainable recall, citations, dialectic |
| Cross-Agent | `cross-agent.md` | multi-agent | Multi-agent memory, Honcho perspective |
| Auto Deep | `auto-deep.md` | automation | CI/CD pipeline, consolidate, dream, tiers |
| Self Improve | `self-improve.md` | self-learn | Self-heal, curriculum, drift repair |
| Lifecycle | `lifecycle.md` | maintenance | Tiers, decay, compression, Leitner, dream |

## Agent Mode Mapping

| Agent role | Skills needed |
|------------|---------------|
| **New agent** (first run) | onboarding → basic-usage |
| **Developer agent** | basic-usage → quality-ingest → recall-arbitration |
| **Multi-agent team** | cross-agent → basic-usage |
| **Maintenance agent** | auto-deep → lifecycle → self-improve |
| **Self-learning agent** | self-improve → auto-deep |
| **Production agent** | all skills |

## Recommended Cron Jobs

For automated Dream Engine, Self-Improvement, and daily maintenance without manual intervention, set up these 3 cron jobs on new OpenClaw installs:

| Job | Schedule | Description |
|-----|----------|-------------|
| **smem-daily-maintenance** | Daily 2AM | Semantic index, dedup, compression (`POST /maintenance/run light`) |
| **smem-weekly-dream** | Sunday 3AM | Dream Engine full cycle (insight → weak tie → pattern summary) |
| **smem-monthly-deep** | Day 1 4AM | Drift repair + self-heal + full maintenance |

See [`docs/recommended-cron-jobs.md`](../docs/recommended-cron-jobs.md) for exact JSON payloads and setup instructions.
