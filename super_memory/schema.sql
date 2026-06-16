-- Super-Memory Unified Schema v1.0
-- Single source of truth for all tables
-- Usage: python -m super_memory.migrations

-- ============================================================================
-- CORE MEMORY STORAGE
-- ============================================================================

-- Main memories table (canonical storage across all layers)
CREATE TABLE IF NOT EXISTS memories (
    id TEXT NOT NULL,
    layer TEXT NOT NULL DEFAULT 'workspace_markdown',
    content TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'context',
    scope TEXT NOT NULL DEFAULT 'session',
    agent_id TEXT,
    session_id TEXT,
    project TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    source TEXT,
    trust_score REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (id, layer)
);

-- ============================================================================
-- HONCHO SUBSYSTEM (peer/session intelligence)
-- ============================================================================

-- Honcho events (peer observations)
CREATE TABLE IF NOT EXISTS honcho_events (
    id TEXT PRIMARY KEY,
    memory_id TEXT,
    workspace TEXT NOT NULL,
    session_id TEXT,
    observer_peer_id TEXT NOT NULL,
    observed_peer_id TEXT,
    content TEXT NOT NULL,
    source TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Honcho conclusions (derived insights about peers)
CREATE TABLE IF NOT EXISTS honcho_conclusions (
    id TEXT PRIMARY KEY,
    about_peer_id TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.8,
    source TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Honcho peers (participant registry)
CREATE TABLE IF NOT EXISTS honcho_peers (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    display_name TEXT,
    model_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================================
-- SESSION MANAGEMENT
-- ============================================================================

-- Sessions (agent-session metadata)
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT,
    peer_id TEXT,
    status TEXT DEFAULT 'active',
    current_project TEXT,
    current_goal TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Session archives (compressed summaries)
CREATE TABLE IF NOT EXISTS session_archives (
    id TEXT PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    agent_id TEXT,
    summary TEXT,
    event_count INTEGER DEFAULT 0,
    key_decisions_json TEXT NOT NULL DEFAULT '[]',
    open_blockers_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================================
-- CROSS-AGENT COORDINATION
-- ============================================================================

-- Handoff bundles (agent-to-agent context transfer)
CREATE TABLE IF NOT EXISTS handoff_bundles (
    id TEXT PRIMARY KEY,
    from_agent TEXT,
    to_agent TEXT,
    session_id TEXT,
    title TEXT,
    summary TEXT,
    context_json TEXT NOT NULL DEFAULT '{}',
    memory_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    claimed_at TEXT,
    completed_at TEXT
);

-- Cross-agent claims (semantic fact extraction)
CREATE TABLE IF NOT EXISTS cross_agent_claims (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    polarity TEXT DEFAULT 'positive',
    agent_id TEXT,
    memory_id TEXT,
    status TEXT DEFAULT 'active',
    resolution TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Cross-agent conflicts (detected contradictions)
CREATE TABLE IF NOT EXISTS cross_agent_conflicts (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    agent_a TEXT NOT NULL,
    agent_b TEXT NOT NULL,
    memory_a_id TEXT,
    memory_b_id TEXT,
    content_a TEXT,
    content_b TEXT,
    status TEXT DEFAULT 'open',
    resolution TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);

-- ============================================================================
-- MEMPALACE SUBSYSTEM (spatial memory projection)
-- ============================================================================

-- Palace drawers (spatial organization)
CREATE TABLE IF NOT EXISTS palace_drawers (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    wing TEXT NOT NULL,
    room TEXT NOT NULL,
    hall TEXT NOT NULL,
    content TEXT NOT NULL,
    checksum TEXT NOT NULL,
    source TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================================
-- GRAPH SUBSYSTEM (associative links)
-- ============================================================================

-- Cognitive synapses (unified graph: neural+associative edges)
-- Replaces legacy graph_edges; single source of truth for all graph operations.
CREATE TABLE IF NOT EXISTS cognitive_synapses (
    id TEXT PRIMARY KEY,
    source_neuron_id TEXT NOT NULL,
    target_neuron_id TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT 'associative',
    weight REAL NOT NULL DEFAULT 0.5,
    confidence REAL NOT NULL DEFAULT 0.5,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_neuron_id, target_neuron_id, relation)
);

-- Legacy graph_edges kept for backward compatibility; new writes go to cognitive_synapses.
CREATE TABLE IF NOT EXISTS graph_edges (
    id TEXT PRIMARY KEY,
    source_memory_id TEXT NOT NULL,
    target_memory_id TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT 'associative',
    weight REAL NOT NULL DEFAULT 1.0,
    confidence REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================================
-- PERFORMANCE INDEXES
-- ============================================================================

-- Memories indexes
CREATE INDEX IF NOT EXISTS idx_memories_agent_created ON memories(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_session_created ON memories(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_scope_created ON memories(scope, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_type_scope ON memories(type, scope);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project);
CREATE INDEX IF NOT EXISTS idx_memories_content ON memories(content);

-- Honcho indexes
CREATE INDEX IF NOT EXISTS idx_honcho_events_session_created ON honcho_events(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_honcho_events_observer_created ON honcho_events(observer_peer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_honcho_events_observed_created ON honcho_events(observed_peer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_honcho_events_memory ON honcho_events(memory_id);
CREATE INDEX IF NOT EXISTS idx_honcho_conclusions_peer ON honcho_conclusions(about_peer_id, created_at DESC);

-- Session indexes
CREATE INDEX IF NOT EXISTS idx_sessions_agent_status ON sessions(agent_id, status);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_archives_agent_created ON session_archives(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_archives_session ON session_archives(session_id);

-- Handoff indexes
CREATE INDEX IF NOT EXISTS idx_handoff_to_status ON handoff_bundles(to_agent, status);
CREATE INDEX IF NOT EXISTS idx_handoff_from_created ON handoff_bundles(from_agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_handoff_session ON handoff_bundles(session_id);

-- Claim/conflict indexes
CREATE INDEX IF NOT EXISTS idx_claims_agent_subject ON cross_agent_claims(agent_id, subject);
CREATE INDEX IF NOT EXISTS idx_claims_memory ON cross_agent_claims(memory_id);
CREATE INDEX IF NOT EXISTS idx_claims_status ON cross_agent_claims(status);
CREATE INDEX IF NOT EXISTS idx_conflicts_agents ON cross_agent_conflicts(agent_a, agent_b);
CREATE INDEX IF NOT EXISTS idx_conflicts_status ON cross_agent_conflicts(status);

-- MemPalace indexes
CREATE INDEX IF NOT EXISTS idx_palace_memory ON palace_drawers(memory_id);
CREATE INDEX IF NOT EXISTS idx_palace_location ON palace_drawers(wing, room, hall);
CREATE INDEX IF NOT EXISTS idx_palace_created ON palace_drawers(created_at DESC);

-- Graph indexes
CREATE INDEX IF NOT EXISTS idx_graph_source ON graph_edges(source_memory_id);
CREATE INDEX IF NOT EXISTS idx_graph_target ON graph_edges(target_memory_id);
CREATE INDEX IF NOT EXISTS idx_graph_relation ON graph_edges(relation);
CREATE INDEX IF NOT EXISTS idx_graph_weight ON graph_edges(weight DESC);

-- Cognitive synapse indexes (unified graph)
CREATE INDEX IF NOT EXISTS idx_cognitive_synapses_source ON cognitive_synapses(source_neuron_id);
CREATE INDEX IF NOT EXISTS idx_cognitive_synapses_target ON cognitive_synapses(target_neuron_id);
CREATE INDEX IF NOT EXISTS idx_cognitive_synapses_relation ON cognitive_synapses(relation);
CREATE INDEX IF NOT EXISTS idx_cognitive_synapses_weight ON cognitive_synapses(weight DESC);

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Keep session updated_at fresh
CREATE TRIGGER IF NOT EXISTS trg_sessions_updated_at
AFTER UPDATE ON sessions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE sessions SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================================
-- HEALTH VIEWS
-- ============================================================================

CREATE VIEW IF NOT EXISTS v_agent_activity AS
SELECT
    m.agent_id,
    COUNT(*) AS memory_count,
    MAX(m.created_at) AS recent_memory,
    COUNT(DISTINCT m.session_id) AS session_count
FROM memories m
WHERE m.agent_id IS NOT NULL
GROUP BY m.agent_id;

CREATE VIEW IF NOT EXISTS v_session_health AS
SELECT
    s.id AS session_id,
    s.agent_id,
    s.status,
    s.started_at,
    s.updated_at,
    COUNT(h.id) AS event_count
FROM sessions s
LEFT JOIN honcho_events h ON h.session_id = s.id
GROUP BY s.id, s.agent_id, s.status, s.started_at, s.updated_at;
