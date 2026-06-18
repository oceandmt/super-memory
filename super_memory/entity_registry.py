from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .config import load_config
from .migrations import run_migrations
from .storage import SuperMemoryStore


def ensure_entity_tables(config_path: str | Path | None = None) -> None:
    cfg = load_config(config_path)
    run_migrations(cfg)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS entity_registry ("
            "id TEXT PRIMARY KEY, kind TEXT NOT NULL, canonical_name TEXT NOT NULL, "
            "aliases_json TEXT NOT NULL DEFAULT '[]', metadata_json TEXT NOT NULL DEFAULT '{}', "
            "created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_registry_kind ON entity_registry(kind)")
        conn.commit()


def upsert_entity(kind: str, canonical_name: str, aliases: list[str] | None = None, metadata: dict[str, Any] | None = None, config_path: str | Path | None = None) -> dict[str, Any]:
    ensure_entity_tables(config_path)
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    aliases = aliases or []
    metadata = metadata or {}
    with store.connect() as conn:
        existing = conn.execute("SELECT * FROM entity_registry WHERE kind = ? AND canonical_name = ?", (kind, canonical_name)).fetchone()
        if existing:
            merged_aliases = sorted(set(json.loads(existing["aliases_json"]) + aliases))
            merged_meta = {**json.loads(existing["metadata_json"]), **metadata}
            conn.execute(
                "UPDATE entity_registry SET aliases_json = ?, metadata_json = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(merged_aliases), json.dumps(merged_meta), existing["id"]),
            )
            entity_id = existing["id"]
        else:
            entity_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO entity_registry (id, kind, canonical_name, aliases_json, metadata_json) VALUES (?, ?, ?, ?, ?)",
                (entity_id, kind, canonical_name, json.dumps(sorted(set(aliases))), json.dumps(metadata)),
            )
        conn.commit()
    return {"ok": True, "id": entity_id, "kind": kind, "canonical_name": canonical_name}


def resolve_entity(name: str, kind: str | None = None, config_path: str | Path | None = None) -> dict[str, Any]:
    ensure_entity_tables(config_path)
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM entity_registry" + (" WHERE kind = ?" if kind else ""), ((kind,) if kind else ())).fetchall()
    for row in rows:
        aliases = json.loads(row["aliases_json"])
        if name == row["canonical_name"] or name in aliases:
            return {"ok": True, "id": row["id"], "kind": row["kind"], "canonical_name": row["canonical_name"], "aliases": aliases}
    return {"ok": False, "name": name, "kind": kind}


def collision_report(config_path: str | Path | None = None) -> dict[str, Any]:
    ensure_entity_tables(config_path)
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    seen: dict[str, list[str]] = {}
    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM entity_registry").fetchall()
    for row in rows:
        names = [row["canonical_name"], *json.loads(row["aliases_json"])]
        for name in names:
            seen.setdefault(name.lower(), []).append(row["id"])
    collisions = {name: ids for name, ids in seen.items() if len(set(ids)) > 1}
    return {"ok": not collisions, "collisions": collisions, "count": len(collisions)}
