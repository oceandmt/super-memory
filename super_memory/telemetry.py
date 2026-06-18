from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class TelemetryRegistry:
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    latencies_ms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def inc(self, name: str, value: int = 1) -> None:
        self.counters[name] += value

    def observe_ms(self, name: str, value: float) -> None:
        self.latencies_ms[name].append(float(value))

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
            self.inc(name + ".success")
        except Exception:
            self.inc(name + ".error")
            raise
        finally:
            self.observe_ms(name + ".latency_ms", (time.perf_counter() - start) * 1000)

    def snapshot(self) -> dict[str, object]:
        latency_summary: dict[str, dict[str, float]] = {}
        for name, values in self.latencies_ms.items():
            if not values:
                continue
            latency_summary[name] = {
                "count": len(values),
                "avg": sum(values) / len(values),
                "max": max(values),
            }
        return {"counters": dict(self.counters), "latencies_ms": latency_summary}

    def prometheus_text(self) -> str:
        lines: list[str] = []
        for name, value in sorted(self.counters.items()):
            metric = "super_memory_" + name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE {metric} counter")
            lines.append(f"{metric} {value}")
        for name, values in sorted(self.latencies_ms.items()):
            if not values:
                continue
            metric = "super_memory_" + name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE {metric} gauge")
            lines.append(f"{metric}_avg {sum(values) / len(values):.3f}")
            lines.append(f"{metric}_max {max(values):.3f}")
            lines.append(f"{metric}_count {len(values)}")
        return "\n".join(lines) + ("\n" if lines else "")


telemetry = TelemetryRegistry()


def ensure_telemetry_tables(config_path: str | Path | None = None) -> None:
    from .config import load_config
    from .migrations import run_migrations
    from .storage import SuperMemoryStore

    cfg = load_config(config_path)
    run_migrations(cfg)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS telemetry_events ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, value REAL NOT NULL DEFAULT 1, "
            "metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_events_name_created ON telemetry_events(name, created_at DESC)")
        conn.commit()


def record_event(name: str, value: float = 1.0, metadata: dict[str, Any] | None = None, config_path: str | Path | None = None) -> dict[str, Any]:
    import json
    from .config import load_config
    from .storage import SuperMemoryStore

    ensure_telemetry_tables(config_path)
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        conn.execute("INSERT INTO telemetry_events (name, value, metadata_json) VALUES (?, ?, ?)", (name, value, json.dumps(metadata or {})))
        conn.commit()
    return {"ok": True, "name": name, "value": value}


def telemetry_history(name: str | None = None, limit: int = 100, config_path: str | Path | None = None) -> dict[str, Any]:
    import json
    from .config import load_config
    from .storage import SuperMemoryStore

    ensure_telemetry_tables(config_path)
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        if name:
            rows = conn.execute("SELECT * FROM telemetry_events WHERE name = ? ORDER BY created_at DESC LIMIT ?", (name, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM telemetry_events ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"ok": True, "events": [{"name": r["name"], "value": r["value"], "metadata": json.loads(r["metadata_json"]), "created_at": r["created_at"]} for r in rows]}
