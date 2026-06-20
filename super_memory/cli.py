from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .compat import memory_get_compatible, memory_search_compatible
from .config import load_config
from .grpc_server import run_sync as grpc_run_sync
from .models import MemoryScope, MemoryType
from .promote import PROMOTABLE_TYPES, promote_both
from .service import SuperMemoryService
from .storage import SuperMemoryStore

app = typer.Typer(help="Local multi-layer memory app for OpenClaw")
semantic_app = typer.Typer(help="Semantic sqlite-vec/Ollama setup, indexing, and verification")
app.add_typer(semantic_app, name="semantic")


@app.callback()
def main_callback(
    grpc: bool = typer.Option(False, "--grpc", help="Start gRPC server alongside the CLI"),
    grpc_port: int = typer.Option(50051, "--grpc-port", help="gRPC port (default: 50051)"),
):
    """Super Memory CLI — optional gRPC server can be started alongside."""
    if grpc:
        import threading
        t = threading.Thread(target=grpc_run_sync, args=(grpc_port,), daemon=True)
        t.start()
        from rich.console import Console
        Console().print(f"[green]gRPC server started on 127.0.0.1:{grpc_port}[/green]")
console = Console()


@app.command()
def remember(
    content: str = typer.Argument(..., help="Memory content"),
    type: MemoryType = MemoryType.CONTEXT,
    scope: MemoryScope = MemoryScope.SESSION,
    agent_id: str = "lucas",
    session_id: Optional[str] = None,
    project: Optional[str] = None,
    tags: list[str] = typer.Option([], "--tag", "-t"),
    source: Optional[str] = None,
    config: Optional[str] = None,
    json_out: bool = False,
):
    from . import bridge as _bridge
    payload = {
        "content": content,
        "type": type.value if isinstance(type, MemoryType) else type,
        "scope": scope.value if isinstance(scope, MemoryScope) else scope,
        "agent_id": agent_id,
        "session_id": session_id,
        "project": project,
        "tags": tags,
        "source": source,
    }
    result = _bridge.remember(payload, config_path=config)
    if json_out:
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    record = result.get("record", {})
    results = result.get("results", [])
    table = Table(title=f"Saved memory {record.get('id', '?')}")
    table.add_column("Layer")
    table.add_column("OK")
    table.add_column("Reference / message")
    for r in results:
        table.add_row(r.get("layer", "?"), "yes" if r.get("ok") else "no", r.get("reference") or r.get("message") or "")
    console.print(table)


@app.command()
def recall(query: str, limit: int = 5, config: Optional[str] = None, json_out: bool = False):
    svc = SuperMemoryService(load_config(config))
    hits = svc.recall(query, limit=limit)
    if json_out:
        console.print(json.dumps({k.value: [r.model_dump(mode="json") for r in v] for k, v in hits.items()}, ensure_ascii=False, indent=2))
        return
    for layer, records in hits.items():
        console.rule(layer.value)
        if not records:
            console.print("(no hits)")
        for rec in records:
            console.print(f"- [{rec.type.value}/{rec.scope.value}] {rec.content}")


@app.command("memory-search")
def memory_search_cmd(
    query: str,
    max_results: int = 5,
    min_score: float = 0.0,
    corpus: str = "all",
    config: Optional[str] = None,
    json_out: bool = False,
):
    payload = memory_search_compatible(
        query,
        max_results=max_results,
        min_score=min_score,
        corpus=corpus,
        config=load_config(config),
    )
    if json_out:
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for hit in payload["results"]:
        console.print(f"- {hit['path']}#{hit['startLine']}-{hit['endLine']} score={hit['score']:.2f}")
        console.print(f"  {hit['snippet']}")


@app.command("memory-get")
def memory_get_cmd(
    path: str,
    from_line: int = 1,
    lines: int = 20,
    corpus: str = "all",
    config: Optional[str] = None,
    json_out: bool = False,
):
    payload = memory_get_compatible(path, from_line=from_line, lines=lines, corpus=corpus, config=load_config(config))
    if json_out:
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if "error" in payload:
        console.print(f"[red]{payload['error']}[/red]")
        raise typer.Exit(1)
    console.print(payload.get("content", ""))


