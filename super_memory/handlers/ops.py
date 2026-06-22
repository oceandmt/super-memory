"""Safety, diagnostics, sync, durable pack handlers."""
from __future__ import annotations

from .. import bridge
from .base import ToolHandler, SimpleHandler
from .core import _str, _int, _num, _bool, _array, _obj, CFG


def get_safety_handlers() -> list[ToolHandler]:
    return [
        SimpleHandler(
            "super_memory_safety_firewall",
            "Check content against input firewall.",
            bridge.run_safety_firewall,
            properties={"text": _str("Content to check")},
            required=["text"],
        ),
        SimpleHandler(
            "super_memory_evaluate_freshness",
            "Evaluate memory freshness by age in days.",
            bridge.evaluate_freshness,
            properties={"days_old": _num("Age in days", 0.0)},
        ),
        SimpleHandler(
            "super_memory_encrypt_content",
            "Encrypt memory content using Fernet key.",
            bridge.encrypt_content,
            properties={"content": _str("Content"), "key": _str("Encryption key")},
            required=["content"],
        ),
        SimpleHandler(
            "super_memory_extract_relations",
            "Extract causal/comparative/sequential relations from text.",
            bridge.extract_relations,
            properties={"text": _str("Text")},
            required=["text"],
        ),
        SimpleHandler(
            "super_memory_check_triggers",
            "Check content against auto-capture trigger patterns.",
            bridge.check_triggers,
            properties={"text": _str("Text")},
            required=["text"],
        ),
        SimpleHandler(
            "super_memory_detect_structure",
            "Detect structured content format.",
            bridge.detect_structure,
            properties={"text": _str("Text")},
            required=["text"],
        ),
        SimpleHandler(
            "super_memory_spreading_activation",
            "Run spreading activation for associative graph recall.",
            bridge.run_spreading_activation,
            properties={
                "query": _str("Query"),
                "anchor_neurons": _array("Anchor neuron IDs"),
                "max_hops": _int("Max hops", 3),
                "config_path": CFG,
            },
            required=["query"],
        ),
        SimpleHandler(
            "super_memory_get_eternal_context",
            "Get session-start context injection.",
            bridge.get_eternal_context,
            properties={"level": _int("Detail level 1-3", 1), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_dedup_check_content",
            "Check content against 3-tier dedup pipeline.",
            bridge.dedup_check_content,
            properties={"content": _str("Content"), "config_path": CFG},
            required=["content"],
        ),
        SimpleHandler(
            "super_memory_load_warm_cache",
            "Load activation cache for warm-start recall.",
            bridge.load_warm_cache,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_run_auto_deep",
            "Run full Auto Deep Engine — Audit/Qualify/Debug/Improve.",
            bridge.run_auto_deep,
            properties={"config_path": CFG},
        ),
    ]


def get_diagnostics_handlers() -> list[ToolHandler]:
    return [
        SimpleHandler(
            "super_memory_diagnostics",
            "Phase 8 diagnostics dashboard.",
            bridge.diagnostics,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_diagnostics_new",
            "Runtime diagnostics — component health + milestones.",
            bridge.diagnostics_new,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_cross_layer_health",
            "Audit cross-layer consistency.",
            bridge.cross_layer_health,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_cleanup_orphans",
            "Clean up cross-layer orphan projections (palace_drawers, honcho_events).",
            bridge.cleanup_orphans,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_memory_slot_contract",
            "Run Phase 8 memory-slot replacement contract.",
            bridge.memory_slot_contract,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_mcp_contract",
            "Verify MCP stdio tools/list exposure.",
            bridge.mcp_contract,
            properties={"profile": _str("Profile", "admin"), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_supervised_runtime_smoke",
            "Run local supervised runtime smoke.",
            bridge.supervised_runtime_smoke,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_classify_affect",
            "Classify arousal and valence of text.",
            bridge.classify_affect,
            properties={"text": _str("Text")},
            required=["text"],
        ),
        SimpleHandler(
            "super_memory_recall_by_affect",
            "Recall memories filtered by arousal threshold or valence.",
            bridge.recall_by_affect,
            properties={
                "min_arousal": _num("Min arousal 0-1"),
                "valence": _str("positive/negative/neutral"),
                "limit": _int("Max results", 20),
                "config_path": CFG,
            },
        ),
    ]


def get_sync_handlers() -> list[ToolHandler]:
    return [
        SimpleHandler(
            "super_memory_build_merkle_root",
            "Build Merkle root hash for all active memories.",
            bridge.build_merkle_root,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_diff_merkle_trees",
            "Diff local vs remote Merkle states.",
            bridge.diff_merkle_trees,
            properties={
                "local_root": _str("Local root hash"),
                "remote_root": _str("Remote root hash"),
                "remote_buckets": _obj("Remote buckets dict"),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_build_memory_proof",
            "Build Merkle proof for a specific memory.",
            bridge.build_memory_proof,
            properties={"memory_id": _str("Memory ID"), "config_path": CFG},
            required=["memory_id"],
        ),
        SimpleHandler(
            "super_memory_sync_status",
            "Show sync status only; cloud disabled.",
            bridge.sync_status,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_store_status",
            "Show store status only.",
            bridge.store_status,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_backfill_markdown_sqlite",
            "Admin repair: backfill missing workspace_markdown SQLite rows.",
            bridge.backfill_markdown_sqlite,
            properties={"limit": _int("Max items", 2000), "config_path": CFG},
        ),
    ]


def get_durable_pack_handlers() -> list[ToolHandler]:
    return [
        SimpleHandler(
            "super_memory_durable_pack",
            "Install curated shared/project durable memories.",
            bridge.durable_pack,
            properties={
                "pack_name": _str("Pack name", "openclaw-super-memory-durable-pack-v1"),
                "project": _str("Project", "super-memory"),
                "agents": _array("Agent IDs"),
                "qualify": _bool("Qualify after install", True),
                "debug": _bool("Debug after install", True),
                "dedupe": _bool("Dedupe", True),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_durable_pack_status",
            "Audit if the curated durable memory pack is installed.",
            bridge.durable_pack_status,
            properties={
                "pack_name": _str("Pack name", "openclaw-super-memory-durable-pack-v1"),
                "project": _str("Project", "super-memory"),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_durable_pack_audit",
            "Deep audit the OpenClaw durable memory pack.",
            bridge.durable_pack_audit,
            properties={
                "pack_name": _str("Pack name", "openclaw-super-memory-durable-pack-v1"),
                "project": _str("Project", "super-memory"),
                "fix": _bool("Fix issues", False),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_dreaming_repair",
            "Inspect dreaming artifacts and recommend repair actions.",
            bridge.dreaming_repair,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_leitner_due",
            "Return count of Leitner-due memories.",
            bridge.leitner_due,
            properties={"config_path": CFG},
        ),
    ]


def get_optional_heavy_handlers() -> list[ToolHandler]:
    """Phase 4 optional/heavy handlers that delegate to bridge.optional_heavy."""
    HEAVY_TOOLS = ["train", "import", "index", "sync", "telegram_backup", "visualize", "store", "watch"]
    handlers = []
    for name in HEAVY_TOOLS:
        handlers.append(SimpleHandler(
            f"super_memory_{name}",
            f"Phase 4 optional/heavy {name} skeleton; disabled unless explicitly configured.",
            bridge.optional_heavy,
            properties={
                "params": _obj(f"{name} parameters"),
                "config_path": CFG,
            },
        ))
    return handlers


def get_leitner_handlers() -> list[ToolHandler]:
    """Standalone leitner handlers for direct dispatch."""
    return [
        SimpleHandler(
            "super_memory_leitner_queue",
            "Return memories due for review (next_review <= now).",
            bridge.leitner_queue,
            properties={"limit": _int("Max items", 50), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_leitner_mark",
            "Record a Leitner review result.",
            bridge.leitner_mark,
            properties={"memory_id": _str("Memory ID"), "success": _bool("Success", True), "config_path": CFG},
            required=["memory_id"],
        ),
        SimpleHandler(
            "super_memory_leitner_schedule",
            "Manually set a memory's Leitner box.",
            bridge.leitner_schedule,
            properties={"memory_id": _str("Memory ID"), "box": _int("Box 0-4"), "config_path": CFG},
            required=["memory_id", "box"],
        ),
        SimpleHandler(
            "super_memory_leitner_stats",
            "Leitner box distribution + review stats.",
            bridge.leitner_stats,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_leitner_auto_seed",
            "Auto-assign Leitner boxes to unassigned memories.",
            bridge.leitner_auto_seed,
            properties={"limit": _int("Max items", 100), "config_path": CFG},
        ),
    ]


def get_local_handlers() -> list[ToolHandler]:
    """Local file/index/train handlers."""
    return [
        SimpleHandler(
            "super_memory_train_local",
            "Train from local text/rich docs under workspace only.",
            bridge.train_local,
            properties={
                "path": _str("File/dir path"),
                "domain_tag": _str("Domain tag", "local"),
                "recursive": _bool("Recursive", True),
                "limit": _int("Max items", 200),
                "save": _bool("Save to DB", True),
                "config_path": CFG,
            },
            required=["path"],
        ),
        SimpleHandler(
            "super_memory_index_local",
            "Index code symbols/imports under workspace only.",
            bridge.index_local,
            properties={
                "path": _str("Dir path"),
                "extensions": _array("File extensions"),
                "recursive": _bool("Recursive", True),
                "limit": _int("Max items", 500),
                "save": _bool("Save to DB", True),
                "config_path": CFG,
            },
            required=["path"],
        ),
        SimpleHandler(
            "super_memory_index_status",
            "Show local code index manifest status.",
            bridge.index_status,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_import_local",
            "Import local markdown/text/json/jsonl under workspace only.",
            bridge.import_local,
            properties={
                "path": _str("File/dir path"),
                "source_name": _str("Source name", "local-import"),
                "recursive": _bool("Recursive", True),
                "limit": _int("Max items", 200),
                "save": _bool("Save to DB", True),
                "config_path": CFG,
            },
            required=["path"],
        ),
        SimpleHandler(
            "super_memory_watch_scan",
            "One-shot file watch scan; no daemon.",
            bridge.watch_scan,
            properties={
                "directory": _str("Dir to scan"),
                "recursive": _bool("Recursive", True),
                "limit": _int("Max items", 200),
                "save": _bool("Save to DB", False),
                "config_path": CFG,
            },
            required=["directory"],
        ),
    ]
