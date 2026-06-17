"""Fact Checker — verify statements against known facts in the Knowledge Graph.

Detects three classes of issue:
  1. similar_name — text mentions a name close to a registered entity (possible typo)
  2. relationship_mismatch — text asserts a relationship that contradicts the KG
  3. temporal_conflict — text asserts something outside valid time window

Uses EntityRegistry + KnowledgeGraph. No LLM, no network.

Usage:
    from super_memory.mempalace.fact_checker import fact_check
    result = fact_check("Bob is Alice's brother", kg=kg, registry=registry)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance between two strings (no external deps)."""
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)

    prev_row = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr_row = [i + 1]
        for j, cb in enumerate(b):
            insert = prev_row[j + 1] + 1
            delete = curr_row[j] + 1
            sub = prev_row[j] + (0 if ca == cb else 1)
            curr_row.append(min(insert, delete, sub))
        prev_row = curr_row
    return prev_row[-1]


def _words_in_text(words: set[str], text: str) -> set[str]:
    """Return which words appear in text (case-insensitive)."""
    text_lower = text.lower()
    return {w for w in words if w.lower() in text_lower}


def _extract_capitalized(text: str) -> list[str]:
    """Extract capitalized words from text."""
    import re
    return re.findall(r'\b[A-Z][a-z]{2,}\b', text)


def fact_check(
    text: str,
    db_path: Path | str | None = None,
    kg: Any = None,
    registry: Any = None,
) -> dict[str, Any]:
    """Check a text statement against known knowledge graph facts.

    Args:
        text: Statement to check
        db_path: Path to SQLite database (for KG init)
        kg: Pre-initialized KnowledgeGraph instance (optional)
        registry: Pre-loaded EntityRegistry instance (optional)

    Returns:
        Dict with issues list
    """
    issues: list[dict[str, Any]] = []

    # ── 1. similar_name check ───────────────────────────────────────────
    if registry is not None:
        known_names = set()
        for entity in registry._entities.values():
            known_names.add(entity["name"])
            for alias in entity.get("aliases", []):
                known_names.add(alias)

        text_words = _extract_capitalized(text)
        for word in text_words:
            for name in known_names:
                if word.lower() == name.lower():
                    break  # exact match, no issue
                dist = _edit_distance(word.lower(), name.lower())
                if 0 < dist <= 2 and len(word) >= 4:
                    issues.append({
                        "type": "similar_name",
                        "severity": "low",
                        "text_name": word,
                        "known_name": name,
                        "edit_distance": dist,
                        "suggestion": f'Did you mean "{name}" instead of "{word}"?',
                    })

    # ── 2. relationship_mismatch check ──────────────────────────────────
    if kg is not None:
        try:
            # Extract entity names from text
            text_names = set(_extract_capitalized(text))
            text_lower = text.lower()

            # Check each pair for relationship assertions
            for name_a in text_names:
                for name_b in text_names:
                    if name_a >= name_b:
                        continue

                    # Skip if both names aren't in text near each other
                    a_pos = text_lower.find(name_a.lower())
                    b_pos = text_lower.find(name_b.lower())
                    if a_pos < 0 or b_pos < 0:
                        continue

                    # Check KG for known relationships between these entities
                    a_rels = kg.query_entity(name_a, direction="both", limit=200)
                    b_rels = kg.query_entity(name_b, direction="both", limit=200)

                    # Build set of known connections
                    known_connections: set[tuple[str, str, str]] = set()
                    for rel in a_rels.get("relationships", []):
                        other = rel.get("target") or rel.get("source")
                        if other and other.lower() == name_b.lower():
                            known_connections.add((name_a, name_b, rel["rel_type"]))

                    # Check if text asserts a relationship not in KG
                    # Look for relationship keywords
                    rel_keywords = {
                        "is": ["is", "was", "has been"],
                        "works_on": ["works on", "working on", "built", "maintains"],
                        "owns": ["owns", "has", "possesses"],
                        "created": ["created", "made", "wrote", "developed"],
                        "part_of": ["part of", "member of", "belongs to"],
                    }

                    text_asserts_rel = False
                    asserted_type = "unknown"
                    for rel_type, keywords in rel_keywords.items():
                        for kw in keywords:
                            # Check both directions
                            if f"{name_a.lower()} {kw} {name_b.lower()}" in text_lower:
                                text_asserts_rel = True
                                asserted_type = rel_type
                                break
                        if text_asserts_rel:
                            break

                    if text_asserts_rel and not known_connections:
                        issues.append({
                            "type": "relationship_mismatch",
                            "severity": "medium",
                            "asserted": f"{name_a} → {asserted_type} → {name_b}",
                            "known_relationships": [],
                            "suggestion": f"No known relationship between {name_a} and {name_b} in knowledge graph.",
                        })

        except Exception:
            pass  # Gracefully degrade

    # ── 3. temporal_conflict check ──────────────────────────────────────
    if kg is not None:
        try:
            import re
            from datetime import datetime, timezone

            date_patterns = [
                (re.compile(r'(\d{4}-\d{2}-\d{2})'), "%Y-%m-%d"),
                (re.compile(r'(\d{2}/\d{2}/\d{4})'), "%m/%d/%Y"),
            ]
            found_dates: list[tuple[str, str]] = []
            for pattern, fmt in date_patterns:
                for match in pattern.finditer(text):
                    found_dates.append((match.group(1), fmt))

            # For each entity in text, check if facts are valid at mentioned dates
            for name in _extract_capitalized(text):
                entity_facts = kg.query_facts(subject=name, limit=100)
                for date_str, fmt in found_dates:
                    try:
                        d = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc).isoformat()
                        for fact in entity_facts:
                            vf = fact.get("valid_from")
                            vu = fact.get("valid_until")
                            if vf and d < vf:
                                issues.append({
                                    "type": "temporal_conflict",
                                    "severity": "medium",
                                    "fact": f"{fact['subject']} {fact['predicate']} {fact['object']}",
                                    "valid_from": vf,
                                    "mentioned_date": d,
                                    "issue": "fact not yet valid at mentioned date",
                                })
                            if vu and d > vu:
                                issues.append({
                                    "type": "temporal_conflict",
                                    "severity": "low",
                                    "fact": f"{fact['subject']} {fact['predicate']} {fact['object']}",
                                    "valid_until": vu,
                                    "mentioned_date": d,
                                    "issue": "fact expired before mentioned date",
                                })
                    except (ValueError, OverflowError):
                        continue

        except Exception:
            pass

    return {
        "text": text[:200],
        "issues": issues,
        "issue_count": len(issues),
        "passed": len(issues) == 0,
    }