@app.command("recall-graph")
def recall_graph(memory_id: str, depth: int = 2, limit: int = 20, config: Optional[str] = None, json_out: bool = False):
    svc = SuperMemoryService(load_config(config))
    records = svc.recall_graph(memory_id, depth=depth, limit=limit)
    if json_out:
        console.print(json.dumps([r.model_dump(mode="json") for r in records], ensure_ascii=False, indent=2))
        return
    for rec in records:
        console.print(f"- {rec.id} [{rec.type.value}/{rec.scope.value}] {rec.content}")


@app.command()
def save_order():
    console.print("1. Workspace Markdown: canonical local truth, append-only daily notes/registers")
    console.print("2. MemPalace layer: structured palace/rooms/entities/procedural memory adapter")
    console.print("3. Honcho layer: conversational participant/session memory adapter")
    console.print("4. Neural Memory layer: associative graph/semantic recall adapter, embedded LLM optional")


@app.command("durable-pack")
def durable_pack_cmd(
    pack_name: str = typer.Option("openclaw-super-memory-durable-pack-v1", "--pack-name"),
    project: str = typer.Option("super-memory", "--project"),
    agent: list[str] = typer.Option(["lucas", "alex", "max", "isol"], "--agent"),
    no_qualify: bool = typer.Option(False, "--no-qualify"),
    no_debug: bool = typer.Option(False, "--no-debug"),
    config: Optional[str] = None,
    json_out: bool = False,
):
    """Install the OpenClaw durable memory pack and auto-qualify recall."""
    from . import bridge as _bridge

    result = _bridge.durable_pack(
        pack_name=pack_name,
        project=project,
        agents=agent,
        qualify=not no_qualify,
        debug=not no_debug,
        config_path=config,
    )
    if json_out:
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    console.print(f"[green]Durable pack[/green] {pack_name}: {'OK' if result.get('ok') else 'FAILED'}")
    table = Table(title="Qualification")
    table.add_column("OK")
    table.add_column("Hits")
    table.add_column("Query")
    for q in result.get("qualification", []):
        table.add_row("✅" if q.get("ok") else "❌", str(q.get("hit_count", 0)), q.get("query", ""))
    console.print(table)

