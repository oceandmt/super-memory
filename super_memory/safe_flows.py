from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import bridge
from .config import load_config
from .extractors import available_extractors, extract_text
from .ingest import is_ignored_source_path
from .models import MemoryScope, MemoryType
from .sanitize import sanitize_prompt
from .storage import SuperMemoryStore

TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".rst"}
RICH_EXTENSIONS = {".pdf", ".docx", ".pptx", ".html", ".htm", ".xlsx", ".csv"}
TRAIN_EXTENSIONS = TEXT_EXTENSIONS | RICH_EXTENSIONS
IMPORT_EXTENSIONS = TEXT_EXTENSIONS | {".json", ".jsonl"}


def _bounded_limit(limit: int, default: int = 200, maximum: int = 1000) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(maximum, value))

def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, tuple):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        return [value]
    return []

def _object_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolve_under_workspace(path: str | None, config_path: str | None = None) -> tuple[Path, Any]:
    cfg = load_config(config_path)
    root = Path(cfg.workspace_root).resolve()
    candidate = Path(path or root)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path outside configured workspace_root: {resolved}") from exc
    return resolved, cfg


def _iter_files(path: Path, extensions: set[str], recursive: bool = True, limit: int = 200) -> Iterable[Path]:
    limit = _bounded_limit(limit)
    if path.is_file():
        if path.suffix.lower() in extensions:
            yield path
        return
    pattern = "**/*" if recursive else "*"
    count = 0
    for file_path in sorted(path.glob(pattern)):
        if count >= limit:
            break
        # Skip build/vendor artifacts (.venv, site-packages, node_modules,
        # .dist-info, etc). Without this, train/import walked vendored deps and
        # ingested them as "memories" (root cause of the .venv-yt-dlp junk rows).
        if is_ignored_source_path(str(file_path)):
            continue
        if file_path.is_file() and file_path.suffix.lower() in extensions:
            count += 1
            yield file_path


def _chunks(text: str, max_chars: int = 1200) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs or [text]:
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            current = para[:max_chars]
    if current:
        chunks.append(current)
    return chunks


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _init_ingest_manifest(store: SuperMemoryStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ingest_manifest (
                key TEXT PRIMARY KEY,
                flow TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                chunk_index INTEGER NOT NULL DEFAULT 0,
                saved_memory_id TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )

def _manifest_seen(store: SuperMemoryStore, key: str) -> bool:
    _init_ingest_manifest(store)
    with store.connect() as conn:
        return conn.execute("SELECT key FROM ingest_manifest WHERE key=?", (key,)).fetchone() is not None

def _manifest_record(store: SuperMemoryStore, *, key: str, flow: str, path: str, sha256: str, chunk_index: int, memory_id: str | None) -> None:
    _init_ingest_manifest(store)
    with store.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ingest_manifest (key, flow, path, sha256, chunk_index, saved_memory_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, flow, path, sha256, chunk_index, memory_id, datetime.now(timezone.utc).isoformat()),
        )


