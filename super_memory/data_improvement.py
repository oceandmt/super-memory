"""Data Improvement Engine: fix canonical compliance, dedup, trust_score, promotion.

Usage:
    from super_memory.data_improvement import run_improvement
    result = run_improvement()
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import load_config
from .storage import SuperMemoryStore
from .models import MemoryType, MemoryScope

logger = logging.getLogger("super-memory.data_improvement")


def _compute_trust(content: str, mem_type: str | None = None, source: str | None = None) -> float:
    """Compute trust score from content quality + provenance signals.

    Source-aware: curated/canonical provenance earns higher trust than raw
    conversation turn-dumps (source='openclaw.turn'), which are noisy and
    should not dominate recall arbitration.
    """
    score = 0.5  # baseline
    c = content.strip()
    if len(c) >= 50:
        score += 0.15
    if len(c) >= 200:
        score += 0.10
    if any(x in c for x in ["verified", "commit", "test", "deploy", "config"]):
        score += 0.10
    if any(x in c for x in ["path:", "version:", "id:", "hash:"]):
        score += 0.10
    if mem_type in ("fact", "decision", "instruction", "reference", "workflow"):
        score += 0.10
    if mem_type in ("doctrine", "preference", "blocker", "lesson"):
        score += 0.15

    # Provenance adjustment: curated saves are trusted; raw turn captures are not.
    src = (source or "").lower()
    if src.startswith("openclaw.turn") or mem_type == "event":
        # Raw conversation capture — cap low regardless of length heuristics so it
        # cannot outrank curated canonical memory in arbitration.
        score = min(score, 0.4)
    elif src.startswith(("conversation-implementation", "telegram-request", "direct", "super-memory")):
        score += 0.10

    return min(1.0, max(0.1, round(score, 3)))


def _is_durable(mem_type: str) -> bool:
    return mem_type in ("fact", "decision", "workflow", "lesson", "insight", "instruction", "reference", "doctrine")


def _compute_canonical_filename(memory_id: str, content: str, mem_type: str | None = None) -> str:
    """Derive a canonical markdown filename from memory content."""
    # Try to extract a title from first line or key info
    first_line = content.strip().split("\n")[0][:80]
    # Remove common prefixes
    title = re.sub(r'^(assistant:|user:|##|###)\s*', '', first_line).strip()
    if not title or len(title) < 5:
        title = f"{mem_type or 'memory'}-{memory_id[:8]}"
    # Slugify
    slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
    slug = re.sub(r'[-\s]+', '-', slug)[:80]
    return f"{slug}.md"


def _find_memory_markdown_files(root: Path) -> set[str]:
    """Find all markdown files in workspace memory dirs that could serve as canonical."""
    files = set()
    for d in [root / 'memory', root / 'projects' / 'super-memory-github' / 'memory']:
        if d.exists():
            for f in d.glob('**/*.md'):
                if '__pycache__' not in str(f):
                    files.add(str(f.relative_to(root)))
    return files


def check_state(config_path: str | None = None) -> dict[str, Any]:
    """Analyze current memory state for all 4 improvement areas."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    root = Path(cfg.workspace_root)
    
    rows = list(store.list_memory_rows(limit=20000))
    total = len(rows)
    
    state = {
        "total": total,
        "types": {},
        "scopes": {},
        "no_trust": 0,
        "no_trust_valid": 0,
        "canonical_files": len(_find_memory_markdown_files(root)),
        "duplicate_count": 0,
        "event_count": 0,
        "durable_count": 0,
        "session_count": 0,
        "project_shared_count": 0,
        "canonical_candidates": 0,
        "promotion_candidates": 0,
        "needs_dedup": False,
    }
    
    for r in rows:
        d = dict(r)
        content = d.get('content', '') or ''
        mem_type = d.get('type', 'context') or 'context'
        scope = d.get('scope', 'session') or 'session'
        trust = d.get('trust_score')
        
        state['types'][mem_type] = state['types'].get(mem_type, 0) + 1
        state['scopes'][scope] = state['scopes'].get(scope, 0) + 1
        
        if trust is None or trust <= 0:
            state['no_trust'] += 1
            if len(content) > 30:
                state['no_trust_valid'] += 1
        
        if mem_type == 'event':
            state['event_count'] += 1
        if _is_durable(mem_type):
            state['durable_count'] += 1
        if scope == 'session':
            state['session_count'] += 1
        if scope in ('project', 'shared'):
            state['project_shared_count'] += 1
        if _is_durable(mem_type) and len(content) > 50:
            state['canonical_candidates'] += 1
        if scope == 'session' and _is_durable(mem_type) and len(content) > 50:
            state['promotion_candidates'] += 1
    
    state['duplicate_count'] = _estimate_duplicates(rows)
    state['needs_dedup'] = state['duplicate_count'] > 5
    
    return state


