# Phase 6 — Cognitive Orchestration Model

Status: deterministic baseline implemented  
Project: `projects/super-memory`  
Purpose: make the four Super Memory layers cooperate like complementary human memory systems without breaking canonical-first safety.

## Summary

Phase 6 treats Super Memory as a brain-like memory coordinator. The goal is not to make all layers equally authoritative. The goal is to let all four layers operate in parallel under an executive controller:

1. **Workspace Markdown** = canonical autobiographical/declarative memory.
2. **MemPalace** = spatial/procedural/project memory.
3. **Honcho** = social/conversation/session memory.
4. **NeuralMemory-style** = associative/graph/pattern memory.

The controller coordinates attention, working memory, parallel projection, recall arbitration, consolidation, conflict handling, and feedback learning.

Core invariant remains unchanged:

> Workspace Markdown is canonical local truth. Derived layers enrich recall, but they do not outrank canonical markdown.

## Human-brain analogy

| Super Memory layer | Brain-like role | Primary job |
| --- | --- | --- |
| Workspace Markdown | Hippocampal/autobiographical record | Preserve exact durable truth and provenance |
| MemPalace | Spatial + procedural memory | Organize tasks, projects, rooms, workflows, procedures |
| Honcho | Social/conversation memory | Track participants, sessions, preferences, dialogue state |
| NeuralMemory-style | Associative memory | Link patterns, blockers, insights, workflows, and concepts |
| Cognitive controller | Prefrontal/executive system | Decide what matters, where it goes, what to recall, and what wins conflicts |

## Target workflow

```text
Input / experience
  ↓
Sensory filter: sanitize + normalize
  ↓
Working memory: current task/session/goal/blocker state
  ↓
Attention scoring: decide salience and routing
  ↓
Hippocampal commit: Workspace Markdown canonical event
  ↓
Parallel consolidation/projection:
  ├─ MemPalace: place/procedure/project structure
  ├─ Honcho: social/session/participant state
  └─ NeuralMemory-style: associations/graph/patterns
  ↓
Sleep/consolidation cycle:
  ├─ dedupe
  ├─ strengthen repeated memories
  ├─ detect conflicts
  ├─ promote stable doctrine/workflows
  ├─ decay/archive weak/noisy memories
  └─ create summaries/links
  ↓
Recall:
  ├─ exact recall from Workspace Markdown
  ├─ spatial/procedure recall from MemPalace
  ├─ social/session recall from Honcho
  └─ associative recall from NeuralMemory-style
  ↓
Recall arbitration:
  ├─ exact facts: Markdown wins
  ├─ procedures/projects: MemPalace gets higher weight
  ├─ people/session state: Honcho gets higher weight
  ├─ patterns/associations: NeuralMemory-style gets higher weight
  └─ conflicts: canonical source wins and conflict is reported
  ↓
Compact context / action / reply
  ↓
Feedback learning after outcome
```

## Required Phase 6 components

### 1. Working memory

Short-lived task/session state. It should capture what matters right now without prematurely making every detail permanent.

Recommended fields:

- `current_task`
- `current_goal`
- `active_project`
- `active_agent`
- `active_session`
- `current_blocker`
- `next_step`
- `recent_decisions`
- `scratch_context`
- `expires_at`

Storage options:

- in-process cache for active run
- sandbox-local SQLite table
- optional canonical checkpoint when state should survive restart

### 2. Attention scoring

Not every input deserves the same memory strength. The controller should score salience before save/projection.

Suggested scoring signals:

- Boss explicitly asked to remember/save it.
- Contains a durable decision.
- Contains workflow change or doctrine.
- Contains blocker/error/fix.
- Affects project state.
- Repeats across sessions.
- Has high trust/provenance.
- Contains sensitive material that should be minimized or redacted.
- Is temporary/noisy and should stay in working memory only.

Suggested output:

```json
{
  "attention_score": 0.0,
  "salience": "low|normal|high|critical",
  "routes": ["workspace_markdown", "mempalace", "honcho", "neural"],
  "ttl": "session|days:7|durable",
  "promotion_candidate": false,
  "reason": "short explanation"
}
```

### 3. Parallel layer write

After canonical commit succeeds, derived layers should receive the same normalized event in parallel where safe.

Rules:

- Canonical Workspace Markdown writes first.
- If canonical write fails and `require_canonical_first=true`, derived writes are skipped.
- Derived writes may happen concurrently after canonical success.
- Each layer returns independent result/provenance.
- Partial derived failure should be visible, not hidden.

### 4. Recall arbitrator

Recall may produce different answers from different layers. The arbitrator decides what to trust and how to merge.

Default arbitration rules:

- Exact command/path/config/date/quote: Workspace Markdown or source file wins.
- Workflow/procedure: MemPalace gets higher weight.
- Participant/session/preference: Honcho gets higher weight.
- Pattern/association/repeated blocker: NeuralMemory-style gets higher weight.
- Conflict: preserve all candidates, mark conflict, prefer canonical source until resolved.

