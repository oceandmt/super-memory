"""Versioned corpus evaluator for deterministic semantic classification."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from .semantic_classifier import classify_semantic_type

def evaluate_corpus(path: str | Path) -> dict[str, Any]:
    rows=[json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    labels=sorted({r["type"] for r in rows}); counts=defaultdict(lambda:[0,0,0]); confusion=defaultdict(int)
    for row in rows:
        pred=classify_semantic_type(row["text"]).semantic_type; gold=row["type"]; confusion[(gold,pred)]+=1
        for label in labels:
            if pred==label and gold==label: counts[label][0]+=1
            elif pred==label: counts[label][1]+=1
            elif gold==label: counts[label][2]+=1
    f1={}
    for label,(tp,fp,fn) in counts.items(): f1[label]=0 if not tp else 2*tp/(2*tp+fp+fn)
    nonblock=sum(r["type"]!="blocker" for r in rows); blocker_fp=sum(n for (g,p),n in confusion.items() if g!="blocker" and p=="blocker")/max(1,nonblock)
    df=sum(n for (g,p),n in confusion.items() if {g,p}=={"decision","fact"})/max(1,sum(r["type"] in {"decision","fact"} for r in rows))
    return {"corpus_version":"1","cases":len(rows),"macro_f1":round(sum(f1.values())/len(f1),4),"blocker_false_positive_rate":round(blocker_fp,4),"decision_fact_confusion_rate":round(df,4),"per_type_f1":{k:round(v,4) for k,v in f1.items()},"gate":{"macro_f1":sum(f1.values())/len(f1)>=.90,"blocker_false_positives":blocker_fp<.02,"decision_fact_confusion":df<.03}}
