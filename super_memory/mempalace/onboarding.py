"""Onboarding — first-run setup that teaches MemPalace about the user's world.

Seeds the entity_registry with confirmed data so MemPalace knows
who the people are and what the projects are before a single drawer is stored.

Designed for both interactive (CLI) and programmatic use.
Companion to: entity_registry.py, entity_detector.py

Usage:
    python3 -m super_memory.mempalace.onboarding
    # or programmatically:
    from super_memory.mempalace.onboarding import quick_setup
    registry = quick_setup(mode="combo", people=[...], projects=[...])
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# ── Default wing taxonomies by mode ─────────────────────────────────────────

DEFAULT_WINGS: dict[str, list[str]] = {
    "work": ["projects", "clients", "team", "decisions", "research"],
    "personal": ["family", "health", "creative", "reflections", "relationships"],
    "combo": ["family", "work", "health", "creative", "projects", "reflections"],
}

# ── Interactive prompts ─────────────────────────────────────────────────────


def _hr():
    print(f"\n{'─' * 58}")


def _header(text: str):
    print(f"\n{'=' * 58}")
    print(f"  {text}")
    print(f"{'=' * 58}")


def _ask(prompt: str, default: str | None = None) -> str:
    if default:
        return input(f"  {prompt} [{default}]: ").strip() or default
    return input(f"  {prompt}: ").strip()


def _yn(prompt: str, default: str = "y") -> bool:
    val = input(f"  {prompt} [{'Y/n' if default == 'y' else 'y/N'}]: ").strip().lower()
    if not val:
        return default == "y"
    return val.startswith("y")


# ── Step 1: Mode ────────────────────────────────────────────────────────────


def _ask_mode() -> str:
    _header("Welcome to Super Memory")
    print("""
  Super Memory needs to know a little about your world — who the people
  are, what the projects are, and how you want memory organized.

  This takes about 2 minutes. You can always update later.
""")
    print("  How are you using Super Memory?")
    print("    [1]  Work     — projects, clients, colleagues, decisions")
    print("    [2]  Personal — diary, family, health, relationships")
    print("    [3]  Both     — personal and professional mixed\n")

    while True:
        choice = input("  Your choice [1/2/3]: ").strip()
        if choice == "1":
            return "work"
        elif choice == "2":
            return "personal"
        elif choice == "3":
            return "combo"
        print("  Please enter 1, 2, or 3.")


# ── Step 2: People ──────────────────────────────────────────────────────────


def _ask_people(mode: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    people: list[dict[str, str]] = []
    aliases: dict[str, str] = {}

    if mode in ("personal", "combo"):
        _hr()
        print("""
  Personal world — who are the important people in your life?

  Format: name, relationship (e.g. "Riley, daughter" or just "Devon")
  Type 'done' when finished.
""")
        while True:
            entry = input("  Person: ").strip()
            if entry.lower() in ("done", ""):
                break
            parts = [p.strip() for p in entry.split(",", 1)]
            name = parts[0]
            relationship = parts[1] if len(parts) > 1 else ""
            if name:
                nick = input(f"  Nickname for {name}? (enter to skip): ").strip()
                if nick:
                    aliases[nick] = name
                people.append({"name": name, "relationship": relationship, "context": "personal"})

    if mode in ("work", "combo"):
        _hr()
        print("""
  Work world — who are the colleagues, clients, collaborators?

  Format: name, role (e.g. "Ben, co-founder" or just "Sarah")
  Type 'done' when finished.
""")
        while True:
            entry = input("  Person: ").strip()
            if entry.lower() in ("done", ""):
                break
            parts = [p.strip() for p in entry.split(",", 1)]
            name = parts[0]
            role = parts[1] if len(parts) > 1 else ""
            if name:
                people.append({"name": name, "relationship": role, "context": "work"})

    return people, aliases


# ── Step 3: Projects ────────────────────────────────────────────────────────


def _ask_projects(mode: str) -> list[str]:
    if mode == "personal":
        return []

    _hr()
    print("""
  What are your main projects? (Helps distinguish project names from
  common words — e.g. "Lantern" the project vs. "lantern" the object.)

  Type 'done' when finished.
""")
    projects: list[str] = []
    while True:
        proj = input("  Project: ").strip()
        if proj.lower() in ("done", ""):
            break
        if proj:
            projects.append(proj)
    return projects


# ── Step 4: Wings ───────────────────────────────────────────────────────────


def _ask_wings(mode: str) -> list[str]:
    defaults = DEFAULT_WINGS.get(mode, DEFAULT_WINGS["combo"])
    _hr()
    print(f"""
  Wings are the top-level categories in your memory palace.

  Suggested for {mode} mode:
    {", ".join(defaults)}

  Press enter to keep these, or type your own comma-separated list.
""")
    custom = input("  Wings: ").strip()
    if custom:
        return [w.strip() for w in custom.split(",") if w.strip()]
    return defaults


# ── Quick setup (non-interactive, for programmatic use) ─────────────────────


def quick_setup(
    mode: str = "combo",
    people: list[dict[str, str]] | None = None,
    projects: list[str] | None = None,
    aliases: dict[str, str] | None = None,
    wings: list[str] | None = None,
    registry_path: str = "",
    save: bool = True,
) -> Any:
    """Programmatic setup without interactive prompts.

    Args:
        mode: "work", "personal", or "combo"
        people: List of {"name": str, "relationship": str, "context": str}
        projects: List of project name strings
        aliases: Dict of nickname → canonical_name
        wings: Wing name list (uses DEFAULT_WINGS if None)
        registry_path: Path for entity registry JSON
        save: Whether to persist registry

    Returns:
        Seeded EntityRegistry instance
    """
    from .entity_registry import EntityRegistry

    registry = EntityRegistry.load(registry_path=registry_path)

    for p in (people or []):
        kind = "person"
        if p.get("context") == "work":
            kind = "person"
        registry.add(
            name=p["name"],
            kind=kind,
            source="onboarding",
            confidence=1.0,
            metadata={"relationship": p.get("relationship", ""), "context": p.get("context", "")},
        )

    for proj in (projects or []):
        registry.add(name=proj, kind="project", source="onboarding")

    for nick, canonical in (aliases or {}).items():
        if canonical.lower() in registry._entities:
            if nick.lower() not in registry._aliases:
                registry._aliases[nick.lower()] = canonical.lower()

    if save:
        registry.save()

    return registry


# ── Run interactive onboarding ──────────────────────────────────────────────


def run_onboarding(registry_path: str = "") -> Any:
    """Run the full interactive onboarding flow.

    Returns the seeded EntityRegistry.
    """
    from .entity_registry import EntityRegistry

    mode = _ask_mode()
    people, aliases = _ask_people(mode)
    projects = _ask_projects(mode)
    wings = _ask_wings(mode)

    registry = quick_setup(
        mode=mode,
        people=people,
        projects=projects,
        aliases=aliases,
        wings=wings,
        registry_path=registry_path,
    )

    _header("Setup Complete")
    stats = registry.stats()
    print(f"\n  {stats['total_entities']} entities registered")
    if wings:
        print(f"  Wings: {', '.join(wings)}")
    print(f"  Registry: {registry.registry_path}")
    print(f"\n  Super Memory knows your world from the first session.")

    return registry


# ── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else ""
    run_onboarding(registry_path=path)