def _estimate_duplicates(rows: list) -> int:
    """Quick dedup estimate by checking overlapping content prefixes."""
    seen = {}
    dups = 0
    for r in rows:
        d = dict(r)
        content = d.get('content', '') or ''
        prefix = content[:80].strip().lower()
        if len(prefix) > 30:
            if prefix in seen:
                dups += 1
            else:
                seen[prefix] = True
    return dups


def backfill_trust_scores(config_path: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Backfill trust_score for all memories that lack it."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    
    rows = list(store.list_memory_rows(limit=20000))
    assigned = 0
    skipped = 0
    
    for r in rows:
        d = dict(r)
        trust = d.get('trust_score')
        if trust is not None and trust > 0:
            skipped += 1
            continue
        
        content = d.get('content', '') or ''
        mem_type = d.get('type', 'context') or 'context'
        memory_id = d.get('id')
        if not memory_id or len(content) < 20:
            skipped += 1
            continue
        
        score = _compute_trust(content, mem_type)
        
        if not dry_run:
            try:
                c = store.connect()
                c.execute('UPDATE memories SET trust_score=? WHERE id=?', (score, memory_id))
                c.close()
            except Exception as exc:
                    logger.warning("Failed to update trust for %s: %s", memory_id, exc)
                    skipped += 1
                    continue
        assigned += 1
    
    return {
        "ok": True,
        "dry_run": dry_run,
        "assigned": assigned,
        "skipped_already_had": skipped,
        "new_coverage": f"{assigned}/{assigned + skipped} ({assigned / max(assigned + skipped, 1) * 100:.1f}%)",
    }


def promote_events_to_durable(config_path: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Promote event-type memories to facts/decisions when they have quality content.
    Also promote session-scope durable memories to project scope."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    
    rows = list(store.list_memory_rows(limit=20000))
    promoted_type = 0
    promoted_scope = 0
    
    for r in rows:
        d = dict(r)
        content = d.get('content', '') or ''
        mem_type = d.get('type', 'context') or 'context'
        scope = d.get('scope', 'session') or 'session'
        memory_id = d.get('id')
        
        if not memory_id:
            continue
        
        # Promote event → fact/decision if content is meaningful
        new_type = None
        if mem_type == 'event' and len(content) >= 80:
            # Check if it has decision-like or fact-like content
            if any(x in content.lower() for x in ['decided', 'decision', 'chose', 'will use', 'quyết định']):
                new_type = 'decision'
            elif any(x in content.lower() for x in ['path:', 'version:', 'installed', 'config', 'deploy']):
                new_type = 'fact'
            elif len(content) >= 200:
                new_type = 'fact'
        
        if new_type and not dry_run:
            try:
                c = store.connect()
                c.execute('UPDATE memories SET type=? WHERE id=?', (new_type, memory_id))
                c.close()
                promoted_type += 1
            except Exception as exc:
                logger.warning("Failed to promote type for %s: %s", memory_id, exc)
        elif new_type:
            promoted_type += 1
        
        # Promote session → project for durable types with enough content
        if scope == 'session' and _is_durable(mem_type or new_type or 'context') and len(content) >= 100:
            if not dry_run:
                try:
                    c = store.connect()
                    c.execute('UPDATE memories SET scope=? WHERE id=?', ('project', memory_id))
                    c.close()
                    promoted_scope += 1
                except Exception as exc:
                    logger.warning("Failed to promote scope for %s: %s", memory_id, exc)
            else:
                promoted_scope += 1
    
    return {
        "ok": True,
        "dry_run": dry_run,
        "events_promoted_to_durable": promoted_type,
        "sessions_promoted_to_project": promoted_scope,
    }


def backfill_canonical_markdown(config_path: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Create canonical markdown files for SQLite memories that lack them."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    root = Path(cfg.workspace_root)
    memory_dir = root / 'memory'
    memory_dir.mkdir(parents=True, exist_ok=True)
    
    existing_files = _find_memory_markdown_files(root)
    
    rows = list(store.list_memory_rows(limit=20000))
    created = 0
    skipped_no_content = 0
    skipped_event = 0
    skipped_short = 0
    
    for r in rows:
        d = dict(r)
        content = d.get('content', '') or ''
        mem_type = d.get('type', 'context') or 'context'
        memory_id = d.get('id')
        source = d.get('source') or 'unknown'
        
        # Skip events (they're ephemeral) and very short content
        if mem_type == 'event':
            skipped_event += 1
            continue
        if len(content) < 50:
            skipped_short += 1
            continue
        if not memory_id:
            skipped_no_content += 1
            continue
        
        # Derive filename
        filename = _compute_canonical_filename(memory_id, content, mem_type)
        rel_path = f"memory/{filename}"
        
        if rel_path in existing_files:
            # File exists — skip (already has canonical)
            continue
        
        # Build canonical markdown content
        lines = [
            f"# {_compute_canonical_filename(memory_id, content, mem_type).replace('.md','').replace('-', ' ').title()}",
            f"",
            f"**Type:** {mem_type}  **Source:** {source}  **ID:** `{memory_id}`",
            f"**Created:** {d.get('created_at', '')[:19] if d.get('created_at') else ''}",
            f"",
            content.strip(),
        ]
        md_content = "\n".join(lines)
        
        if not dry_run:
            filepath = memory_dir / filename
            filepath.write_text(md_content, encoding='utf-8')
        created += 1
    
    return {
        "ok": True,
        "dry_run": dry_run,
        "canonical_files_created": created,
        "skipped_events": skipped_event,
        "skipped_short_content": skipped_short,
        "skipped_no_content": skipped_no_content,
    }


def run_dedup(config_path: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Run dedup consolidation on duplicate memory clusters."""
    from . import bridge
    try:
        result = bridge.consolidate(strategy="dedup", dry_run=dry_run, config_path=config_path)
        return result
    except Exception as exc:
        logger.warning("Dedup consolidation failed: %s", exc)
        # Fallback: run deep improve proposal
        try:
            return bridge.deep_improve(dry_run=dry_run, config_path=config_path)
        except Exception as exc2:
            return {"ok": False, "error": f"dedup: {exc}, improve: {exc2}"}


def run_improvement(config_path: str | None = None, dry_run: bool = True) -> dict[str, Any]:
    """Run all 4 improvement strategies and return results."""
    logger.info("Starting data improvement (dry_run=%s)", dry_run)
    
    state_before = check_state(config_path=config_path)
    
    # 1. Trust score backfill
    trust_result = backfill_trust_scores(config_path=config_path, dry_run=dry_run)
    
    # 2. Event → Durable + Session → Project promotion
    promote_result = promote_events_to_durable(config_path=config_path, dry_run=dry_run)
    
    # 3. Canonical markdown backfill
    canonical_result = backfill_canonical_markdown(config_path=config_path, dry_run=dry_run)
    
    # 4. Dedup consolidation
    dedup_result = run_dedup(config_path=config_path, dry_run=dry_run)
    
    state_after = check_state(config_path=config_path) if not dry_run else None
    
    return {
        "ok": True,
        "dry_run": dry_run,
        "state_before": state_before,
        "state_after": state_after,
        "results": {
            "trust_score_backfill": trust_result,
            "event_session_promotion": promote_result,
            "canonical_markdown_backfill": canonical_result,
            "dedup_consolidation": dedup_result,
        },
    }
