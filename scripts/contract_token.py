"""Print a bearer token for `make test-contracts`.

Registers a throwaway org + admin (so the fuzzer can never change the password
of, or delete the projects of, a real or seeded user) and logs in. Stdlib only.

Usage: python scripts/contract_token.py [BASE_URL]   (default http://localhost:8000/v1)
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"contract_token: {url} -> HTTP {exc.code}: {exc.read().decode()[:200]}")
    except urllib.error.URLError as exc:
        sys.exit(f"contract_token: cannot reach {url}: {exc.reason}")


def main() -> None:
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/v1").rstrip("/")
    tag = uuid.uuid4().hex[:12]
    creds = {"email": f"contract-gate-{tag}@example.com", "password": uuid.uuid4().hex}
    _post(f"{base}/auth/register", {"org_name": f"contract-gate-{tag}", **creds})
    print(_post(f"{base}/auth/login", creds)["access_token"])


if __name__ == "__main__":
    main()
