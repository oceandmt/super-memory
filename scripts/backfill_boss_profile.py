#!/usr/bin/env python3
"""Backfill Boss Honcho profile from canonical markdown memory."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from super_memory.config import load_config  # noqa: E402
from super_memory.honcho.tools import HonchoTools  # noqa: E402

PATTERNS = [
    r"Boss (prefers|expects|wants|needs|likes|uses|default[s]? to) ([^.\n]+)",
    r"(?:User|Boss) preference[:\-]\s*([^.\n]+)",
    r"Default(?: workflow| behavior| rule)?[:\-]\s*([^.\n]+)",
    r"Treat Boss as ([^.\n]+)",
    r"For ([^:\n]+):\s*([^\n]+)",
]


def iter_memory_files(root: Path):
    paths = [root / "MEMORY.md", root / "USER.md"]
    mem = root / "memory"
    if mem.exists():
        paths.extend(sorted(mem.glob("*.md"))[-30:])
        reg = mem / "registers"
        if reg.exists():
            paths.extend(sorted(reg.glob("*.md")))
    seen = set()
    for path in paths:
        if path.exists() and path not in seen:
            seen.add(path)
            yield path


def extract_facts(text: str, limit: int = 80) -> list[str]:
    facts: list[str] = []
    seen: set[str] = set()
    for pattern in PATTERNS:
        for match in re.finditer(pattern, text, flags=re.I):
            groups = [g.strip(" -:;") for g in match.groups() if g]
            fact = "Boss " + " ".join(groups) if not groups[0].lower().startswith("boss") else " ".join(groups)
            fact = re.sub(r"\s+", " ", fact).strip()
            if 12 <= len(fact) <= 240 and fact.lower() not in seen:
                seen.add(fact.lower())
                facts.append(fact)
            if len(facts) >= limit:
                return facts
    return facts


def main() -> int:
    config = load_config()
    root = Path(config.workspace_root)
    text_parts = []
    for path in iter_memory_files(root):
        try:
            text_parts.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    facts = extract_facts("\n".join(text_parts), limit=80)
    tools = HonchoTools(config)
    if not facts:
        print("No Boss profile facts extracted.")
        return 0
    result = tools.honcho_profile(peer_id="boss", facts=facts, merge=True)
    print({"ok": result.get("ok"), "facts_extracted": len(facts), "peer_id": "boss"})
    for fact in facts[:20]:
        print("-", fact)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