Suggested output:

```json
{
  "answer_context": [],
  "layer_votes": {},
  "conflicts": [],
  "winner_policy": "canonical|procedural|social|associative|mixed",
  "confidence": 0.0,
  "citations": []
}
```

### 5. Consolidation scheduler

A sleep-like maintenance cycle that improves memory quality without interrupting live tasks.

Suggested jobs:

- dedupe equivalent memories
- merge repeated workflows
- detect unresolved conflicts
- create summaries for long sessions
- strengthen memories repeatedly recalled or repeatedly validated
- decay/archive low-value or stale memories
- promote stable rules to registers or skill proposals
- update provenance links

Cadence options:

- manual command
- startup safe consolidation
- post-task light consolidation
- periodic background job only after explicit operator configuration

### 6. Conflict resolver

When layers disagree, the system should not silently overwrite. It should mark and route conflicts.

Conflict examples:

- Markdown says one config value; derived layer says another.
- Honcho preference contradicts a newer user instruction.
- Neural-style association suggests stale workflow.
- MemPalace procedure differs from current source file.

Resolution policy:

1. Prefer newest explicit Boss instruction when applicable.
2. Prefer canonical Workspace Markdown/source files for exact facts.
3. Keep both if they apply to different scopes or times.
4. Mark old memory superseded if newer proof invalidates it.
5. Save the resolution as a durable event.

### 7. Promotion engine

Promotion turns repeated or high-value observations into durable doctrine, workflow, or skills.

Promotion candidates:

- repeated fix pattern
- recurring blocker
- stable project convention
- Boss preference
- tool workflow that succeeded multiple times
- safety rule discovered through failure

Promotion destinations:

- `MEMORY.md` for broad orientation
- `memory/registers/` for doctrine/preferences/blockers/workflows
- Skill Workshop proposal for reusable procedures
- project docs for project-specific architecture/workflows

### 8. Feedback learning

After a task completes, the controller should update memory strength based on outcome.

Examples:

- Successful workflow: strengthen/propose promotion.
- Failed workflow: record blocker/error and reduce confidence.
- Fixed bug: link error to resolution.
- User correction: supersede old assumption.
- Repeated recall usefulness: increase salience.

## Implemented API/tool surface for Phase 6

Implemented bridge/MCP tool names:

- `super_memory_working_memory_get`
- `super_memory_working_memory_set`
- `super_memory_attention_score`
- `super_memory_route_memory`
- `super_memory_parallel_save`
- `super_memory_recall_arbitrate`
- `super_memory_consolidation_cycle`
- `super_memory_conflict_resolve`
- `super_memory_promotion_candidates`
- `super_memory_feedback_outcome`

Implemented HTTP API endpoints:

- `GET /working-memory`
- `POST /working-memory`
- `POST /attention-score`
- `POST /route-memory`
- `POST /parallel-save`
- `POST /recall-arbitrate`
- `POST /consolidation-cycle`
- `POST /conflict-resolve`
- `GET /promotion-candidates`
- `POST /feedback-outcome`

## Safety constraints

Phase 6 must preserve these constraints:

- Do not let derived layers outrank Workspace Markdown for exact facts.
- Do not auto-promote secrets or unnecessary sensitive personal data.
- Do not enable background daemons/cloud sync/import/watch by default.
- Do not rewrite canonical memory silently.
- Do not enable OpenClaw hook skeletons until live hook API names/payloads are verified.
- Do not use real provider credentials in sandbox qualification.

## Implementation order

Recommended order:

1. Add working-memory data model and local storage.
2. Add attention scoring with deterministic baseline.
3. Add recall arbitration over existing recall results.
4. Add feedback outcome recording.
5. Add promotion-candidate detection.
6. Add consolidation cycle as manual command first.
7. Add optional OpenClaw hook integration only after hook API validation.
8. Add model-backed scoring/consolidation later, behind explicit configuration.

## Acceptance criteria

Phase 6 should be considered implemented only when:

- working memory can be set/read without writing durable memory unnecessarily
- attention score controls routing/TTL/promotion candidates
- canonical-first save invariant remains tested
- parallel projection reports per-layer success/failure
- recall arbitration explains which layer won and why
- conflict resolution preserves superseded/conflicting provenance
- consolidation can run manually and produce a bounded report
- sandbox OpenClaw smoke passes without touching host OpenClaw config

## Bottom line

The desired brain-like model is not four independent memories fighting each other. It is four specialized memory systems coordinated by an executive controller:

- Workspace Markdown remembers what is true.
- MemPalace remembers where procedures and projects live.
- Honcho remembers social/session context.
- NeuralMemory-style remembers associations and patterns.
- The cognitive controller decides attention, routing, recall arbitration, consolidation, promotion, and learning from outcomes.
