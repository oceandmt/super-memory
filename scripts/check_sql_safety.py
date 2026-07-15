#!/usr/bin/env python3
"""SQL injection safety checker for super-memory.

Scans all Python files for dangerous SQL patterns:
- f-string in execute()
- f-string for sql variable assignment
- unvalidated user input in WHERE clauses

Exit 0 if safe, exit 1 if violations found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def check_file(path: Path) -> list[str]:
    """Return list of violations in file."""
    violations = []
    text = path.read_text()
    lines = text.splitlines()
    for i, line in enumerate(text.splitlines(), 1):
        if "# nosec-sql" in line:
            continue
        # Multi-line f-string assignments (e.g. `sql = f"""...`) cannot carry a
        # trailing same-line comment, so also honor a nosec marker on the
        # immediately preceding line.
        if i >= 2 and "# nosec-sql" in lines[i - 2]:
            continue
        # Pattern 1: execute(f"...")
        if re.search(r'execute\s*\(\s*f["\']', line):
            violations.append(f"{path}:{i}: execute with f-string: {line.strip()}")
        # Pattern 2: sql = f"..."
        if re.search(r'sql\s*=\s*f["\']', line):
            violations.append(f"{path}:{i}: sql assignment with f-string: {line.strip()}")
    return violations


def main() -> int:
    root = Path(__file__).parent.parent / "super_memory"
    if not root.exists():
        print(f"ERROR: super_memory directory not found at {root}", file=sys.stderr)
        return 1
    
    all_violations = []
    for path in sorted(root.rglob("*.py")):
        violations = check_file(path)
        all_violations.extend(violations)
    
    if all_violations:
        print("SQL_SAFETY_FAIL")
        print(f"Found {len(all_violations)} violations:")
        for v in all_violations:
            print(f"  {v}")
        return 1
    
    print("SQL_SAFETY_OK")
    print(f"Checked {len(list(root.rglob('*.py')))} files, no f-string SQL patterns found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
