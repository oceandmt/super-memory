"""initial_super_memory_schema

Revision ID: d3dd86dec2be
Revises:
Create Date: 2026-06-17 08:26:10.950668
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3dd86dec2be"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the SuperMemory v1 schema from the canonical schema.sql file."""
    schema_path = Path(__file__).resolve().parents[2] / "super_memory" / "schema.sql"
    bind = op.get_bind()
    # schema.sql is SQLite-specific and contains comments with semicolons, so
    # execute it via the DB-API executescript path instead of naïve splitting.
    raw_conn = bind.connection.driver_connection
    raw_conn.executescript(schema_path.read_text(encoding="utf-8"))


def downgrade() -> None:
    """Best-effort downgrade for test/dev databases.

    Production users should prefer backups over downgrade for memory data.
    """
    bind = op.get_bind()
    tables = [
        "alembic_version",
        "memories_fts",
        "memory_fts",
        "cognitive_synapses",
        "graph_edges",
        "palace_drawers",
        "cross_agent_conflicts",
        "cross_agent_claims",
        "handoff_bundles",
        "session_archives",
        "sessions",
        "honcho_peers",
        "honcho_conclusions",
        "honcho_events",
        "memories",
    ]
    for table in tables:
        bind.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
