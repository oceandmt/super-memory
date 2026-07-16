"""Versioned semantic trust calibration.

Trust dimensions remain independent evidence.  In particular, graph degree or
edge count is structural metadata and is deliberately not accepted as a trust
input.
"""
from __future__ import annotations

import json, math, sqlite3, uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

DIMENSIONS = ("source_reliability", "content_verification", "extraction_confidence",
              "relation_confidence", "correction_history", "freshness")


def _unit(value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("trust values must be finite probabilities in [0, 1]")
    return value

@dataclass(frozen=True)
class TrustEvidence:
    source_reliability: float
    content_verification: float
    extraction_confidence: float
    relation_confidence: float
    correction_history: float
    freshness: float
    def __post_init__(self):
        for name in DIMENSIONS: _unit(getattr(self, name))

@dataclass(frozen=True)
class CalibrationModel:
    version: str
    weights: dict[str, float]
    intercept: float = 0.0
    def __post_init__(self):
        if set(self.weights) != set(DIMENSIONS):
            raise ValueError(f"weights must contain exactly {DIMENSIONS}")
        if not self.version: raise ValueError("model version is required")
        if any(not math.isfinite(float(v)) for v in self.weights.values()):
            raise ValueError("weights must be finite")
    def predict(self, evidence: TrustEvidence) -> float:
        # Logistic calibration combines semantic dimensions only; structural
        # graph properties belong in ranking diagnostics, never semantic trust.
        z = float(self.intercept) + sum(self.weights[k] * getattr(evidence, k) for k in DIMENSIONS)
        return 1 / (1 + math.exp(-max(-40.0, min(40.0, z))))

DEFAULT_MODEL = CalibrationModel("trust-v1", {k: 1/len(DIMENSIONS) for k in DIMENSIONS}, -0.5)

def brier_score(predictions: Sequence[float], outcomes: Sequence[int | bool]) -> float:
    if len(predictions) != len(outcomes) or not predictions: raise ValueError("equal non-empty samples required")
    return sum((_unit(p) - int(bool(y))) ** 2 for p, y in zip(predictions, outcomes)) / len(predictions)

def expected_calibration_error(predictions: Sequence[float], outcomes: Sequence[int | bool], bins: int = 10) -> float:
    if len(predictions) != len(outcomes) or not predictions: raise ValueError("equal non-empty samples required")
    if bins < 1 or bins > 100: raise ValueError("bins must be in [1, 100]")
    buckets=[[] for _ in range(bins)]
    for p,y in zip(predictions,outcomes):
        p=_unit(p); buckets[min(int(p*bins), bins-1)].append((p,int(bool(y))))
    n=len(predictions)
    return sum(len(b)/n * abs(sum(p for p,_ in b)/len(b)-sum(y for _,y in b)/len(b)) for b in buckets if b)

def evaluate(model: CalibrationModel, samples: Iterable[tuple[TrustEvidence, int | bool]], bins: int = 10) -> dict:
    pairs=list(samples); predictions=[model.predict(x) for x,_ in pairs]; outcomes=[y for _,y in pairs]
    return {"model_version": model.version, "samples": len(pairs), "brier_score": brier_score(predictions,outcomes), "ece": expected_calibration_error(predictions,outcomes,bins), "bins": bins}

def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS trust_calibration_models(version TEXT PRIMARY KEY, weights_json TEXT NOT NULL, intercept REAL NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS trust_calibration_events(id TEXT PRIMARY KEY, memory_id TEXT, model_version TEXT NOT NULL, evidence_json TEXT NOT NULL, prediction REAL NOT NULL CHECK(prediction BETWEEN 0 AND 1), outcome INTEGER CHECK(outcome IN (0,1)), created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_trust_calibration_created ON trust_calibration_events(created_at);
    """)

def save_model(conn: sqlite3.Connection, model: CalibrationModel) -> None:
    init_schema(conn); conn.execute("INSERT OR REPLACE INTO trust_calibration_models VALUES(?,?,?,?)",(model.version,json.dumps(model.weights,sort_keys=True),model.intercept,datetime.now(timezone.utc).isoformat()))

def record_event(conn: sqlite3.Connection, evidence: TrustEvidence, *, model: CalibrationModel=DEFAULT_MODEL, memory_id: str|None=None, outcome: bool|None=None) -> dict:
    init_schema(conn); prediction=model.predict(evidence); event_id=f"cal:{uuid.uuid4().hex}"
    conn.execute("INSERT INTO trust_calibration_events VALUES(?,?,?,?,?,?,?)",(event_id,memory_id,model.version,json.dumps(asdict(evidence),sort_keys=True),prediction,None if outcome is None else int(outcome),datetime.now(timezone.utc).isoformat()))
    return {"id":event_id,"model_version":model.version,"prediction":prediction}
