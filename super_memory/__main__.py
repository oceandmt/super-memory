#!/usr/bin/env python3
"""Super Memory CLI entry point for `python -m super_memory`."""

from __future__ import annotations

import sys


def main() -> None:
    """CLI entry point: run auto_deep by default."""
    args = sys.argv[1:]

    if args and args[0] == "auto-deep":
        from .auto_deep import run_deep_engine
        import logging

        logging.basicConfig(level=logging.INFO, format="%(message)s")
        result = run_deep_engine()
        print(f"\n{result.full_report()}")
    elif args and args[0] == "version":
        from . import __version__
        print(f"super-memory {__version__}")
    else:
        print(__doc__)
        print("\nUsage: python -m super_memory [auto-deep|version]")


if __name__ == "__main__":
    main()
