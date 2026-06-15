"""Progressive memory loading — 4 layers inspired by MemPalace architecture.

Layer 1: Verbatim (recent raw memories, ~170 tokens for startup)
Layer 2: Structured (entities + concepts extracted)
Layer 3: Spatial (wing/room/hall organized)
Layer 4: Compressed (AAAK index, keyword-based recall)

Each layer loads incrementally when needed, minimizing startup cost.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..models import MemoryRecord, MemoryLayer


class MemPalaceLoader:
    """4-layer progressive memory loader. Startup cost target: ≤200 tokens."""

    def __init__(self, db_path: Path, workspace_root: Path):
        self.db_path = db_path
        self.workspace_root = workspace_root

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def load_layer1_verbatim(self, limit: int = 10, days_back: int = 7) -> list[MemoryRecord]:
        """Layer 1: Recent verbatim memories. Target ~170 tokens startup cost.
        
        Returns most recent memories from the last N days, focusing on
        high-priority and frequently accessed items.
        """
        cutoff = datetime.now() - timedelta(days=days_back)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.* FROM memories m
                WHERE m.layer = 'mempalace'
                  AND datetime(m.created_at) >= ?
                  AND m.metadata_json NOT LIKE '%"lifecycle_state":"soft_deleted"%'
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                (cutoff.isoformat(), limit),
            ).fetchall()
        
        return [self._row_to_record(r) for r in rows]

    def load_layer2_structured(self, query: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Layer 2: Structured extraction (entities, concepts, domains).
        
        Loads previously extracted structure from palace_drawers metadata.
        If query provided, filters by relevance.
        """
        with self._connect() as conn:
            if query:
                rows = conn.execute(
                    """
                    SELECT * FROM palace_drawers
                    WHERE content LIKE ? OR metadata_json LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (f"%{query}%", f"%{query}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM palace_drawers ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

        return {
            "drawers": [dict(r) for r in rows],
            "count": len(rows),
        }

    def load_layer3_spatial(self, wing: str | None = None, room: str | None = None, hall: str | None = None, limit: int = 30) -> dict[str, Any]:
        """Layer 3: Spatial organization query (wing → room → hall → drawers).
        
        Navigate memory palace structure to find context within spatial scope.
        """
        from .spatial import SpatialNavigator
        nav = SpatialNavigator(self.db_path)
        
        if hall:
            drawers = nav.drawers(wing=wing, room=room, hall=hall, limit=limit)
        elif room:
            drawers = nav.drawers(wing=wing, room=room, limit=limit)
        elif wing:
            drawers = nav.drawers(wing=wing, limit=limit)
        else:
            drawers = nav.drawers(limit=limit)

        return {
            "spatial_scope": {
                "wing": wing,
                "room": room,
                "hall": hall,
            },
            "drawers": drawers,
            "count": len(drawers),
        }

    def load_layer4_compressed(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Layer 4: AAAK compressed index search.
        
        Fast keyword-based recall over compressed representation.
        Returns compressed entries with expansion available on-demand.
        """
        from .compressor import AAAKCompressor
        
        # Build index from palace_drawers (in real deployment, this would be cached)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, content FROM palace_drawers ORDER BY created_at DESC LIMIT 1000"
            ).fetchall()
        
        texts = [(r["id"], r["content"]) for r in rows]
        compressor = AAAKCompressor()
        index = compressor.compress_batch(texts)
        results = compressor.search(query, index, limit=limit)
        
        return {
            "query": query,
            "compressed_results": [
                {
                    "id": cm.id,
                    "keywords": cm.keywords,
                    "dense_text": cm.dense_text,
                    "compression_ratio": cm.compression_ratio,
                }
                for cm in results
            ],
            "stats": compressor.stats(index),
            "count": len(results),
        }

    def startup_context(self, max_tokens: int = 200) -> dict[str, Any]:
        """Generate minimal startup context. Target ≤200 tokens.
        
        Combines Layer 1 (verbatim recent) with critical spatial overview.
        """
        layer1 = self.load_layer1_verbatim(limit=5, days_back=3)
        
        from .spatial import SpatialNavigator
        nav = SpatialNavigator(self.db_path)
        summary = nav.summary()
        
        # Format as compact text block
        lines: list[str] = []
        lines.append("# MemPalace Startup Context")
        lines.append(f"Spatial: {summary['total_wings']} wings, {summary['total_rooms']} rooms, {summary['total_drawers']} drawers")
        
        if layer1:
            lines.append("\nRecent Memories (last 3 days):")
            for rec in layer1[:5]:
                lines.append(f"- [{rec.type.value}] {rec.content[:80]}")
        
        context_text = "\n".join(lines)
        estimated_tokens = len(context_text.split()) * 1.3  # rough estimate
        
        return {
            "context_text": context_text,
            "estimated_tokens": int(estimated_tokens),
            "layer1_count": len(layer1),
            "spatial_summary": summary,
        }

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        """Convert SQLite row to MemoryRecord."""
        import json
        return MemoryRecord(
            id=row["id"],
            content=row["content"],
            type=row["type"],
            scope=row["scope"],
            agent_id=row["agent_id"],
            session_id=row["session_id"],
            project=row["project"],
            tags=json.loads(row["tags_json"]),
            source=row["source"],
            trust_score=row["trust_score"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=json.loads(row["metadata_json"]),
        )

    def load_all_layers(self, query: str | None = None) -> dict[str, Any]:
        """Load all 4 layers for comprehensive context (expensive, use sparingly)."""
        return {
            "layer1_verbatim": [r.__dict__ for r in self.load_layer1_verbatim()],
            "layer2_structured": self.load_layer2_structured(query),
            "layer3_spatial": self.load_layer3_spatial(),
            "layer4_compressed": self.load_layer4_compressed(query or ""),
        }
