# Super Memory Research Summary

This summary distills the repository research into implementation decisions for `projects/super-memory`.

## Hermes Agent patterns to adopt

- Memory should be layered, not one giant context blob.
- Keep hot prompt memory small and curated; use retrieval for larger history.
- Provide a `MemoryProvider`-style adapter interface with lifecycle hooks:
  - initialize/session start
  - prefetch before turn
  - sync after turn
  - pre-compress extraction
  - session-end extraction
  - delegation/subagent event capture
  - memory-write notification
- Use local SQLite/FTS5 transcript/session search as a cheap fallback.
- Treat skills/procedures as procedural memory and route durable workflow improvements into a reviewed proposal/update path.
- Prefer async/post-turn sync so memory writes do not block agent response.
- Use staging/approval for self-improvement writes that change durable procedures.

## MemPalace patterns to adopt

- Verbatim-first storage: raw memory chunks should be preserved before summaries.
- Hierarchical scoping:
  - palace = full store
  - wing = person/project/agent/topic
  - room = specific task/topic
  - hall = category (`facts`, `events`, `discoveries`, `preferences`, `advice`, etc.)
  - drawer = retrieval unit / verbatim chunk
  - tunnel = cross-wing relation
- Metadata filtering should happen before ranking.
- Temporal knowledge graph should support facts that change over time:
  - subject → predicate → object
  - valid_from / valid_to
  - confidence
  - source drawer links
- Add duplicate checking/idempotent ingestion early.
- Agent diary per specialist agent is useful for Lucas/Alex/Max/Isol.

## Honcho patterns to adopt

- Peer/session/conversation memory model:
  - workspace
  - peer
  - session
  - message/event
  - observation/conclusion
  - peer card/profile/representation
- Observer/observed relations are important for multi-agent memory:
  - what Lucas knows about Boss
  - what Alex knows about a project
  - what the project memory knows about a dependency
- Background derivation should be optional and pluggable, not required for baseline local memory.
- Avoid requiring Honcho's full server stack for Super Memory baseline because it introduces Postgres/pgvector/workers/LLM dependencies.

## Neural Memory patterns to adopt

- Local-first SQLite storage.
- Typed memory categories: fact, decision, preference, todo, insight, context, instruction, error, workflow, reference, boundary.
- Typed graph relations:
  - related_to
  - caused_by
  - leads_to
  - resolved_by
  - contradicts
  - supersedes
  - mentions_entity
- Recall should work without embedded LLM:
  - FTS/lexical search
  - entity/time filters
  - graph expansion 1–3 hops
  - score by recency, priority, relation weight, access count, trust/confidence
- Lifecycle should include hot/warm/cold, pin, soft-delete, supersede, reinforce-on-recall, and optional consolidation.

## Super Memory implementation decisions

1. Workspace Markdown remains canonical local truth.
2. Derived layers must not become more authoritative than canonical markdown.
3. Baseline app must run locally without Docker.
4. Baseline remember/recall must not require embedded LLM.
5. Derived layers start as deterministic SQLite adapters with stable APIs.
6. Upstream-specific adapters can be added later behind the same backend interface.
7. Every memory write carries provenance tags: agent, scope, type, project when applicable.
8. Self-improvement writes should distinguish:
   - observation/result
   - lesson
   - workflow candidate
   - approved procedure/skill

## Main risks

- Verbatim memory can grow quickly; retention/lifecycle is required.
- Automatic conclusions can create false memory without provenance/review.
- Too many relation types too early will make recall hard to debug.
- Direct Honcho integration is heavy for local-first use.
- Direct Neural Memory package dependency can overfit Super Memory to a large external API surface.
