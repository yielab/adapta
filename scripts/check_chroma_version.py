#!/usr/bin/env python3
"""
Guard: the chromadb CLIENT pin (pyproject.toml) must equal the chroma SERVER image
tag (docker-compose.yml). A client/server API skew (e.g. 1.x client vs 0.6.x
server) silently breaks ALL collection creation with KeyError('_type') — it bit us
once already. This fails the fast CI gate if the two drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _client_version() -> str | None:
    text = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'chromadb==([0-9][0-9A-Za-z.\-]*)', text)
    return m.group(1) if m else None


def _server_version() -> str | None:
    text = (ROOT / "docker-compose.yml").read_text()
    m = re.search(r'chromadb/chroma:([0-9][0-9A-Za-z.\-]*)', text)
    return m.group(1) if m else None


def main() -> int:
    client, server = _client_version(), _server_version()
    if client is None:
        print("FAIL: could not find 'chromadb==<version>' in pyproject.toml")
        return 1
    if server is None:
        print("FAIL: could not find 'chromadb/chroma:<tag>' in docker-compose.yml")
        return 1
    if client != server:
        print(
            f"FAIL: chroma client/server version skew — pyproject chromadb=={client} "
            f"but docker-compose chromadb/chroma:{server}. Keep them equal (skew → "
            "KeyError('_type') on all indexing)."
        )
        return 1
    print(f"OK: chroma client and server both pinned to {client}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
