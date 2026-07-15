"""Layer consistency validator for Super Memory.

Verifies that all 4 layers (workspace_markdown, mempalace, honcho, neural_memory)
have identical content_hash for the same memory ID.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .config import load_config
from .storage import SuperMemoryStore


def verify_layer_consistency(
    memory_id: str | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Verify layer consistency for one or all memories.
    
    Args:
        memory_id: Specific memory ID to check, or None for all
        config_path: Config file path
        
    Returns:
        Report with consistency status and any issues found
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    
    issues = []
    checked = 0
    consistent = 0
    
    with store.connect() as conn:
        if memory_id:
            memory_ids = [memory_id]
        else:
            rows = conn.execute("SELECT DISTINCT id FROM memories").fetchall()
            memory_ids = [r["id"] for r in rows]
        
        for mid in memory_ids:
            rows = conn.execute(
                "SELECT layer, content_hash FROM memories WHERE id = ?",
                (mid,)
            ).fetchall()
            
            if not rows:
                continue
                
            checked += 1
            layers = {r["layer"] for r in rows}
            hashes = {r["content_hash"] for r in rows if r["content_hash"]}
            
            expected_layers = {"workspace_markdown", "mempalace", "honcho", "neural_memory"}
            missing_layers = expected_layers - layers
            
            if len(hashes) == 1 and not missing_layers:
                consistent += 1
            else:
                issues.append({
                    "memory_id": mid,
                    "consistent": len(hashes) == 1,
                    "layer_count": len(layers),
                    "expected_layers": 4,
                    "content_hashes": list(hashes),
                    "missing_layers": list(missing_layers),
                    "issue_type": "content_drift" if len(hashes) > 1 else "missing_layers"
                })
    
    return {
        "ok": len(issues) == 0,
        "checked": checked,
        "consistent": consistent,
        "issues_count": len(issues),
        "issues": issues[:50],  # Limit to 50 for reporting
        "consistency_rate": round(consistent / checked * 100, 2) if checked > 0 else 0
    }


def verify_fingerprint_coverage(config_path: str | None = None) -> dict[str, Any]:
    """Verify that workspace_markdown layer has fingerprints for all memories.
    
    Returns:
        Report with fingerprint coverage stats
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    
    with store.connect() as conn:
        canonical_count = conn.execute(
            "SELECT COUNT(DISTINCT id) FROM memories WHERE layer = 'workspace_markdown'"
        ).fetchone()[0]
        
        fingerprint_count = conn.execute(
            "SELECT COUNT(DISTINCT memory_id) FROM memory_fingerprints WHERE layer = 'workspace_markdown'"
        ).fetchone()[0]
        
        missing = conn.execute(
            """
            SELECT m.id, m.content_hash
            FROM memories m
            LEFT JOIN memory_fingerprints f ON m.id = f.memory_id AND f.layer = 'workspace_markdown'
            WHERE m.layer = 'workspace_markdown' AND f.memory_id IS NULL
            LIMIT 10
            """
        ).fetchall()
        
    return {
        "ok": len(missing) == 0,
        "canonical_memories": canonical_count,
        "fingerprints": fingerprint_count,
        "coverage_rate": round(fingerprint_count / canonical_count * 100, 2) if canonical_count > 0 else 0,
        "missing_count": len(missing),
        "missing_sample": [{"id": r["id"], "content_hash": r["content_hash"]} for r in missing]
    }


def full_consistency_check(config_path: str | None = None) -> dict[str, Any]:
    """Run full consistency check: layers + fingerprints.
    
    Returns:
        Complete consistency report
    """
    layer_report = verify_layer_consistency(config_path=config_path)
    fingerprint_report = verify_fingerprint_coverage(config_path=config_path)
    
    overall_ok = layer_report["ok"] and fingerprint_report["ok"]
    
    return {
        "ok": overall_ok,
        "grade": "A" if overall_ok else "B" if layer_report["consistency_rate"] > 95 else "C",
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "layer_consistency": layer_report,
        "fingerprint_coverage": fingerprint_report,
        "summary": {
            "total_memories": layer_report["checked"],
            "consistent_memories": layer_report["consistent"],
            "consistency_rate": layer_report["consistency_rate"],
            "fingerprint_coverage": fingerprint_report["coverage_rate"],
            "issues": layer_report["issues_count"]
        }
    }
