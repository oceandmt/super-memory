"""Persistent personal entity registry for Super Memory MemPalace.

Knows the difference between Riley (a person) and ever (an adverb).
Built from three sources, in priority order:
  1. Onboarding — what the user explicitly told us
  2. Learned — what we inferred from session history with high confidence
  3. Detected — regex pattern matches with context disambiguation

Usage:
    from super_memory.mempalace.entity_registry import EntityRegistry
    registry = EntityRegistry.load()
    result = registry.lookup("Max", context="I went with Max today")
    # → {"type": "person", "confidence": 1.0, "source": "onboarding"}

Deterministic. No LLM. No network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# ── Common English words that could be confused with names ──────────────────
COMMON_ENGLISH_WORDS: set[str] = {
    "ever", "grace", "will", "bill", "mark", "april", "may", "june",
    "joy", "hope", "faith", "chance", "chase", "hunter", "dash", "flash",
    "star", "rose", "lily", "daisy", "river", "lake", "amber", "jade",
    "ruby", "opal", "pearl", "storm", "sky", "rain", "snow", "frost",
    "cliff", "rock", "stone", "reed", "thorn", "wolf", "fox", "bear",
    "kit", "pat", "frank", "ray", "dean", "grant", "lance", "miles",
    "pierce", "wade", "art", "bud", "chip", "clay", "dale", "drew",
    "grant", "lance", "lane", "miles", "page", "payne", "randy",
    "art", "bill", "bob", "chip", "chuck", "dan", "don", "doug",
    "ed", "fred", "gene", "hank", "jack", "jim", "joe", "ken",
    "larry", "mike", "nick", "pat", "ray", "rick", "rob", "ron",
    "sam", "stan", "ted", "tim", "tom", "vic", "will",
    # Vietnamese common words
    "yêu", "thương", "nhớ", "mong", "chờ", "đợi", "nắng", "mưa",
    "gió", "mây", "sông", "núi", "biển", "hoa", "lá", "chim",
}
COMMON_ENGLISH_WORDS_LOWER = {w.lower() for w in COMMON_ENGLISH_WORDS}

# ── Context disambiguation patterns ─────────────────────────────────────────
# If a word appears in one of these contexts, it's PERSON
EXPLICIT_MENTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:talked|spoke|met|chatted|worked|paired)\s+with\s+(\w+)", re.IGNORECASE),
    re.compile(r"(?:my|our)\s+(?:friend|partner|colleague|brother|sister|dad|mom|son|daughter|boss|teammate)\s+(\w+)", re.IGNORECASE),
    re.compile(r"(\w+)\s+(?:is|was|has been)\s+(?:my|our)\s+(?:friend|partner|colleague|boss)", re.IGNORECASE),
    re.compile(r"(\w+)\s+(?:said|told|mentioned|wrote|asked|replied|noted|reported|suggested)", re.IGNORECASE),
    re.compile(r"(?:go|went|going)\s+(?:to|with)\s+(\w+)(?:'s)?\s+(?:place|house|office)", re.IGNORECASE),
    re.compile(r"@(\w[\w.-]*)", re.IGNORECASE),  # Mentions
]

# ── Collocation boost: names often appear with these verbs ──────────────────
PERSON_VERBS: set[str] = {
    "said", "told", "asked", "replied", "wrote", "mentioned", "noted",
    "called", "emailed", "texted", "messaged", "reported", "suggested",
    "recommended", "decided", "agreed", "disagreed", "explained",
    "laugh", "laughed", "smiled", "nodded", "sighed",
}


class EntityRegistry:
    """Persistent entity registry backed by JSON.

    Priority order for lookups:
      1. Onboarding (user-confirmed) — confidence 1.0
      2. Learned (high-confidence session inference) — confidence 0.7+
      3. Detected (regex + context) — confidence varies

    Saves to workspace_root/data/entity_registry.json.
    """

    def __init__(self, registry_path: Path | str):
        self.registry_path = Path(registry_path)
        self._entities: dict[str, dict[str, Any]] = {}
        self._aliases: dict[str, str] = {}  # alias → canonical name

    @classmethod
    def load(cls, workspace_root: str = "", registry_path: str = "") -> EntityRegistry:
        """Load registry from file, or create empty."""
        if registry_path:
            path = Path(registry_path)
        else:
            ws = Path(workspace_root) if workspace_root else Path(__file__).parent.parent.parent / "data"
            ws.mkdir(parents=True, exist_ok=True)
            path = ws / "entity_registry.json"
        
        reg = cls(path)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                reg._entities = data.get("entities", {})
                reg._aliases = data.get("aliases", {})
            except (json.JSONDecodeError, KeyError):
                pass
        return reg

    def save(self) -> None:
        """Persist registry to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(
            {"entities": self._entities, "aliases": self._aliases},
            indent=2, ensure_ascii=False,
        ))

    # ── CRUD ────────────────────────────────────────────────────────────────

    def add(
        self,
        name: str,
        kind: str = "person",
        source: str = "onboarding",
        confidence: float = 1.0,
        aliases: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add or update an entity."""
        canonical = name.strip()
        entry = {
            "name": canonical,
            "kind": kind,
            "source": source,
            "confidence": confidence,
            "aliases": aliases or [],
            "metadata": metadata or {},
            "added_at": _now_iso(),
        }
        self._entities[canonical.lower()] = entry
        for alias in aliases or []:
            self._aliases[alias.lower()] = canonical.lower()

    def remove(self, name: str) -> bool:
        """Remove entity. Returns True if existed."""
        key = name.strip().lower()
        if key in self._entities:
            del self._entities[key]
            # Clean aliases
            gone = [a for a, c in self._aliases.items() if c == key]
            for a in gone:
                del self._aliases[a]
            self.save()
            return True
        return False

    def get(self, name: str) -> dict[str, Any] | None:
        """Get entity by canonical name or alias."""
        key = name.strip().lower()
        if key in self._aliases:
            key = self._aliases[key]
        return self._entities.get(key)

    # ── Disambiguation ──────────────────────────────────────────────────────

    def lookup(self, word: str, context: str = "") -> dict[str, Any]:
        """Look up a word. Disambiguates person vs common word.

        Returns:
            {"type": "person"|"concept"|"project"|..., 
             "confidence": 0.0-1.0, 
             "source": "onboarding"|"learned"|"detected",
             "canonical": "..."}
        """
        word_stripped = word.strip()
        key = word_stripped.lower()

        # 1. Check if registered
        entity = self.get(key)
        if entity:
            return {
                "type": entity["kind"],
                "confidence": entity["confidence"],
                "source": entity["source"],
                "canonical": entity["name"],
                "aliases": entity.get("aliases", []),
            }

        # 2. Disambiguate
        return self._disambiguate(word_stripped, context)

    def _disambiguate(self, word: str, context: str) -> dict[str, Any]:
        """Heuristic disambiguation without LLM."""
        w_lower = word.lower()

        # Common word override
        if w_lower in COMMON_ENGLISH_WORDS_LOWER:
            # Check if context suggests person use
            if context:
                person_score = self._person_context_score(word, context)
                if person_score > 0.5:
                    return {
                        "type": "person", "confidence": min(0.7, person_score),
                        "source": "detected", "canonical": word,
                    }
            return {
                "type": "common_word", "confidence": 0.9,
                "source": "dictionary", "canonical": word,
            }

        # Capitalized = likely proper noun
        if word[0].isupper() and word.isalpha():
            return {
                "type": "person", "confidence": 0.5,
                "source": "detected", "canonical": word,
                "note": "capitalized — assumed proper noun",
            }

        # Unknown lowercase
        return {"type": "unknown", "confidence": 0.3, "source": "detected", "canonical": word}

    def _person_context_score(self, word: str, context: str) -> float:
        """Score likelihood that word is a person based on context."""
        score = 0.0
        for pattern in EXPLICIT_MENTION_PATTERNS:
            for match in pattern.finditer(context):
                if match.group(1).lower() == word.lower():
                    return 0.9  # Strong signal
        
        # Check for person verbs nearby
        words = context.lower().split()
        word_idx = -1
        for i, w in enumerate(words):
            if w == word.lower():
                word_idx = i
                break
        if word_idx >= 0:
            # Check 2 words before/after for person verbs
            window = words[max(0, word_idx-2):word_idx+3]
            if any(v in window for v in PERSON_VERBS):
                score += 0.3

        return min(0.8, score)

    # ── Bulk operations ─────────────────────────────────────────────────────

    def list_all(self, kind: str | None = None) -> list[dict[str, Any]]:
        """List all entities, optionally filtered by kind."""
        entities = list(self._entities.values())
        if kind:
            entities = [e for e in entities if e["kind"] == kind]
        return sorted(entities, key=lambda e: e["name"])

    def stats(self) -> dict[str, Any]:
        """Registry statistics."""
        kinds: dict[str, int] = {}
        sources: dict[str, int] = {}
        for e in self._entities.values():
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
            sources[e["source"]] = sources.get(e["source"], 0) + 1
        return {
            "total_entities": len(self._entities),
            "total_aliases": len(self._aliases),
            "by_kind": kinds,
            "by_source": sources,
        }

    def detect_and_learn(self, text: str, min_confidence: float = 0.6) -> list[dict[str, Any]]:
        """Scan text for potential new entities and auto-learn high-confidence ones.

        Returns list of detected entities (only those above min_confidence are auto-added).
        """
        from .extractor import SpatialExtractor
        extractor = SpatialExtractor()
        entities = extractor.extract_entities(text)
        
        learned: list[dict[str, Any]] = []
        for entity in entities:
            result = self._disambiguate(entity.name, text)
            if result["type"] == "person" and result["confidence"] >= min_confidence:
                if entity.name.lower() not in self._entities and entity.name.lower() not in self._aliases:
                    self.add(
                        name=entity.name,
                        kind="person",
                        source="learned",
                        confidence=result["confidence"],
                        metadata={"detected_in": text[:100]},
                    )
                    learned.append({"name": entity.name, "confidence": result["confidence"]})
        
        if learned:
            self.save()
        return learned


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── Command-line ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    reg = EntityRegistry.load()
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "list":
            for e in reg.list_all():
                print(f"  {e['kind']:12s} {e['name']:20s} conf={e['confidence']:.1f} src={e['source']}")
        elif cmd == "stats":
            print(json.dumps(reg.stats(), indent=2))
        elif cmd == "lookup" and len(sys.argv) > 2:
            result = reg.lookup(sys.argv[2], context=" ".join(sys.argv[3:]))
            print(json.dumps(result, indent=2))
        elif cmd == "add" and len(sys.argv) >= 4:
            reg.add(name=sys.argv[2], kind=sys.argv[3])
            reg.save()
            print(f"✓ Added: {sys.argv[2]} ({sys.argv[3]})")
    else:
        print(json.dumps(reg.stats(), indent=2))
