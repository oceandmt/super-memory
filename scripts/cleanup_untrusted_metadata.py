#!/usr/bin/env python3
"""
Cleanup migration: remove untrusted metadata fields from Super Memory DB + canonical markdown.

Phase 1 — metadata_json: remove untrusted keys from DB memories
Phase 2 — canonical markdown: redact raw "Conversation info / Sender (untrusted metadata)" blocks
Phase 3 — rebuild FTS + indices

Usage:
  python3 cleanup_untrusted_metadata.py            # dry-run
  python3 cleanup_untrusted_metadata.py --apply    # apply + rebuild
  python3 cleanup_untrusted_metadata.py --apply --skip-rebuild
"""

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# ── Keys to remove from metadata_json ──────────────────────────────────────

UNTRUSTED_KEYS = {
    "chat_id",
    "sender_id",
    "message_id",
    "topic_id",
    "thread_label",
    "conversation_label",
    "senderName",
    "senderBlock",
}

# ── Patterns for canonical markdown raw blocks ─────────────────────────────
# Format: `user: Conversation info (untrusted metadata):\n```json\n{...}\n````
# Format: `assistant: Sender (untrusted metadata):\n```json\n{...}\n````

MD_RAW_BLOCK_PATTERN = re.compile(
    r'(?:^|\n)((?:user|assistant|System|system):\s*'
    r'(?:Conversation info|Sender)\s*\(untrusted metadata\):\s*\n'
    r'```json\s*\n\{.*?\n\})',
    re.DOTALL | re.MULTILINE,
)

# Also catch inline format:
# `Conversation info (untrusted metadata): ```json { ... } ````
MD_INLINE_BLOCK_PATTERN = re.compile(
    r'(?:Conversation info|Sender)\s*\(untrusted metadata\):\s*'
    r'```json\s*\{.*?\}\s*```',
    re.DOTALL,
)

# ── Helpers ─────────────────────────────────────────────────────────────────


def strip_untrusted_from_metadata(metadata_str: str) -> tuple[str | None, bool]:
    """Remove UNTRUSTED_KEYS from a JSON metadata string. Returns (cleaned_str, changed)."""
    if not metadata_str or metadata_str.strip() in ("", "{}", "null"):
        return metadata_str, False
    try:
        obj = json.loads(metadata_str)
    except (json.JSONDecodeError, TypeError):
        return metadata_str, False
    if not isinstance(obj, dict):
        return metadata_str, False

    changed = False
    for key in list(UNTRUSTED_KEYS):
        if key in obj:
            del obj[key]
            changed = True

    # Clean structured_fields entries whose name is an untrusted key
    if changed and "structured_fields" in obj and isinstance(obj["structured_fields"], list):
        obj["structured_fields"] = [
            sf for sf in obj["structured_fields"]
            if sf.get("name") not in UNTRUSTED_KEYS
        ]

    if not changed:
        return None, False
    return json.dumps(obj, ensure_ascii=False), True


def redact_markdown_raw_blocks(text: str) -> tuple[str, bool]:
    """Redact raw untrusted metadata blocks from markdown content."""
    changed = False
    new_text, n1 = MD_RAW_BLOCK_PATTERN.subn(
        '', text
    )
    if n1 > 0:
        changed = True
    new_text, n2 = MD_INLINE_BLOCK_PATTERN.subn(
        '', new_text
    )
    if n2 > 0:
        changed = True
    return new_text, changed


# ── Phase 1 ─────────────────────────────────────────────────────────────────


def phase1_metadata_json(conn, dry_run: bool) -> int:
    """Remove untrusted keys from metadata_json in DB."""
    rows = conn.execute(
        "SELECT id, metadata_json FROM memories WHERE metadata_json IS NOT NULL"
    ).fetchall()
    cleaned = 0
    for rid, mj in rows:
        stripped, changed = strip_untrusted_from_metadata(mj)
        if not changed:
            continue
        cleaned += 1
        if not dry_run:
            conn.execute(
                "UPDATE memories SET metadata_json=? WHERE id=?",
                (stripped, rid),
            )
    conn.commit()
    return cleaned


