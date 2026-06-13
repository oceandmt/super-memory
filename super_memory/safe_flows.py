from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import load_config
from .models import MemoryScope, MemoryType
from .sanitize import sanitize_prompt
from .storage import SuperMemoryStore
from . import bridge

TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
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


def train(path: str, *, domain_tag: str = "local", recursive: bool = True, limit: int = 200, max_chunks_per_file: int = 20, save: bool = True, config_path: str | None = None) -> dict[str, Any]:
    limit = _bounded_limit(limit)
    max_chunks_per_file = _bounded_limit(max_chunks_per_file, default=20, maximum=200)
    target, cfg = _resolve_under_workspace(path, config_path)
    files = list(_iter_files(target, TEXT_EXTENSIONS, recursive=recursive, limit=limit))
    items = []
    saved_count = 0
    for file_path in files:
        rel = str(file_path.relative_to(Path(cfg.workspace_root).resolve()))
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        file_chunks = _chunks(text)[:max_chunks_per_file]
        file_item = {"path": rel, "sha256": _file_hash(file_path), "chunks": len(file_chunks), "saved": 0}
        if save:
            for idx, chunk in enumerate(file_chunks, start=1):
                payload = {
                    "content": sanitize_prompt(chunk, max_chars=3000),
                    "type": MemoryType.CONTEXT.value,
                    "scope": MemoryScope.PROJECT.value,
                    "tags": ["trained", f"domain:{domain_tag}", f"file:{rel}", f"chunk:{idx}"],
                    "source": rel,
                    "metadata": {"flow": "train", "domain_tag": domain_tag, "chunk_index": idx, "chunks": len(file_chunks), "sha256": file_item["sha256"]},
                }
                result = bridge.remember(payload, config_path=config_path)
                if result["results"] and result["results"][0]["ok"]:
                    saved_count += 1
                    file_item["saved"] += 1
        items.append(file_item)
    return {"ok": True, "enabled": True, "mode": "local_text_markdown", "path": str(target), "files": items, "saved_chunks": saved_count, "external_backends": "disabled"}


def import_local(path: str, *, source_name: str = "local-import", recursive: bool = True, limit: int = 200, save: bool = True, config_path: str | None = None) -> dict[str, Any]:
    limit = _bounded_limit(limit)
    target, cfg = _resolve_under_workspace(path, config_path)
    files = list(_iter_files(target, IMPORT_EXTENSIONS, recursive=recursive, limit=limit))
    imported = []
    saved_count = 0
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
        file_item = {"path": rel, "records": len(records), "saved": 0}
        if save:
            for idx, record in enumerate(records[:limit], start=1):
                content = record.get("content") or record.get("text") or record.get("message") or json.dumps(record, ensure_ascii=False)
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
                if result["results"] and result["results"][0]["ok"]:
                    saved_count += 1
                    file_item["saved"] += 1
        imported.append(file_item)
    return {"ok": True, "enabled": True, "mode": "local_import", "path": str(target), "files": imported, "saved_records": saved_count, "external_backends": "disabled"}


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
        saved = import_local(str(target), source_name="watch-scan", recursive=recursive, limit=limit, save=True, config_path=config_path)
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
