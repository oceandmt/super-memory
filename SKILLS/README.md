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