# ── Phase 2 ─────────────────────────────────────────────────────────────────


def phase2_canonical_markdown(dry_run: bool) -> tuple[int, list[str]]:
    """Redact raw untrusted metadata blocks from canonical markdown files."""
    md_dir = Path("/home/oceandmt/.openclaw/workspace/memory")
    if not md_dir.exists():
        return 0, ["memory dir not found"]

    affected = []
    for md_file in sorted(md_dir.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        cleaned, changed = redact_markdown_raw_blocks(text)
        if not changed:
            continue

        affected.append(md_file.name)
        if not dry_run:
            md_file.write_text(cleaned, encoding="utf-8")
            # Also update memories DB entries that source from this file
            # (content references will be fixed by rebuild)

    return len(affected), affected


# ── Phase 3 ─────────────────────────────────────────────────────────────────


def phase3_rebuild(dry_run: bool):
    """Rebuild FTS + vector + graph indices."""
    if dry_run:
        print("  [dry-run] skip: reindex_fts_only + self_heal_embeddings + graph_rebuild")
        return

    print("  Rebuilding FTS indices...")
    from super_memory import bridge
    bridge.reindex_fts_only()
    print("  FTS done.")

    print("  Self-healing embeddings...")
    try:
        res = bridge.self_heal_embeddings()
        print(f"  Self-heal: {res}")
    except Exception as e:
        print(f"  Self-heal skipped: {e}")

    print("  Rebuilding graph...")
    try:
        res = bridge.graph_rebuild()
        print(f"  Graph: {res}")
    except Exception as e:
        print(f"  Graph skipped: {e}")

    print("  Reindexing sessions...")
    try:
        from super_memory.session_index import index_all_sessions
        r = index_all_sessions()
        print(f"  Sessions: {r.get('files_found')} found, {r.get('indexed')} indexed")
    except Exception as e:
        print(f"  Sessions skipped: {e}")


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Execute migration")
    parser.add_argument("--skip-rebuild", action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    DB = "/home/oceandmt/.openclaw/workspace/data/super-memory.sqlite3"
    conn = sqlite3.connect(DB)

    print(f"{'DRY RUN' if dry_run else 'APPLY'} — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 50)

    # Phase 1
    meta_cleaned = phase1_metadata_json(conn, dry_run)
    print(f"Phase 1 (metadata_json): {meta_cleaned} records cleaned")

    # Phase 2
    md_count, md_files = phase2_canonical_markdown(dry_run)
    print(f"Phase 2 (canonical markdown): {md_count} files redacted")
    if md_files:
        print("  Files affected:")
        for fname in md_files:
            print(f"    - {fname}")

    # Summary
    total_mem = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    rmeta = conn.execute(
        "SELECT COUNT(*) FROM memories WHERE "
        "metadata_json LIKE '%chat_id%' OR metadata_json LIKE '%sender_id%' "
        "OR metadata_json LIKE '%senderName%' OR metadata_json LIKE '%senderBlock%' "
        "OR metadata_json LIKE '%thread_label%' OR metadata_json LIKE '%conversation_label%'"
    ).fetchone()[0]
    rcontent = conn.execute(
        "SELECT COUNT(*) FROM memories WHERE "
        "content LIKE '%Conversation info (untrusted metadata)%' "
        "OR content LIKE '%Sender (untrusted metadata)%'"
    ).fetchone()[0]

    print(f"\nDB state: {total_mem} memories total")
    print(f"  Remaining untrusted in metadata_json: {rmeta}")
    print(f"  Remaining 'untrusted metadata' in content: {rcontent}")

    # Phase 3
    if not args.skip_rebuild:
        print()
        phase3_rebuild(dry_run)

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
