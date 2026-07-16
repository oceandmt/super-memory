"""Labeled, reproducible benchmark for meaningful canonical-memory writes.

This module is deliberately independent of the production classifiers: it measures
semantic policy outcomes and can therefore be used as a release gate without
teaching to (or mutating) the classifier implementation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

_TOKEN = re.compile(r"[\w./=-]+", re.UNICODE)
NOISE = (
    "thanks", "thank you", "how are you", "typing", "please wait", "task started",
    "successfully completed", "as an ai language model", "let me know if",
    "đang nhập", "vui lòng chờ", "cảm ơn bạn", "处理中", "请稍候", "谢谢",
)
SPECULATION = ("maybe", "possibly", "i guess", "probably", "perhaps", "có lẽ", "也许", "未检查", "chưa kiểm tra")
DURABLE = (
    "decision", "decided", "verified", "workflow", "runbook", "contract", "policy",
    "preference", "prefers", "fact", "lesson", "deadline", "owner", "rollback",
    "quyết định", "đã xác minh", "thích", "quy trình", "决定", "决策", "検証済み", "规范",
)
EVIDENCE = ("test", "commit", "report", "adr-", "evidence", "audit", "verified", "xác minh", "kiểm thử", "検証", "证据")
GENERATED = ("generated summary", "approved generated summary", "生成摘要", "tóm tắt được tạo")
UNAPPROVED = ("unapproved", "no one approved", "未经人工批准", "chưa được con người phê duyệt")

@dataclass(frozen=True)
class Assessment:
    promote: bool
    score: float
    reasons: tuple[str, ...]


def assess_write(text: str, *, origin: str = "human", approved: bool = False, threshold: float = 0.55,
                 use_noise_filter: bool = True, enforce_approval: bool = True) -> Assessment:
    low = " ".join(text.lower().split())
    reasons: list[str] = []
    generated = origin == "generated" or any(x in low for x in GENERATED)
    if generated and enforce_approval and (not approved or any(x in low for x in UNAPPROVED)):
        return Assessment(False, 0.0, ("generated_requires_explicit_approval",))
    tokens = _TOKEN.findall(low)
    score = 0.0
    durable_hits = sum(x in low for x in DURABLE)
    evidence_hits = sum(x in low for x in EVIDENCE)
    if len(tokens) >= 8 or (len(text) >= 20 and re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text)):
        score += .22; reasons.append("substantive_length")
    if durable_hits:
        score += min(.48, .38 + .05 * (durable_hits - 1)); reasons.append("durable_semantics")
    if evidence_hits:
        score += min(.28, .20 + .04 * (evidence_hits - 1)); reasons.append("evidence")
    if generated and approved:
        score += .20; reasons.append("explicitly_approved_generated_content")
    if re.search(r"(?:/\w|\d{4}-\d{2}-\d{2}|\b\d+\s*(?:days|minutes|utc)|\badr-\d+)", low):
        score += .14; reasons.append("specific_detail")
    if use_noise_filter:
        if any(x in low for x in NOISE):
            score -= .65; reasons.append("transient_or_boilerplate")
        if any(x in low for x in SPECULATION):
            score -= .42; reasons.append("unverified_speculation")
        # Trigger stuffing has many policy words but no normal proposition/evidence.
        if (durable_hits >= 3 and evidence_hits >= 2 and len(tokens) < 14) or "remember remember" in low or "click here to win" in low:
            score -= .9; reasons.append("trigger_stuffing")
    score = max(0.0, min(1.0, score))
    return Assessment(score >= threshold, round(score, 4), tuple(reasons))


def load_corpus(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def evaluate(cases: Iterable[dict[str, Any]], *, threshold: float = .55,
             use_noise_filter: bool = True, enforce_approval: bool = True) -> dict[str, Any]:
    rows = []
    for case in cases:
        result = assess_write(case["text"], origin=case.get("origin", "human"),
                              approved=bool(case.get("approved")), threshold=threshold,
                              use_noise_filter=use_noise_filter, enforce_approval=enforce_approval)
        expected = bool(case["useful"])
        rows.append({"id": case["id"], "expected": expected, "promote": result.promote,
                     "score": result.score, "category": case["category"], "language": case["language"],
                     "reasons": list(result.reasons)})
    tp = sum(r["expected"] and r["promote"] for r in rows); fp = sum(not r["expected"] and r["promote"] for r in rows)
    fn = sum(r["expected"] and not r["promote"] for r in rows); noise = sum(not r["expected"] for r in rows)
    unapproved = [r for r, c in zip(rows, cases) if c.get("origin") == "generated" and not c.get("approved") and r["promote"]]
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"threshold": threshold, "counts": {"tp": tp, "fp": fp, "fn": fn, "noise": noise},
            "useful_write_precision": round(precision, 4), "useful_write_recall": round(recall, 4),
            "noise_promotion_rate": round(fp / noise if noise else 0.0, 4),
            "unapproved_generated_promotions": len(unapproved),
            "false_cases": [r for r in rows if r["expected"] != r["promote"]], "rows": rows}


def benchmark(corpus_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    cases = load_corpus(corpus_path)
    primary = evaluate(cases)
    report = {"schema_version": 1, "corpus_size": len(cases), "targets": {
        "useful_write_precision": .95, "useful_write_recall": .90,
        "noise_promotion_rate_lt": .01, "unapproved_generated_promotions": 0},
        "primary": primary,
        "threshold_report": [evaluate(cases, threshold=t) for t in (.45, .50, .55, .60, .65)],
        "ablations": {"without_noise_filter": evaluate(cases, use_noise_filter=False),
                      "without_approval_guard": evaluate(cases, enforce_approval=False)}}
    p = primary
    report["passed"] = (p["useful_write_precision"] >= .95 and p["useful_write_recall"] >= .90
                        and p["noise_promotion_rate"] < .01 and p["unapproved_generated_promotions"] == 0)
    report["actionable_false_cases"] = [{**r, "action": "review labeling or tune semantic evidence/penalties"}
                                         for r in p["false_cases"]]
    if output_path:
        path = Path(output_path); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
