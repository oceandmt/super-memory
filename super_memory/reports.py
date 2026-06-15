"""Inspectability reports and health dashboards for Super-Memory."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from .db import DBMixin


class Reports(DBMixin):

    def cross_agent_report(self, days: int = 7) -> dict[str, Any]:
        """Per-agent memory, events, sessions, conflicts, handoffs report."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        agents = {}
        
        with self._conn() as conn:
            if self._has(conn, "memories"):
                rows = conn.execute("""
                    SELECT agent_id, COUNT(*) AS memory_count, MAX(created_at) AS recent_activity
                    FROM memories WHERE agent_id IS NOT NULL AND created_at >= ?
                    GROUP BY agent_id
                """, (cutoff,)).fetchall()
                for r in rows:
                    aid = r["agent_id"]
                    agents.setdefault(aid, {"agent_id": aid, "memory_count": 0, "honcho_events": 0, "sessions": 0, "conflicts": 0, "handoffs": 0})
                    agents[aid]["memory_count"] = r["memory_count"]
                    agents[aid]["recent_activity"] = r["recent_activity"]

            if self._has(conn, "honcho_events"):
                rows = conn.execute("""
                    SELECT observer_peer_id AS agent_id, COUNT(*) AS event_count
                    FROM honcho_events WHERE observer_peer_id IS NOT NULL AND created_at >= ?
                    GROUP BY observer_peer_id
                """, (cutoff,)).fetchall()
                for r in rows:
                    aid = r["agent_id"]
                    agents.setdefault(aid, {"agent_id": aid, "memory_count": 0, "honcho_events": 0, "sessions": 0, "conflicts": 0, "handoffs": 0})
                    agents[aid]["honcho_events"] = r["event_count"]

            if self._has(conn, "sessions"):
                rows = conn.execute("""
                    SELECT agent_id, COUNT(DISTINCT id) AS session_count
                    FROM sessions WHERE agent_id IS NOT NULL AND started_at >= ?
                    GROUP BY agent_id
                """, (cutoff,)).fetchall()
                for r in rows:
                    aid = r["agent_id"]
                    agents.setdefault(aid, {"agent_id": aid, "memory_count": 0, "honcho_events": 0, "sessions": 0, "conflicts": 0, "handoffs": 0})
                    agents[aid]["sessions"] = r["session_count"]

            if self._has(conn, "cross_agent_conflicts"):
                rows = conn.execute("""
                    SELECT agent_a AS agent_id, COUNT(*) AS conflict_count
                    FROM cross_agent_conflicts WHERE created_at >= ? GROUP BY agent_a
                    UNION ALL
                    SELECT agent_b AS agent_id, COUNT(*) AS conflict_count
                    FROM cross_agent_conflicts WHERE created_at >= ? GROUP BY agent_b
                """, (cutoff, cutoff)).fetchall()
                for r in rows:
                    aid = r["agent_id"]
                    agents.setdefault(aid, {"agent_id": aid, "memory_count": 0, "honcho_events": 0, "sessions": 0, "conflicts": 0, "handoffs": 0})
                    agents[aid]["conflicts"] = agents[aid].get("conflicts", 0) + r["conflict_count"]

            if self._has(conn, "handoff_bundles"):
                rows = conn.execute("""
                    SELECT from_agent AS agent_id, COUNT(*) AS handoff_count
                    FROM handoff_bundles WHERE created_at >= ? GROUP BY from_agent
                """, (cutoff,)).fetchall()
                for r in rows:
                    aid = r["agent_id"]
                    agents.setdefault(aid, {"agent_id": aid, "memory_count": 0, "honcho_events": 0, "sessions": 0, "conflicts": 0, "handoffs": 0})
                    agents[aid]["handoffs"] = r["handoff_count"]

        return {"ok": True, "days": days, "agents": list(agents.values()), "count": len(agents)}

    def session_health(self) -> dict[str, Any]:
        """Session health: total, events per session, stale sessions, duplicates."""
        with self._conn() as conn:
            total_sessions = 0
            events_per_session = {}
            stale_sessions = []
            stale_cutoff = (datetime.now() - timedelta(days=7)).isoformat()

            if self._has(conn, "sessions"):
                total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                stale_rows = conn.execute("""
                    SELECT id, agent_id, updated_at FROM sessions
                    WHERE status='active' AND updated_at < ?
                """, (stale_cutoff,)).fetchall()
                stale_sessions = [dict(r) for r in stale_rows]

            if self._has(conn, "honcho_events"):
                rows = conn.execute("""
                    SELECT session_id, COUNT(*) AS event_count FROM honcho_events
                    WHERE session_id IS NOT NULL GROUP BY session_id
                """).fetchall()
                events_per_session = {r["session_id"]: r["event_count"] for r in rows}

            avg_events = sum(events_per_session.values()) / max(1, len(events_per_session)) if events_per_session else 0

            # Duplicate detection: find memories with same content
            duplicates = []
            if self._has(conn, "memories"):
                rows = conn.execute("""
                    SELECT content, COUNT(*) AS dup_count, GROUP_CONCAT(id) AS ids
                    FROM memories WHERE LENGTH(content) > 20
                    GROUP BY content HAVING dup_count > 1 LIMIT 20
                """).fetchall()
                duplicates = [{"content": r["content"][:100], "count": r["dup_count"], "ids": r["ids"].split(",")} for r in rows]

        return {
            "ok": True,
            "total_sessions": total_sessions,
            "avg_events_per_session": round(avg_events, 2),
            "stale_sessions": stale_sessions,
            "stale_count": len(stale_sessions),
            "duplicates": duplicates,
            "duplicate_count": len(duplicates)
        }

    def memory_pollution_report(self) -> dict[str, Any]:
        """Find stale/duplicate/low-quality memory entries."""
        issues = {"short_entries": [], "no_agent": [], "duplicates": [], "stale_entries": []}
        stale_cutoff = (datetime.now() - timedelta(days=90)).isoformat()

        with self._conn() as conn:
            if self._has(conn, "memories"):
                # Short entries
                rows = conn.execute("""
                    SELECT id, content, agent_id, created_at FROM memories
                    WHERE LENGTH(content) < 20 LIMIT 50
                """).fetchall()
                issues["short_entries"] = [dict(r) for r in rows]

                # No agent_id
                rows = conn.execute("""
                    SELECT id, content, created_at FROM memories
                    WHERE agent_id IS NULL LIMIT 50
                """).fetchall()
                issues["no_agent"] = [dict(r) for r in rows]

                # Stale entries
                rows = conn.execute("""
                    SELECT id, content, agent_id, created_at FROM memories
                    WHERE created_at < ? LIMIT 50
                """, (stale_cutoff,)).fetchall()
                issues["stale_entries"] = [dict(r) for r in rows]

                # Duplicates already handled in session_health
                rows = conn.execute("""
                    SELECT content, COUNT(*) AS dup_count, GROUP_CONCAT(id) AS ids
                    FROM memories WHERE LENGTH(content) > 20
                    GROUP BY content HAVING dup_count > 1 LIMIT 20
                """).fetchall()
                issues["duplicates"] = [{"content": r["content"][:100], "count": r["dup_count"], "ids": r["ids"].split(",")} for r in rows]

        return {
            "ok": True,
            "short_count": len(issues["short_entries"]),
            "no_agent_count": len(issues["no_agent"]),
            "stale_count": len(issues["stale_entries"]),
            "duplicate_count": len(issues["duplicates"]),
            "issues": issues
        }

    def export_memory_graph(self, format: str = "json") -> dict[str, Any]:
        """Export agents -> sessions -> topics -> conflicts graph."""
        graph = {"agents": [], "sessions": [], "conflicts": [], "handoffs": []}

        with self._conn() as conn:
            if self._has(conn, "memories"):
                agent_rows = conn.execute("""
                    SELECT DISTINCT agent_id FROM memories WHERE agent_id IS NOT NULL
                """).fetchall()
                graph["agents"] = [r["agent_id"] for r in agent_rows]

            if self._has(conn, "sessions"):
                session_rows = conn.execute("""
                    SELECT id, agent_id, peer_id, status, started_at FROM sessions LIMIT 100
                """).fetchall()
                graph["sessions"] = [dict(r) for r in session_rows]

            if self._has(conn, "cross_agent_conflicts"):
                conflict_rows = conn.execute("""
                    SELECT id, topic, agent_a, agent_b, status FROM cross_agent_conflicts LIMIT 50
                """).fetchall()
                graph["conflicts"] = [dict(r) for r in conflict_rows]

            if self._has(conn, "handoff_bundles"):
                handoff_rows = conn.execute("""
                    SELECT id, from_agent, to_agent, title, status, created_at FROM handoff_bundles LIMIT 50
                """).fetchall()
                graph["handoffs"] = [dict(r) for r in handoff_rows]

        if format == "markdown":
            md_lines = ["# Super-Memory Graph Export", f"\nGenerated: {datetime.now().isoformat()}\n"]
            md_lines.append(f"\n## Agents ({len(graph['agents'])})\n")
            for a in graph["agents"]:
                md_lines.append(f"- {a}")
            md_lines.append(f"\n## Sessions ({len(graph['sessions'])})\n")
            for s in graph["sessions"][:20]:
                md_lines.append(f"- {s['id']} ({s.get('agent_id')}) - {s.get('status')}")
            md_lines.append(f"\n## Conflicts ({len(graph['conflicts'])})\n")
            for c in graph["conflicts"]:
                md_lines.append(f"- {c.get('topic')} between {c.get('agent_a')} vs {c.get('agent_b')} - {c.get('status')}")
            md_lines.append(f"\n## Handoffs ({len(graph['handoffs'])})\n")
            for h in graph["handoffs"]:
                md_lines.append(f"- {h.get('from_agent')} → {h.get('to_agent')}: {h.get('title')} ({h.get('status')})")
            return {"ok": True, "format": "markdown", "content": "\n".join(md_lines)}

        return {"ok": True, "format": "json", "graph": graph}


REPORTS_TOOLS = [
    {"name": "super_memory_cross_agent_report", "description": "Per-agent activity report", "inputSchema": {"type": "object", "properties": {"days": {"type": "integer", "default": 7}}, "required": []}},
    {"name": "super_memory_session_health", "description": "Session health report", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "super_memory_memory_pollution_report", "description": "Memory pollution and quality report", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "super_memory_export_memory_graph", "description": "Export memory graph", "inputSchema": {"type": "object", "properties": {"format": {"type": "string", "default": "json"}}, "required": []}},
]
