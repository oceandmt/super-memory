"""Phase 4 compact benchmarks for Super-Memory MemPalace + Honcho."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Support running as script: python super_memory/benchmarks.py
# or as module: python -m super_memory.benchmarks
try:
    from .config import load_config
    from .honcho.tools import HonchoTools
    from .mempalace.tools import MemPalaceTools
except ImportError:
    # Add parent of super_memory to sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from super_memory.config import load_config
    from super_memory.honcho.tools import HonchoTools
    from super_memory.mempalace.tools import MemPalaceTools


@dataclass
class BenchResult:
    name: str
    target: str
    actual: Any
    passed: bool
    notes: str = ""


@dataclass
class BenchSuite:
    results: list[BenchResult] = field(default_factory=list)

    def add(self, name: str, target: str, actual: Any, passed: bool, notes: str = "") -> None:
        self.results.append(BenchResult(name, target, actual, passed, notes))

    def summary(self) -> dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "all_passed": passed == total,
            "details": [r.__dict__ for r in self.results],
        }


def _db_path(config) -> Path:
    return Path(config.workspace_root) / config.sqlite_path


def ensure_bench_data(config, count: int = 500) -> int:
    """Seed synthetic memories and spatial drawers using current SQLite schema."""
    db = _db_path(config)
    db.parent.mkdir(parents=True, exist_ok=True)
    topics = [
        ("gold trading signal blackout window", "trading", "signals", "decisions"),
        ("facebook fanpage post business suite", "content", "social", "workflow"),
        ("NeuralMemory MCP recall depth", "research", "memory", "facts"),
        ("plugin manifest validate contracts", "infra", "openclaw", "facts"),
        ("Meilisearch index refresh multi agent", "infra", "search", "events"),
        ("VPS config backup before gateway restart", "infra", "vps", "events"),
        ("Discord brain lane routing doctrine", "admin", "discord", "doctrine"),
        ("OpenClaw workspace template installer", "infra", "templates", "workflow"),
    ]
    with sqlite3.connect(db, timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        existing = conn.execute("SELECT COUNT(*) FROM palace_drawers WHERE memory_id LIKE 'bench-%'").fetchone()[0]
        if existing >= count:
            return 0
        base = datetime(2026, 6, 14)
        for i in range(count):
            phrase, wing, room, hall = topics[i % len(topics)]
            content = f"Synthetic benchmark memory {i}: {phrase}; provenance and recall should work."
            memory_id = f"bench-{i:06d}"
            created = (base - timedelta(minutes=i)).isoformat()
            tags = ["bench", wing, room, hall]
            meta = {"wing": wing, "room": room, "hall": hall, "benchmark": True}
            conn.execute(
                """
                INSERT OR IGNORE INTO memories
                (id, layer, content, type, scope, agent_id, session_id, project,
                 tags_json, source, trust_score, created_at, metadata_json)
                VALUES (?, 'workspace_markdown', ?, 'context', 'project', 'bench',
                        'bench-session', ?, ?, 'benchmark', 0.9, ?, ?)
                """,
                (memory_id, content, wing, json.dumps(tags), created, json.dumps(meta)),
            )
            checksum = hashlib.sha256(f"{wing}\0{room}\0{hall}\0{content}".encode()).hexdigest()
            conn.execute(
                """
                INSERT OR IGNORE INTO palace_drawers
                (id, memory_id, wing, room, hall, content, checksum, source, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'benchmark', ?, ?)
                """,
                (f"drawer-{memory_id}", memory_id, wing, room, hall, content, checksum, json.dumps(meta), created),
            )
    return count - existing


def bench_startup(mp: MemPalaceTools, suite: BenchSuite) -> None:
    r = mp.palace_startup_context(max_tokens=200)
    tokens = int(r.get("estimated_tokens", len(r.get("context_text", "").split())))
    suite.add("MemPalace wake tokens", "<=200", tokens, tokens <= 200)


def bench_recall(mp: MemPalaceTools, suite: BenchSuite) -> None:
    cases = [
        ("gold trading signal", ["trading", "gold"]),
        ("facebook fanpage post", ["content", "facebook"]),
        ("NeuralMemory MCP recall", ["research", "memory"]),
        ("plugin manifest validate", ["infra", "plugin"]),
        ("Meilisearch index refresh", ["infra", "search"]),
    ]
    hits = 0
    for q, expected in cases:
        rows = mp.palace_search(q, limit=5).get("results", [])
        hay = " ".join(json.dumps(row).lower() for row in rows)
        if any(term.lower() in hay for term in expected):
            hits += 1
    score = hits / len(cases)
    suite.add("MemPalace recall@5", ">=90%", f"{hits}/{len(cases)} ({score:.0%})", score >= 0.9)


def bench_layers(mp: MemPalaceTools, suite: BenchSuite) -> None:
    timings: dict[str, float] = {}
    specs = [(1, None), (2, "memory"), (3, None), (4, "memory")]
    for layer, query in specs:
        start = time.perf_counter()
        kwargs = {"layer": layer, "limit": 20}
        if query:
            kwargs["query"] = query
        result = mp.palace_load_layer(**kwargs)
        timings[f"layer{layer}"] = (time.perf_counter() - start) * 1000
        if not result.get("ok"):
            timings[f"layer{layer}"] = 9999
    passed = all(ms < 1000 for ms in timings.values())
    suite.add("MemPalace 4-layer latency", "<1000ms each", {k: round(v, 1) for k, v in timings.items()}, passed)


def bench_spatial(mp: MemPalaceTools, suite: BenchSuite) -> None:
    checks = {
        "wings": mp.palace_wings().get("count", 0),
        "rooms": mp.palace_rooms().get("count", 0),
        "halls": mp.palace_halls().get("count", 0),
        "drawers": mp.palace_drawers(limit=10).get("count", 0),
    }
    suite.add("MemPalace spatial navigation", "all counts >0", checks, all(v > 0 for v in checks.values()))


def bench_extract(mp: MemPalaceTools, suite: BenchSuite) -> None:
    text = "Boss asked Lucas to deploy Super Memory on VPS <VPS_HOST> using markdown first architecture for gold trading signals."
    r = mp.palace_extract(text)
    entities = len(r.get("entities", []))
    concepts = len(r.get("concepts", []))
    domains = len(r.get("domains", []))
    suite.add("MemPalace extraction", "entities+concepts+domains >0", {"entities": entities, "concepts": concepts, "domains": domains}, entities > 0 and (concepts > 0 or domains > 0))


def bench_honcho_latency(hn: HonchoTools, suite: BenchSuite) -> None:
    turns = [
        ("Deploy super-memory carefully", "I will verify config first."),
        ("Gold signal looks strong", "I will check blackout window."),
        ("Schedule Facebook post", "I will use Business Suite."),
        ("Refresh memory index", "I will run Meilisearch refresh."),
        ("Add Discord brain lane", "I will update routing doctrine."),
    ]
    samples = []
    for user, assistant in turns:
        start = time.perf_counter()
        hn.honcho_analyze_turn(user, assistant, peer_id="bench-boss", save=False, depth=2)
        samples.append((time.perf_counter() - start) * 1000)
    avg = sum(samples) / len(samples)
    suite.add("Honcho dialectic latency", "avg<500ms max<1000ms", {"avg_ms": round(avg, 1), "max_ms": round(max(samples), 1)}, avg < 500 and max(samples) < 1000)


def bench_honcho_ops(hn: HonchoTools, suite: BenchSuite) -> None:
    peer = "bench-boss"
    write = hn.honcho_profile(peer_id=peer, facts=["Benchmark prefers careful verification"])
    read = hn.honcho_profile(peer_id=peer)
    conclude = hn.honcho_conclude(content="Benchmark conclusion works", about_peer=peer)
    search = hn.honcho_search(query="benchmark", peer_id=peer, limit=5)
    status = {"write": write.get("ok"), "read": read.get("ok"), "conclude": conclude.get("ok"), "search": search.get("ok")}
    suite.add("Honcho profile/conclude/search", "all ok", status, all(status.values()))


def bench_honcho_context(hn: HonchoTools, suite: BenchSuite) -> None:
    r = hn.honcho_context(peer_id="bench-boss", max_tokens=500)
    tokens = int(r.get("estimated_tokens", len(r.get("context_text", "").split())))
    suite.add("Honcho context budget", "<=500 tokens", tokens, tokens <= 500)


def run_all(config_path: str | None = None) -> BenchSuite:
    config = load_config(config_path)
    added = ensure_bench_data(config, 500)
    if added:
        print(f"[bench] seeded {added} benchmark rows")
    mp = MemPalaceTools(config)
    hn = HonchoTools(config)
    suite = BenchSuite()
    bench_startup(mp, suite)
    bench_recall(mp, suite)
    bench_layers(mp, suite)
    bench_spatial(mp, suite)
    bench_extract(mp, suite)
    bench_honcho_latency(hn, suite)
    bench_honcho_ops(hn, suite)
    bench_honcho_context(hn, suite)
    return suite


if __name__ == "__main__":
    s = run_all(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(s.summary(), indent=2, ensure_ascii=False))
    raise SystemExit(0 if s.summary()["all_passed"] else 1)
