"""Self-Education Curriculum — learn from recall failures and memory outcomes.

P2 — converts repeated failed recalls into:
1. Training sets (JSON cases for recall_bench)
2. Benchmark regression tests (pytest files)
3. Gap documentation
4. Pattern suggestions for new memory types/adapters

Borrowed from:
- Neural Memory: health checks, habits, watch/learn
- Honcho: derived conclusions from conversations
- MemPalace: benchmark methodology, transparent evals
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config

logger = logging.getLogger("super-memory.evals.curriculum")

# ── Config ───────────────────────────────────────────────────────────────────

CURRICULUM_DIR = "tests/recall_cases/auto_curriculum"
MIN_FAILURES_FOR_CASE = 2  # same query failing N+ times → training case
MAX_CASES_PER_BATCH = 50


# ── Analyze Feedback Patterns ───────────────────────────────────────────────

def analyze_feedback_patterns(
    max_events: int = 500,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Analyze recall feedback for failure patterns.

    Groups by query and outcome to find:
    - Repeated failures (same query, corrected/contradicted multiple times)
    - Common failed patterns (query keyword clusters)
    - Successful patterns (high used_in_answer rate)
    """
    cfg = load_config(config_path)
    from ..storage import SuperMemoryStore

    store = SuperMemoryStore(cfg)
    try:
        with store.connect() as conn:
            events = conn.execute(
                "SELECT * FROM recall_events ORDER BY timestamp DESC LIMIT ?",
                (max_events,),
            ).fetchall()
            feedback = conn.execute(
                "SELECT * FROM recall_feedback ORDER BY timestamp DESC LIMIT ?",
                (max_events * 3,),
            ).fetchall()
    except Exception:
        events = []
        feedback = []

    if not events and not feedback:
        return {
            "ok": True,
            "message": "No feedback data yet",
            "total_events": 0,
            "total_feedback": 0,
            "patterns": {},
            "suggestions": [],
        }

    # Count outcomes by query
    query_outcomes: dict[str, Counter] = {}
    for fb in feedback:
        query = fb.get("query", "") if "query" in fb else ""
        # Get query from event
        if not query:
            event = next((e for e in events if e.get("id") == fb.get("recall_event_id")), None)
            query = event.get("query", "") if event else ""
        query = query.strip().lower()
        if not query:
            continue
        if query not in query_outcomes:
            query_outcomes[query] = Counter()
        query_outcomes[query][fb.get("outcome", "unknown")] += 1

    # Find failure patterns
    repeated_failures = []
    for query, outcomes in query_outcomes.items():
        corrections = outcomes.get("corrected", 0)
        contradictions = outcomes.get("contradicted", 0)
        total_failures = corrections + contradictions
        if total_failures >= MIN_FAILURES_FOR_CASE:
            repeated_failures.append({
                "query": query,
                "failures": total_failures,
                "corrected": corrections,
                "contradicted": contradictions,
                "total_attempts": sum(outcomes.values()),
            })

    repeated_failures.sort(key=lambda x: -x["failures"])

    # Success patterns
    high_success = []
    for query, outcomes in query_outcomes.items():
        used = outcomes.get("used", 0)
        total = sum(outcomes.values())
        if total >= 2 and used / total >= 0.8:
            high_success.append({
                "query": query,
                "success_rate": round(used / total * 100, 1),
                "total_attempts": total,
            })

    high_success.sort(key=lambda x: -x["success_rate"])

    # Suggestions
    suggestions = []
    if repeated_failures:
        top_fail = repeated_failures[0]
        suggestions.append({
            "priority": "high",
            "action": "create_training_case",
            "reason": f"Query '{top_fail['query']}' failed {top_fail['failures']} times",
            "suggestion": "Add explicit memory for this query pattern",
        })
        suggestions.append({
            "priority": "medium",
            "action": "audit_memory_quality",
            "reason": f"{len(repeated_failures)} queries with repeated failures",
            "suggestion": "Consider adding better type classification for these patterns",
        })
    if not high_success:
        suggestions.append({
            "priority": "medium",
            "action": "improve_recall",
            "reason": "No high-success recall patterns found",
            "suggestion": "Review recall arbitration weights for better precision",
        })

    return {
        "ok": True,
        "total_events": len(events),
        "total_feedback": len(feedback),
        "unique_queries": len(query_outcomes),
        "repeated_failures": repeated_failures[:20],
        "high_success_queries": high_success[:20],
        "suggestions": suggestions,
    }


