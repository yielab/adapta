"""MkDocs build hook: vendor the OpenAPI spec into the docs tree.

``specs/openapi.yaml`` is the Pillar-1 single source of truth for the API. The
API reference page (``docs/reference/api.md``) renders it with the
render-swagger plugin, which reads from inside the docs directory. Rather than
duplicate the spec in git, we copy it in at build time so the rendered API docs
are always generated from the same file the server validates against.

The copied file (``docs/reference/openapi.yaml``) is gitignored.
"""

from __future__ import annotations

import shutil
from pathlib import Path

_SPEC_SRC = Path("specs/openapi.yaml")
_SPEC_DST = Path("docs/reference/openapi.yaml")


def on_pre_build(config, **kwargs) -> None:  # noqa: ANN001, ARG001 (mkdocs hook signature)
    """Copy the canonical OpenAPI spec into the docs tree before the build."""
    if not _SPEC_SRC.exists():
        raise FileNotFoundError(
            f"OpenAPI spec not found at {_SPEC_SRC} — the API reference page cannot render."
        )
    _SPEC_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_SPEC_SRC, _SPEC_DST)
