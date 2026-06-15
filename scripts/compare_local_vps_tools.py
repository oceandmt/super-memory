#!/usr/bin/env python3
"""Compare local super-memory MCP tools against VPS production.

Environment:
  VPS_HOST defaults to <VPS_USER>@<VPS_HOST>
  VPS_PORT defaults to <VPS_PORT>
  REMOTE_ROOT defaults to ${REMOTE_ROOT}

Exit code:
  0 = local/VPS match
  1 = mismatch or remote failure
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VPS_HOST = os.environ.get("VPS_HOST", "<VPS_USER>@<VPS_HOST>")
VPS_PORT = os.environ.get("VPS_PORT", "<VPS_PORT>")
REMOTE_ROOT = os.environ.get("REMOTE_ROOT", "${REMOTE_ROOT}")

LOCAL_CODE = "import json; import super_memory.mcp_server as m; m.MCP_PROFILE = 'admin'; print(json.dumps(sorted(t['name'] for t in m._tool_descriptors())))"

REMOTE_CODE = LOCAL_CODE


def local_tools() -> set[str]:
    res = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-c", LOCAL_CODE],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stdout + res.stderr)
    return set(json.loads(res.stdout))


def remote_tools() -> set[str]:
    cmd = [
        "ssh",
        "-p",
        VPS_PORT,
        VPS_HOST,
        f"cd '{REMOTE_ROOT}' && {REMOTE_ROOT}/.venv/bin/python3 -c {REMOTE_CODE!r}",
    ]
    res = subprocess.run(cmd, text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(res.stdout + res.stderr)
    return set(json.loads(res.stdout))


def main() -> int:
    try:
        local = local_tools()
        remote = remote_tools()
    except Exception as exc:
        print(f"TOOL_DIFF_ERROR: {exc}", file=sys.stderr)
        return 1

    only_local = sorted(local - remote)
    only_remote = sorted(remote - local)
    print(f"LOCAL_TOOLS={len(local)}")
    print(f"VPS_TOOLS={len(remote)}")

    if not only_local and not only_remote:
        print("TOOL_DIFF_OK")
        return 0

    print("TOOL_DIFF_MISMATCH")
    if only_local:
        print("ONLY_LOCAL:")
        for name in only_local:
            print(f"  - {name}")
    if only_remote:
        print("ONLY_VPS:")
        for name in only_remote:
            print(f"  - {name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