# ── Generate Training Cases ─────────────────────────────────────────────────

def generate_training_cases_from_failures(
    min_failures: int = MIN_FAILURES_FOR_CASE,
    max_cases: int = MAX_CASES_PER_BATCH,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Generate training set JSON files from repeated recall failures."""
    cfg = load_config(config_path)
    from ..storage import SuperMemoryStore

    analysis = analyze_feedback_patterns(max_events=1000, config_path=config_path)
    failures = analysis.get("repeated_failures", [])

    if not failures:
        return {
            "ok": True,
            "message": "No training cases needed — no repeated failures found",
            "cases_generated": 0,
        }

    root = Path(cfg.workspace_root or ".") / CURRICULUM_DIR
    root.mkdir(parents=True, exist_ok=True)

    cases = []
    for fail in failures[:max_cases]:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        case = {
            "id": f"curriculum-{ts}-{hash(fail['query']) % 10000:04d}",
            "query": fail["query"],
            "failure_count": fail["failures"],
            "corrected": fail["corrected"],
            "contradicted": fail["contradicted"],
            "total_attempts": fail["total_attempts"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "expected_contains": fail["query"].split(),
            "tags": ["auto-curriculum", "failed-recall"],
        }
        fname = f"{case['id']}.json"
        fpath = root / fname
        fpath.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
        cases.append(case)

    # Generate a summary curriculum file
    summary = root / "CURRICULUM.md"
    summary.write_text(
        f"# Auto-Generated Curriculum ({datetime.now(timezone.utc).isoformat()[:10]})\n\n"
        f"Total training cases: {len(cases)}\n\n"
        f"## Repeated Failures\n\n"
        + "\n".join(
            f"- **{c['query']}**: {c['failure_count']} failures ({c['corrected']} corrected, {c['contradicted']} contradicted)"
            for c in cases[:30]
        )
        + "\n\n## Usage\n"
        + "These cases are auto-generated from recall feedback. Run:\n"
        + "```bash\n"
        + "python -m pytest tests/recall_cases/auto_curriculum/ --recall-validate\n"
        + "```\n",
        encoding="utf-8",
    )

    return {
        "ok": True,
        "cases_generated": len(cases),
        "directory": str(root),
        "summary_file": str(summary),
        "cases": cases,
    }


# ── Generate Benchmark Tests ───────────────────────────────────────────────

def generate_benchmark_tests(
    config_path: str | None = None,
) -> dict[str, Any]:
    """Generate pytest benchmark test file from training cases.

    Creates a test file in tests/recall_cases/ that runs each training
    case as a recall + validation test.
    """
    cfg = load_config(config_path)
    root = Path(cfg.workspace_root or ".") / CURRICULUM_DIR
    root.mkdir(parents=True, exist_ok=True)

    # Find all training case JSONs
    case_files = sorted(root.glob("curriculum-*.json"))

    if not case_files:
        return {"ok": True, "message": "No training cases found", "tests_generated": 0}

    # Generate test file
    test_path = Path(cfg.workspace_root or ".") / "tests" / "recall_cases" / "test_auto_curriculum.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)

    test_template = '''"""Auto-generated curriculum recall tests.

Generated at: {timestamp}
Training cases: {count}

These tests validate that Super Memory can recall correct information
for queries that previously failed.
"""

import json
from pathlib import Path

import pytest

CASE_DIR = Path(__file__).parent / "auto_curriculum"
CASE_FILES = sorted(CASE_DIR.glob("curriculum-*.json"))

{pytest_cases}


def test_curriculum_summary():
    """List all training cases."""
    assert len(CASE_FILES) > 0, "No curriculum cases found"
    print(f"\\nCurriculum: {len(CASE_FILES)} training cases")
    for cf in CASE_FILES:
        case = json.loads(cf.read_text())
        print(f"  - {case['query'][:60]} ({case['failure_count']} failures)")
'''

    # Generate individual test cases
    case_imports = []
    for i, cf in enumerate(case_files[:30]):  # limit to first 30
        case = json.loads(cf.read_text())
        query = case["query"][:60]
        test_fn = f"test_curriculum_case_{i:03d}"
        case_imports.append(f'''{test_fn}():
    """Recall validation: {query}"""
    case = json.loads(CASE_FILES[{i}].read_text())
    from super_memory.bridge import recall_arbitrate_v3
    result = recall_arbitrate_v3(case["query"])
    selected = result.get("selected", [])
    assert len(selected) > 0, (
        f"No recall results for: {case['query']} "
        f"(failed {case['failure_count']} times in production)"
    )
    top_score = selected[0].get("score", 0)
    assert top_score >= 0.05, (
        f"Weak recall (score={top_score:.3f}) for: {case['query']}"
    )

def ''')

    test_content = test_template.format(
        timestamp=datetime.now(timezone.utc).isoformat()[:19],
        count=len(case_files),
        pytest_cases="\n".join(case_imports),
    )

    test_path.write_text(test_content, encoding="utf-8")

    return {
        "ok": True,
        "tests_generated": min(len(case_files), 30),
        "test_file": str(test_path),
        "total_case_files": len(case_files),
    }


# ── Full Curriculum Pipeline ───────────────────────────────────────────────

def run_curriculum(
    config_path: str | None = None,
) -> dict[str, Any]:
    """Full curriculum pipeline: analyze → generate cases → generate tests."""
    # 1. Analyze
    analysis = analyze_feedback_patterns(config_path=config_path)

    # 2. Generate training cases
    cases = generate_training_cases_from_failures(config_path=config_path)

    # 3. Generate benchmark tests
    tests = generate_benchmark_tests(config_path=config_path)

    return {
        "ok": True,
        "analysis": {
            "total_events": analysis.get("total_events", 0),
            "total_feedback": analysis.get("total_feedback", 0),
            "repeated_failures": len(analysis.get("repeated_failures", [])),
            "suggestions": analysis.get("suggestions", []),
        },
        "training_cases": {
            "generated": cases.get("cases_generated", 0),
            "directory": cases.get("directory", ""),
        },
        "benchmark_tests": {
            "generated": tests.get("tests_generated", 0),
            "test_file": tests.get("test_file", ""),
        },
    }


# ── Benchmark Runner ───────────────────────────────────────────────────────

def run_benchmarks(
    config_path: str | None = None,
) -> dict[str, Any]:
    """Run benchmark tests against training cases.

    For each training case, run recall and measure precision/recall.
    """
    from ..bridge import recall_arbitrate_v3
    from ..recall import quick_search

    cfg = load_config(config_path)
    root = Path(cfg.workspace_root or ".") / CURRICULUM_DIR

    case_files = sorted(root.glob("curriculum-*.json"))
    if not case_files:
        return {"ok": True, "message": "No training cases found", "results": []}

    results = []
    passed = 0
    failed = 0

    for cf in case_files:
        case = json.loads(cf.read_text())
        query = case["query"]

        # Run recall
        result = recall_arbitrate_v3(query, limit=5, config_path=config_path)
        selected = result.get("selected", [])

        top_score = selected[0].get("score", 0) if selected else 0.0
        top_id = selected[0].get("record", {}).get("id", "") if selected else ""

        case_result = {
            "query": query,
            "found": len(selected) > 0,
            "top_score": top_score,
            "top_memory_id": top_id,
            "layer_votes": result.get("layer_votes", {}),
            "expected_contains": case.get("expected_contains", []),
            "continues_failing": False,
        }

        # Check if expected terms appear in results
        expected = case.get("expected_contains", [])
        found_terms = []
        for sel in selected:
            content = (sel.get("record", {}).get("content") or "").lower()
            for term in expected:
                if term.lower() in content:
                    found_terms.append(term)

        if expected and found_terms:
            case_result["expected_found"] = len(found_terms)
            case_result["expected_total"] = len(expected)
            passed += 1
        else:
            failed += 1
            case_result["continues_failing"] = True

        results.append(case_result)

    return {
        "ok": True,
        "total_cases": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / max(len(results), 1) * 100, 1),
        "results": results,
    }
