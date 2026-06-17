"""Codebase symbol indexer for Super Memory."""
from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import bridge
from .config import load_config
from .models import MemoryScope, MemoryType
from .storage import SuperMemoryStore

CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cc"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_limit(limit: int, default: int = 500, maximum: int = 5000) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(maximum, value))


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


def _iter_code_files(path: Path, extensions: set[str], recursive: bool, limit: int) -> Iterable[Path]:
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
            # Skip common generated/vendor dirs
            parts = set(file_path.parts)
            if parts & {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}:
                continue
            count += 1
            yield file_path


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _init_index_manifest(store: SuperMemoryStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS code_index_manifest (
                path TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                symbols_json TEXT NOT NULL,
                imports_json TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
            """
        )


def _extract_python_symbols(text: str) -> dict[str, list[str]]:
    symbols = {"classes": [], "functions": [], "imports": []}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return symbols
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols["classes"].append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols["functions"].append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                symbols["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                symbols["imports"].append(f"{module}.{alias.name}" if module else alias.name)
    return symbols


def _extract_generic_symbols(text: str, ext: str) -> dict[str, list[str]]:
    symbols = {"classes": [], "functions": [], "imports": []}
    # JS/TS/class-like
    symbols["classes"] = re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", text)
    symbols["functions"] = re.findall(r"\b(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?:\{|=>)", text)
    symbols["imports"] = re.findall(r"\bimport\s+(?:.*?\s+from\s+)?['\"]([^'\"]+)['\"]", text)
    symbols["imports"] += re.findall(r"\brequire\(['\"]([^'\"]+)['\"]\)", text)
    # Go/Rust/Java/C rough patterns
    symbols["functions"] += re.findall(r"\b(?:func|fn|public\s+\w+|private\s+\w+|protected\s+\w+|static\s+\w+)\s+([A-Za-z_][A-Za-z0-9_]*)", text)
    return {k: sorted(set(v)) for k, v in symbols.items()}


def _extract_symbols(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".py":
        return _extract_python_symbols(text)
    return _extract_generic_symbols(text, path.suffix.lower())


def index_codebase(path: str, *, extensions: list[str] | None = None, recursive: bool = True, limit: int = 500, save: bool = True, config_path: str | None = None) -> dict[str, Any]:
    """Index code symbols/imports and optionally save one memory per file."""
    limit = _bounded_limit(limit)
    exts = set(extensions or CODE_EXTENSIONS)
    target, cfg = _resolve_under_workspace(path, config_path)
    store = SuperMemoryStore(cfg)
    _init_index_manifest(store)
    files = list(_iter_code_files(target, exts, recursive, limit))
    indexed = []
    saved_count = 0
    skipped_count = 0

    for file_path in files:
        rel = str(file_path.relative_to(Path(cfg.workspace_root).resolve()))
        digest = _file_hash(file_path)
        symbols = _extract_symbols(file_path)
        imports = symbols.get("imports", [])
        symbol_count = len(symbols.get("classes", [])) + len(symbols.get("functions", []))
        changed = True
        with store.connect() as conn:
            old = conn.execute("SELECT sha256 FROM code_index_manifest WHERE path=?", (rel,)).fetchone()
            if old and old["sha256"] == digest:
                changed = False
        if not changed:
            skipped_count += 1
            indexed.append({"path": rel, "changed": False, "symbols": symbol_count, "imports": len(imports), "saved": False})
            continue
        with store.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO code_index_manifest (path, sha256, symbols_json, imports_json, indexed_at) VALUES (?, ?, ?, ?, ?)",
                (rel, digest, json.dumps(symbols, ensure_ascii=False), json.dumps(imports, ensure_ascii=False), _now()),
            )
        saved = False
        if save:
            content = (
                f"Code index for {rel}: classes={symbols.get('classes', [])[:20]}, "
                f"functions={symbols.get('functions', [])[:30]}, imports={imports[:30]}"
            )
            result = bridge.remember({
                "content": content,
                "type": MemoryType.CONTEXT.value,
                "scope": MemoryScope.PROJECT.value,
                "tags": ["code-index", f"file:{rel}", f"ext:{file_path.suffix.lower()}"],
                "source": rel,
                "metadata": {"flow": "code_index", "sha256": digest, "symbols": symbols, "imports": imports},
            }, config_path=config_path)
            saved = bool(result.get("results") and result["results"][0].get("ok"))
            if saved:
                saved_count += 1
        indexed.append({"path": rel, "changed": True, "symbols": symbol_count, "imports": len(imports), "saved": saved})

    return {"ok": True, "enabled": True, "mode": "local_code_index", "path": str(target), "files": indexed, "saved_records": saved_count, "skipped_records": skipped_count, "extensions": sorted(exts)}


def index_status(config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _init_index_manifest(store)
    with store.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM code_index_manifest").fetchone()["c"]
        recent = conn.execute("SELECT path, sha256, indexed_at FROM code_index_manifest ORDER BY indexed_at DESC LIMIT 20").fetchall()
    return {"ok": True, "enabled": True, "mode": "local_code_index", "indexed_files": count, "recent": [dict(r) for r in recent]}
