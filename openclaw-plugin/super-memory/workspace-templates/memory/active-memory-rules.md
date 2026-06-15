# Active Memory Rules

Treat this as active doctrine for Super Memory deployments.

## Canonical Layers

1. **Daily markdown**: `memory/YYYY-MM-DD.md`
   - Append-only session notes
   - Human-readable chronological record

2. **Curated markdown**: `MEMORY.md`
   - Stable long-term recap
   - Orientation facts and durable summaries

3. **Super Memory plugin**
   - Associative recall and durable memory graph
   - Decisions, preferences, TODOs, blockers, workflows, insights

## Save Rules

Save durable items when a turn produces:

- A decision
- A user preference
- A workflow or rule change
- A blocker or resolved blocker
- A durable insight
- A TODO or commitment
- A project milestone

Do not save:

- Secrets or credentials unless explicitly requested
- Raw transcript dumps
- Temporary debugging noise
- Every small message

## Recommended Save Order

1. Append concise note to `memory/YYYY-MM-DD.md`
2. Store atomic memory with `super_memory_remember`
3. Promote stable broad summaries to `MEMORY.md`
4. Run `super_memory_consolidate` periodically

## Retrieval Rules

Before answering prior-work questions:

1. Use `super_memory_recall` for durable meaning
2. Use `memory_search` / local files for exact markdown records
3. Verify exact paths, commands, config values, and quoted text from source files

## Language Rule

Default to the user's preferred language in `USER.md`; keep technical identifiers in English.