def train(path: str, *, domain_tag: str = "local", recursive: bool = True, limit: int = 200, max_chunks_per_file: int = 20, save: bool = True, config_path: str | None = None) -> dict[str, Any]:
    limit = _bounded_limit(limit)
    max_chunks_per_file = _bounded_limit(max_chunks_per_file, default=20, maximum=200)
    target, cfg = _resolve_under_workspace(path, config_path)
    store = SuperMemoryStore(cfg)
    files = list(_iter_files(target, TRAIN_EXTENSIONS, recursive=recursive, limit=limit))
    items = []
    saved_count = 0
    skipped_count = 0
    extraction_failures = 0
    for file_path in files:
        rel = str(file_path.relative_to(Path(cfg.workspace_root).resolve()))
        text = extract_text(file_path)
        if text is None:
            extraction_failures += 1
            continue
        file_chunks = _chunks(text)[:max_chunks_per_file]
        file_item = {"path": rel, "sha256": _file_hash(file_path), "chunks": len(file_chunks), "saved": 0, "skipped": 0}
        if save:
            for idx, chunk in enumerate(file_chunks, start=1):
                key = hashlib.sha256(f"train\0{rel}\0{file_item['sha256']}\0{idx}\0{chunk}".encode("utf-8")).hexdigest()
                if _manifest_seen(store, key):
                    skipped_count += 1
                    file_item["skipped"] += 1
                    continue
                payload = {
                    "content": sanitize_prompt(chunk, max_chars=3000),
                    "type": MemoryType.CONTEXT.value,
                    "scope": MemoryScope.PROJECT.value,
                    "tags": ["trained", f"domain:{domain_tag}", f"file:{rel}", f"chunk:{idx}"],
                    "source": rel,
                    "metadata": {"flow": "train", "domain_tag": domain_tag, "chunk_index": idx, "chunks": len(file_chunks), "sha256": file_item["sha256"]},
                }
                result = bridge.remember(payload, config_path=config_path)
                # bridge.remember() returns no "results" key when the WriteGate
                # blocks the write (result["ok"] is False in that case) -- only
                # the allow-path includes "results"/"record". Guard with .get()
                # so a blocked/quarantined write doesn't crash the whole flow.
                if result.get("results") and result["results"][0].get("ok"):
                    saved_count += 1
                    file_item["saved"] += 1
                    _manifest_record(store, key=key, flow="train", path=rel, sha256=file_item["sha256"], chunk_index=idx, memory_id=result["record"]["id"])
        items.append(file_item)
    return {"ok": True, "enabled": True, "mode": "local_text_rich_documents", "path": str(target), "files": items, "saved_chunks": saved_count, "skipped_chunks": skipped_count, "extraction_failures": extraction_failures, "extractors": available_extractors(), "external_backends": "disabled"}


def import_local(path: str, *, source_name: str = "local-import", recursive: bool = True, limit: int = 200, save: bool = True, config_path: str | None = None) -> dict[str, Any]:
    limit = _bounded_limit(limit)
    target, cfg = _resolve_under_workspace(path, config_path)
    store = SuperMemoryStore(cfg)
    files = list(_iter_files(target, IMPORT_EXTENSIONS, recursive=recursive, limit=limit))
    imported = []
    saved_count = 0
    skipped_count = 0
    for file_path in files:
        rel = str(file_path.relative_to(Path(cfg.workspace_root).resolve()))
        records: list[dict[str, Any]] = []
        if file_path.suffix.lower() in TEXT_EXTENSIONS:
            records = [{"content": file_path.read_text(encoding="utf-8", errors="ignore"), "type": MemoryType.CONTEXT.value}]
        elif file_path.suffix.lower() == ".jsonl":
            for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip():
                    obj = json.loads(line)
                    records.append(obj if isinstance(obj, dict) else {"content": str(obj)})
        elif file_path.suffix.lower() == ".json":
            obj = json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(obj, list):
                records = [x if isinstance(x, dict) else {"content": str(x)} for x in obj]
            elif isinstance(obj, dict) and isinstance(obj.get("memories"), list):
                records = [x if isinstance(x, dict) else {"content": str(x)} for x in obj["memories"]]
            else:
                records = [obj if isinstance(obj, dict) else {"content": str(obj)}]
        digest = _file_hash(file_path)
        file_item = {"path": rel, "sha256": digest, "records": len(records), "saved": 0, "skipped": 0}
        if save:
            for idx, record in enumerate(records[:limit], start=1):
                content = record.get("content") or record.get("text") or record.get("message") or json.dumps(record, ensure_ascii=False)
                key = hashlib.sha256(f"import\0{source_name}\0{rel}\0{digest}\0{idx}\0{content}".encode("utf-8")).hexdigest()
                if _manifest_seen(store, key):
                    skipped_count += 1
                    file_item["skipped"] += 1
                    continue
                payload = {
                    "content": content,
                    "type": record.get("type", MemoryType.CONTEXT.value),
                    "scope": record.get("scope", MemoryScope.PROJECT.value),
                    "agent_id": record.get("agent_id", "lucas"),
                    "project": record.get("project"),
                    "tags": _string_list(record.get("tags")) + ["imported", f"source:{source_name}", f"file:{rel}"],
                    "source": record.get("source", rel),
                    "trust_score": record.get("trust_score"),
                    "metadata": {**_object_dict(record.get("metadata")), "flow": "import", "source_name": source_name, "import_index": idx},
                }
                result = bridge.remember(payload, config_path=config_path)
                if result.get("results") and result["results"][0].get("ok"):
                    saved_count += 1
                    file_item["saved"] += 1
                    _manifest_record(store, key=key, flow="import", path=rel, sha256=digest, chunk_index=idx, memory_id=result["record"]["id"])
                elif (result.get("write_gate") or {}).get("action") == "skip_duplicate":
                    skipped_count += 1
                    file_item["skipped"] += 1
                    _manifest_record(store, key=key, flow="import", path=rel, sha256=digest, chunk_index=idx, memory_id=(result.get("write_gate") or {}).get("duplicate_id") or "duplicate")
        imported.append(file_item)
    return {"ok": True, "enabled": True, "mode": "local_import", "path": str(target), "files": imported, "saved_records": saved_count, "skipped_records": skipped_count, "external_backends": "disabled"}


