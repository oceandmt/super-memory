"""Evidence-only recall benchmarks and release gating.

The benchmark cases are an *oracle*, never a recall corpus. Gate execution is
read-only: it does not seed cases, write memories, or use case filenames or
expected labels when invoking retrieval. Only returned evidence is scored.
"""
from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from .config import load_config

RecallCallable = Callable[..., dict[str, Any]]


def ranked_metrics(
    ranked_ids: list[str], relevant: dict[str, float] | list[str], *, k: int = 10
) -> dict[str, float]:
    """Standard deterministic IR metrics (graded relevance is supported)."""
    gains = relevant if isinstance(relevant, dict) else {item: 1.0 for item in relevant}
    top = ranked_ids[:k]
    recall5 = len(set(ranked_ids[:5]) & set(gains)) / max(len(gains), 1)
    reciprocal = next((1.0 / rank for rank, mid in enumerate(top, 1) if mid in gains), 0.0)
    dcg = sum((2 ** gains.get(mid, 0.0) - 1) / math.log2(rank + 1) for rank, mid in enumerate(top, 1))
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum((2 ** gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(ideal, 1))
    return {"recall_at_5": recall5, "mrr_at_10": reciprocal, "ndcg_at_10": dcg / idcg if idcg else 0.0}


def evaluate_ranked_cases(
    cases: list[dict[str, Any]], recall_callable: RecallCallable, *, limit: int = 10
) -> dict[str, Any]:
    """Evaluate a query oracle, including provenance and negative safety labels.

    The callable may accept ``case`` for deterministic test backends, but no
    oracle relevance labels are passed to it.
    """
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    counters = {"hits": 0, "citations": 0, "unauthorized": 0, "deleted": 0, "stale": 0, "returned": 0}
    for case in cases:
        started = time.perf_counter()
        try:
            payload = recall_callable(query=case["query"], limit=limit, case=case)
        except TypeError:
            payload = recall_callable(case["query"], limit, None)
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        evidence = list(_iter_evidence(payload))[:limit]
        ids = [item["memory_id"] for item in evidence]
        metrics = ranked_metrics(ids, case.get("relevance", case.get("expected_memory_ids", [])), k=10)
        expected_citations = case.get("citations", {})
        relevant_hits = [item for item in evidence if item["memory_id"] in expected_citations]
        citation_hits = sum(item["citation"] == expected_citations[item["memory_id"]] for item in relevant_hits)
        forbidden = set(case.get("unauthorized_ids", []))
        deleted = set(case.get("deleted_ids", []))
        stale = set(case.get("stale_ids", []))
        counters["hits"] += len(relevant_hits); counters["citations"] += citation_hits
        counters["unauthorized"] += sum(mid in forbidden for mid in ids)
        counters["deleted"] += sum(mid in deleted for mid in ids)
        counters["stale"] += sum(mid in stale for mid in ids)
        counters["returned"] += len(ids)
        rows.append({"id": case.get("id"), "category": case.get("category"), **metrics,
                     "citation_correctness": citation_hits / max(len(relevant_hits), 1),
                     "latency_ms": round(elapsed, 3), "ranked_ids": ids})
    denominator = max(counters["returned"], 1)
    mean = lambda key: sum(row[key] for row in rows) / max(len(rows), 1)
    return {
        "case_count": len(rows), "recall_at_5": mean("recall_at_5"),
        "mrr_at_10": mean("mrr_at_10"), "ndcg_at_10": mean("ndcg_at_10"),
        "citation_correctness": counters["citations"] / max(counters["hits"], 1),
        "unauthorized_hit_rate": counters["unauthorized"] / denominator,
        "deleted_hit_rate": counters["deleted"] / denominator,
        "stale_hit_rate": counters["stale"] / denominator,
        "latency_ms": {"mean": statistics.fmean(latencies) if latencies else 0.0,
                       "p95": sorted(latencies)[max(0, math.ceil(.95 * len(latencies)) - 1)] if latencies else 0.0},
        "cases": rows,
    }

# Kept for explicit fixture authoring/backward compatibility. release_gate()
# never calls seed_default_recall_cases().
DEFAULT_RECALL_CASES = [
    {"name": "contract-driven-memory-engine", "query": "contract-driven memory engine MemoryEnvelope WriteGateResult", "expected_contains": ["memory", "contract"]},
    {"name": "recall-arbitration-v4", "query": "Recall Arbitration V4 channels quality trust hydration", "expected_contains": ["recall"]},
    {"name": "drawer-closet-hydration", "query": "drawer closet hydration evidence citations", "expected_contains": ["hydrated"]},
    {"name": "duplicate-resolution-v2", "query": "duplicate_resolution_v2 soft-delete duplicate clusters semantic merge", "expected_contains": ["duplicate"]},
    {"name": "project-inference-backfill", "query": "project inference backfill project metadata super-memory-github", "expected_contains": ["project"]},
]


def case_dir(config_path: str | None = None, *, create: bool = False) -> Path:
    """Return the external oracle directory; create it only for case authoring."""
    cfg = load_config(config_path)
    path = Path(cfg.workspace_root) / "projects" / "super-memory-github" / "tests" / "recall_cases"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def create_recall_case(
    query: str,
    expected_contains: list[str] | None = None,
    expected_memory_ids: list[str] | None = None,
    must_not_include: list[str] | None = None,
    name: str | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Explicitly author an oracle case. This is not used by gate execution."""
    import datetime
    import re

    slug = name or re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:60] or "case"
    path = case_dir(config_path, create=True) / f"{slug}.json"
    case = {
        "query": query,
        "expected_contains": expected_contains or [],
        "expected_memory_ids": expected_memory_ids or [],
        "must_not_include": must_not_include or [],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path), "case": case}


def seed_default_recall_cases(config_path: str | None = None, overwrite: bool = False) -> dict[str, Any]:
    """Explicit fixture-authoring helper; never invoked by a benchmark or gate."""
    created: list[dict[str, Any]] = []
    skipped: list[str] = []
    for case in DEFAULT_RECALL_CASES:
        path = case_dir(config_path, create=True) / f"{case['name']}.json"
        if path.exists() and not overwrite:
            skipped.append(str(path))
            continue
        created.append(
            create_recall_case(
                query=case["query"],
                expected_contains=case.get("expected_contains", []),
                must_not_include=case.get("must_not_include", []),
                name=case["name"],
                config_path=config_path,
            )
        )
    return {
        "ok": True,
        "explicit_authoring_only": True,
        "created_count": len(created),
        "skipped_count": len(skipped),
        "created": created,
        "skipped": skipped,
    }


def _default_recall(query: str, limit: int, config_path: str | None) -> dict[str, Any]:
    # Lazy import avoids a bridge -> benchmark -> bridge import cycle.
    from .bridge import recall

    return recall(query, limit=limit, config_path=config_path)


def _invoke_recall(fn: RecallCallable, query: str, k: int, config_path: str | None) -> dict[str, Any]:
    """Invoke a production-like retrieval fixture with the public recall shape."""
    try:
        result = fn(query=query, limit=k, config_path=config_path)
    except TypeError as keyword_error:
        # Small fixtures often expose positional (query, limit, config_path).
        try:
            result = fn(query, k, config_path)
        except TypeError:
            raise keyword_error
    if not isinstance(result, dict):
        raise TypeError("recall callable must return a dict payload")
    return result


def _iter_evidence(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield only returned recall evidence, never the query/case/oracle payload."""
    seen: set[tuple[str, str]] = set()
    for key in ("selected", "selected_memories", "answer_context", "results", "records"):
        rows = payload.get(key) or []
        if not isinstance(rows, list):
            continue
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            record = raw.get("record") if isinstance(raw.get("record"), dict) else raw
            content = record.get("content") or record.get("text") or record.get("snippet") or ""
            memory_id = record.get("id") or record.get("memory_id") or raw.get("memory_id") or raw.get("id") or ""
            citation = raw.get("citation") or record.get("citation") or record.get("source") or raw.get("source") or raw.get("path") or ""
            marker = (str(memory_id), str(content))
            if marker in seen:
                continue
            seen.add(marker)
            yield {"memory_id": str(memory_id), "content": str(content), "citation": str(citation)}


def _load_cases(directory: Path, limit: int) -> tuple[list[tuple[Path, dict[str, Any]]], list[dict[str, str]]]:
    loaded: list[tuple[Path, dict[str, Any]]] = []
    errors: list[dict[str, str]] = []
    if not directory.is_dir():
        return loaded, [{"file": str(directory), "error": "oracle_directory_missing"}]
    for path in sorted(directory.glob("*.json"))[: max(0, limit)]:
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(case, dict):
                raise ValueError("case must be a JSON object")
            loaded.append((path, case))
        except Exception as exc:
            errors.append({"file": str(path), "error": f"{type(exc).__name__}: {exc}"})
    return loaded, errors


def _oracle_separation(directory: Path, config_path: str | None) -> dict[str, Any]:
    """Prove the oracle is outside the configured retrieval workspace.

    A production retriever may index arbitrary files below ``workspace_root``.
    Merely omitting labels from the recall call is therefore insufficient when
    the oracle itself lives below that root.  Fail before invoking retrieval so
    labels and filenames cannot become corpus data through another indexer.
    """
    cfg = load_config(config_path)
    oracle = directory.expanduser().resolve(strict=False)
    workspace = Path(cfg.workspace_root).expanduser().resolve(strict=False)
    inside_workspace = oracle == workspace or workspace in oracle.parents
    return {
        "ok": not inside_workspace,
        "oracle_path": str(oracle),
        "workspace_root": str(workspace),
        "inside_retrieval_workspace": inside_workspace,
    }


def _evaluate_case(path: Path, case: dict[str, Any], payload: dict[str, Any], elapsed_ms: float) -> dict[str, Any]:
    query = case.get("query")
    labels = [str(x).strip().lower() for x in (case.get("relevant_contains") or case.get("expected_contains") or []) if str(x).strip()]
    expected_ids = [str(x) for x in case.get("expected_memory_ids", []) if str(x)]
    forbidden = [str(x).strip().lower() for x in case.get("must_not_include", []) if str(x).strip()]
    evidence = list(_iter_evidence(payload))
    visible = [item for item in evidence if item["content"].strip()]
    visible_text = "\n".join(item["content"] for item in visible).lower()
    selected_ids = [item["memory_id"] for item in evidence if item["memory_id"]]

    label_hits = {label: label in visible_text for label in labels}
    relevant_items = [
        item for item in visible
        if item["memory_id"] in expected_ids
        or any(label in item["content"].lower() for label in labels)
    ]
    precision = len(relevant_items) / len(visible) if visible else 0.0
    label_coverage = sum(label_hits.values()) / len(labels) if labels else None
    id_recall = sum(mid in selected_ids for mid in expected_ids) / len(expected_ids) if expected_ids else None
    visibility = len(visible) / len(evidence) if evidence else 0.0

    oracle_dir = str(path.parent.resolve())
    leaked_sources = [
        item["citation"] for item in evidence
        if item["citation"] and (
            str(path.resolve()) in item["citation"]
            or oracle_dir in item["citation"]
            or path.name in item["citation"]
        )
    ]
    oracle_content_markers = {
        str(path.resolve()).lower(),
        oracle_dir.lower(),
        path.name.lower(),
    }
    leaked_content_markers = sorted({
        marker
        for marker in oracle_content_markers
        if marker and marker in visible_text
    })
    forbidden_hits = [token for token in forbidden if token in visible_text]
    leakage_count = len(leaked_sources) + len(leaked_content_markers) + len(forbidden_hits)

    errors: list[str] = []
    if not isinstance(query, str) or not query.strip():
        errors.append("missing_query")
    if not labels and not expected_ids:
        errors.append("missing_relevance_oracle")
    if not evidence:
        errors.append("no_returned_evidence")
    if not visible:
        errors.append("no_visible_evidence")
    if leakage_count:
        errors.append("oracle_or_forbidden_leakage")

    min_precision = float(case.get("min_precision_at_k", case.get("min_precision", 0.01)))
    min_visibility = float(case.get("min_visibility", 1.0))
    relevance_ok = (label_coverage in (None, 1.0)) and (id_recall in (None, 1.0))
    ok = not errors and relevance_ok and precision >= min_precision and visibility >= min_visibility
    return {
        "file": str(path),
        "case_id": str(case.get("id") or path.stem),
        "query": query,
        "ok": ok,
        "errors": errors,
        "selected_ids": selected_ids[:10],
        "evidence": {
            "returned_count": len(evidence),
            "visible_count": len(visible),
            "relevant_count": len(relevant_items),
            "precision_at_k": round(precision, 4),
            "relevance_label_coverage": None if label_coverage is None else round(label_coverage, 4),
            "expected_id_recall": None if id_recall is None else round(id_recall, 4),
            "visibility_rate": round(visibility, 4),
            "leakage_count": leakage_count,
            "forbidden_hits": forbidden_hits,
            "leaked_sources": leaked_sources,
            "leaked_content_markers": leaked_content_markers,
        },
        "thresholds": {"min_precision_at_k": min_precision, "min_visibility": min_visibility},
        "elapsed_ms": elapsed_ms,
    }


def run_recall_benchmark(
    config_path: str | None = None,
    limit: int = 50,
    fast: bool = False,
    *,
    recall_callable: RecallCallable | None = None,
    cases_path: str | Path | None = None,
    min_cases: int = 1,
) -> dict[str, Any]:
    """Run an evidence-only benchmark through the full recall path.

    ``fast`` is retained for call compatibility but cannot select a shortcut.
    Tests should inject ``recall_callable``; release runs default to bridge.recall.
    """
    started = time.perf_counter()
    directory = Path(cases_path) if cases_path is not None else case_dir(config_path, create=False)
    cases, load_errors = _load_cases(directory, limit)
    separation = _oracle_separation(directory, config_path)
    results: list[dict[str, Any]] = []
    fn = recall_callable or _default_recall

    for path, case in cases:
        t0 = time.perf_counter()
        if not separation["ok"]:
            results.append({
                "file": str(path),
                "case_id": str(case.get("id") or path.stem),
                "query": case.get("query"),
                "ok": False,
                "errors": ["oracle_inside_retrieval_workspace"],
                "evidence": {
                    "precision_at_k": 0.0,
                    "visibility_rate": 0.0,
                    "leakage_count": 0,
                },
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
            })
            continue
        try:
            query = case.get("query")
            if not isinstance(query, str) or not query.strip():
                payload: dict[str, Any] = {}
            else:
                payload = _invoke_recall(fn, query, int(case.get("k", 10)), config_path)
            result = _evaluate_case(path, case, payload, round((time.perf_counter() - t0) * 1000, 2))
        except Exception as exc:
            result = {
                "file": str(path),
                "case_id": str(case.get("id") or path.stem),
                "query": case.get("query"),
                "ok": False,
                "errors": [f"retrieval_error:{type(exc).__name__}:{exc}"],
                "evidence": {"precision_at_k": 0.0, "visibility_rate": 0.0, "leakage_count": 0},
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
            }
        results.append(result)

    total = len(results)
    passed = sum(bool(item.get("ok")) for item in results)
    precision_values = [float(item.get("evidence", {}).get("precision_at_k", 0.0)) for item in results]
    visibility_values = [float(item.get("evidence", {}).get("visibility_rate", 0.0)) for item in results]
    leakage_count = sum(int(item.get("evidence", {}).get("leakage_count", 0)) for item in results)
    insufficient = total < max(1, int(min_cases))
    total_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "ok": bool(separation["ok"]) and not load_errors and not insufficient and total > 0 and passed == total and leakage_count == 0,
        "mode": "full_production_path",
        "fast_shortcut_used": False,
        "oracle_seeded": False,
        "oracle_directory": str(directory),
        "oracle_separation": separation,
        "minimum_cases": max(1, int(min_cases)),
        "insufficient_cases": insufficient,
        "load_errors": load_errors,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "total_ms": total_ms,
        "avg_ms": round(total_ms / max(total, 1), 2),
        "evidence": {
            "mean_precision_at_k": round(sum(precision_values) / max(total, 1), 4),
            "relevance_rate": round(passed / max(total, 1), 4),
            "mean_visibility_rate": round(sum(visibility_values) / max(total, 1), 4),
            "leakage_count": leakage_count,
        },
        "results": results,
    }


def release_gate(
    config_path: str | None = None,
    limit: int = 100,
    *,
    recall_callable: RecallCallable | None = None,
    cases_path: str | Path | None = None,
    min_cases: int = 5,
) -> dict[str, Any]:
    """Fail-closed release gate. It never creates or seeds its oracle."""
    benchmark = run_recall_benchmark(
        config_path=config_path,
        limit=limit,
        recall_callable=recall_callable,
        cases_path=cases_path,
        min_cases=min_cases,
    )
    return {
        "ok": bool(benchmark.get("ok")),
        "gate": "evidence_only_recall",
        "fail_closed": True,
        "oracle_seeded": False,
        "benchmark": benchmark,
    }