@app.command("promote")
def promote(
    memory_id: str = typer.Argument(..., help="Memory ID to promote"),
    config: Optional[str] = None,
    json_out: bool = False,
):
    cfg = load_config(config)
    store = SuperMemoryStore(cfg)
    record = store.get_memory(memory_id)
    if not record:
        console.print(f"[red]Memory {memory_id} not found[/red]")
        raise typer.Exit(1)
    if record.type not in PROMOTABLE_TYPES:
        console.print(
            f"[yellow]Memory type '{record.type.value}' is not promotable. "
            f"Promotable types: {sorted(t.value for t in PROMOTABLE_TYPES)}[/yellow]"
        )
        raise typer.Exit(1)
    mem_path, reg_path = promote_both(cfg, record)
    if json_out:
        console.print(
            json.dumps(
                {"memory_id": memory_id, "long_term_path": mem_path, "register_path": reg_path},
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    console.print(f"[green]MEMORY.md[/green] {'✅ created' if mem_path else '⏭️ skipped (already present)'}")
    console.print(f"[green]Register[/green] {'✅ created' if reg_path else '⏭️ skipped (already present)'}")


@app.command("setup")
def setup_cmd(
    workspace_root: str = typer.Option(str(Path.home() / ".openclaw" / "workspace"), "--workspace-root"),
    output: str = typer.Option("super-memory.yaml", "--output", "-o"),
    sqlite_path: str = typer.Option("data/super-memory.sqlite3", "--sqlite-path"),
    agents: list[str] = typer.Option([], "--agent", help="Default agent id; repeatable"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    json_out: bool = False,
):
    """Generate a concrete cross-agent/session setup config."""
    from .setup_wizard import build_setup_config, setup_instructions, write_setup_config

    payload = build_setup_config(workspace_root, sqlite_path=sqlite_path, agents=agents or None)
    path = write_setup_config(payload, output, overwrite=overwrite)
    if json_out:
        print(json.dumps({"ok": True, "config_path": str(path), "config": payload}, ensure_ascii=False, indent=2))
        return
    console.print(setup_instructions(path))


@app.command("qualify-cross-agent")
def qualify_cross_agent_cmd(config: Optional[str] = None, json_out: bool = False):
    """Run the cross-agent/cross-session end-to-end qualification harness."""
    from .qualify import qualify_cross_agent

    if json_out:
        with redirect_stdout(sys.stderr):
            result = qualify_cross_agent(config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    result = qualify_cross_agent(config)
    table = Table(title=f"Cross-agent/session qualification: {result['verdict']}")
    table.add_column("Check")
    table.add_column("OK")
    table.add_column("Details")
    for check in result["checks"]:
        table.add_row(check["name"], "yes" if check["ok"] else "no", json.dumps(check.get("details"), ensure_ascii=False)[:120])
    console.print(table)
    if not result["ok"]:
        raise typer.Exit(1)


@app.command("benchmark-cross-agent")
def benchmark_cross_agent_cmd(config: Optional[str] = None, limit: int = 5, json_out: bool = False):
    """Run a small deterministic cross-agent/session recall benchmark."""
    from .benchmark import benchmark_cross_agent

    if json_out:
        with redirect_stdout(sys.stderr):
            result = benchmark_cross_agent(config, limit=limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    result = benchmark_cross_agent(config, limit=limit)
    table = Table(title="Cross-agent/session benchmark")
    table.add_column("Kind")
    table.add_column("Count")
    table.add_column("Latency ms")
    for row in result["results"]:
        table.add_row(row["kind"], str(row["count"]), str(row["latency_ms"]))
    console.print(table)
    console.print(f"avg_latency_ms={result['avg_latency_ms']} cross_layer={result['cross_layer_verdict']}")


@app.command("doctor")
def doctor_cmd(config: Optional[str] = None, no_benchmark: bool = False, json_out: bool = False):
    """Run full health/contract/cross-agent diagnostics."""
    from .doctor import doctor

    if json_out:
        with redirect_stdout(sys.stderr):
            result = doctor(config, run_benchmark=not no_benchmark)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    result = doctor(config, run_benchmark=not no_benchmark)
    table = Table(title=f"Super Memory doctor: {result['verdict']}")
    table.add_column("Check")
    table.add_column("OK")
    table.add_column("Severity")
    for check in result["checks"]:
        table.add_row(check["name"], "yes" if check["ok"] else "no", check["severity"])
    console.print(table)
    if result["verdict"] == "fail":
        raise typer.Exit(1)


@app.command("cleanup")
def cleanup_cmd(
    config: Optional[str] = None,
    vacuum: bool = typer.Option(False, "--vacuum", help="Run VACUUM after transactional cleanup"),
    no_integrity_check: bool = typer.Option(False, "--no-integrity-check", help="Skip PRAGMA quick_check"),
    json_out: bool = False,
):
    """Run safe SQLite cleanup: migrations, views, FTS rebuilds, optional VACUUM."""
    from .cleanup import cleanup

    result = cleanup(config_path=config, vacuum=vacuum, integrity_check=not no_integrity_check)
    if json_out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    console.print(result)
    if not result["ok"]:
        raise typer.Exit(1)

@app.command("prune")
def prune_cmd(
    config: Optional[str] = None,
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Dry-run by default; use --no-dry-run to actually delete"),
    source_prefixes: list[str] = typer.Option([], "--source-prefix", help="Prune sources starting with prefix (repeatable)"),
    max_days: Optional[int] = typer.Option(None, "--max-days", help="Prune memories older than N days"),
    json_out: bool = False,
):
    """Prune memories matching retention policy criteria.

    Built-in always-active criteria:
    - Empty openclaw.turn events (source='openclaw.turn', content='')

    Optional:
    --source-prefix: prune sources starting with these prefixes (repeatable)
      e.g. --source-prefix test. --source-prefix benchmark
    --max-days: prune memories older than N days
    --no-dry-run: actually delete (safe default is dry-run)
    """
    from .cleanup import prune
    result = prune(
        config_path=config,
        dry_run=dry_run,
        source_prefixes=source_prefixes if source_prefixes else None,
        max_days=max_days,
    )
    if json_out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    console.print(result)
    if not result.get("ok", False):
        raise typer.Exit(1)


@app.command("migrate-status")
def migrate_status_cmd(config: Optional[str] = None, json_out: bool = False):
    """Show expected SQLite table/migration status."""
    from .doctor import migration_status

    result = migration_status(config)
    if json_out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    console.print(result)
    if not result["ok"]:
        raise typer.Exit(1)


@app.command("entity-upsert")
def entity_upsert_cmd(kind: str, canonical_name: str, alias: list[str] = typer.Option([], "--alias"), config: Optional[str] = None, json_out: bool = False):
    """Upsert a canonical entity/alias for identity resolution."""
    from .entity_registry import upsert_entity

    result = upsert_entity(kind, canonical_name, alias, config_path=config)
    console.print(json.dumps(result, ensure_ascii=False, indent=2) if json_out else str(result))


@app.command("entity-resolve")
def entity_resolve_cmd(name: str, kind: Optional[str] = None, config: Optional[str] = None, json_out: bool = False):
    """Resolve an alias/canonical entity name."""
    from .entity_registry import resolve_entity

    result = resolve_entity(name, kind, config_path=config)
    console.print(json.dumps(result, ensure_ascii=False, indent=2) if json_out else str(result))


@semantic_app.command("doctor")
def semantic_doctor_cmd(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    query: str = typer.Option("semantic recall smoke test", "--query"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Check semantic-mode prerequisites: config, sqlite-vec, Ollama, and vector DB."""
    from .semantic import semantic_doctor

    result = semantic_doctor(config, query=query)
    if json_out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    table = Table(title=f"Semantic doctor: {result['verdict']}")
    table.add_column("Check")
    table.add_column("OK")
    table.add_column("Severity")
    table.add_column("Detail")
    for check in result["checks"]:
        table.add_row(check["name"], "yes" if check["ok"] else "no", check["severity"], json.dumps(check.get("detail"), ensure_ascii=False)[:80])
    console.print(table)
    if not result["ok"]:
        raise typer.Exit(1)


@semantic_app.command("index")
def semantic_index_cmd(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    rebuild: bool = typer.Option(False, "--rebuild", help="Drop/recreate vector index before indexing"),
    batch_size: int = typer.Option(8, "--batch-size", min=1, max=128),
    limit: Optional[int] = typer.Option(None, "--limit", help="Index only the first N memories for smoke tests"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Build/update data/vectors.sqlite3 from workspace_markdown memories."""
    from .semantic import semantic_index

    result = semantic_index(config, rebuild=rebuild, batch_size=batch_size, limit=limit)
    if json_out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    console.print(result)
    if not result.get("ok", False):
        raise typer.Exit(1)


@semantic_app.command("verify")
def semantic_verify_cmd(
    query: str = typer.Argument("semantic recall smoke test"),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    limit: int = typer.Option(5, "--limit"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Run a semantic KNN query and hydrate results from the memory DB."""
    from .semantic import semantic_verify

    result = semantic_verify(config, query=query, limit=limit)
    if json_out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    console.print(result)
    if not result.get("ok", False):
        raise typer.Exit(1)


@app.command("status")
def status_cmd(config: Optional[str] = None, json_out: bool = False):
    cfg = load_config(config)
    # Ensure schema exists/upgrades before direct status reads.
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        count = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        layers = conn.execute("SELECT layer, COUNT(*) as c FROM memories GROUP BY layer").fetchall()
        edges = conn.execute("SELECT COUNT(*) as c FROM graph_edges").fetchone()["c"]
        drawers = conn.execute("SELECT COUNT(*) as c FROM palace_drawers").fetchone()["c"]
        honcho_events = conn.execute("SELECT COUNT(*) as c FROM honcho_events").fetchone()["c"]

    if json_out:
        console.print(
            json.dumps(
                {
                    "total_memories": count,
                    "layers": {r["layer"]: r["c"] for r in layers},
                    "graph_edges": edges,
                    "palace_drawers": drawers,
                    "honcho_events": honcho_events,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    t = Table(title="Super Memory Status")
    t.add_column("Metric")
    t.add_column("Value")
    t.add_row("Total memories", str(count))
    for r in layers:
        t.add_row(f"  {r['layer']}", str(r["c"]))
    t.add_row("Graph edges", str(edges))
    t.add_row("Palace drawers", str(drawers))
    t.add_row("Honcho events", str(honcho_events))
    console.print(t)