def watch_scan(directory: str, *, recursive: bool = True, limit: int = 200, save: bool = False, config_path: str | None = None) -> dict[str, Any]:
    limit = _bounded_limit(limit)
    target, cfg = _resolve_under_workspace(directory, config_path)
    store = SuperMemoryStore(cfg)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watch_manifest (
                path TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                scanned_at TEXT NOT NULL
            )
            """
        )
    files = list(_iter_files(target, IMPORT_EXTENSIONS, recursive=recursive, limit=limit))
    changed = []
    unchanged = 0
    with store.connect() as conn:
        for file_path in files:
            rel = str(file_path.relative_to(Path(cfg.workspace_root).resolve()))
            digest = _file_hash(file_path)
            stat = file_path.stat()
            old = conn.execute("SELECT sha256 FROM watch_manifest WHERE path=?", (rel,)).fetchone()
            if old and old["sha256"] == digest:
                unchanged += 1
                continue
            changed.append({"path": rel, "sha256": digest, "size": stat.st_size, "mtime": stat.st_mtime})
            conn.execute(
                "INSERT OR REPLACE INTO watch_manifest (path, sha256, size, mtime, scanned_at) VALUES (?, ?, ?, ?, ?)",
                (rel, digest, stat.st_size, stat.st_mtime, datetime.now(timezone.utc).isoformat()),
            )
    saved = None
    if save and changed:
        saved_items = []
        total_saved = 0
        total_skipped = 0
        for item in changed:
            one = import_local(item["path"], source_name="watch-scan", recursive=False, limit=limit, save=True, config_path=config_path)
            saved_items.append(one)
            total_saved += int(one.get("saved_records", 0))
            total_skipped += int(one.get("skipped_records", 0))
        saved = {"ok": True, "files": saved_items, "saved_records": total_saved, "skipped_records": total_skipped}
    return {"ok": True, "enabled": True, "mode": "one_shot_scan", "path": str(target), "changed": changed, "unchanged": unchanged, "saved": saved, "daemon": False, "external_backends": "disabled"}


def sync_status(config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    exists = store.path.exists()
    return {"ok": True, "enabled": False, "mode": "status_only", "sqlite_path": str(store.path), "sqlite_exists": exists, "cloud_sync": "disabled unless explicitly configured in a future backend", "pending_changes": "not tracked for remote sync"}


def store_status(config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    root = Path(cfg.workspace_root)
    return {"ok": True, "enabled": False, "mode": "status_only", "workspace_root": str(root), "community_store": "disabled", "export_available": False, "import_available": "local train/import flows only"}
