from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import load_config
from .compat import memory_get_compatible, memory_search_compatible
from .models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from .promote import PROMOTABLE_TYPES, promote_both
from .service import SuperMemoryService
from .storage import SuperMemoryStore

app = typer.Typer(help="Local multi-layer memory app for OpenClaw")
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
