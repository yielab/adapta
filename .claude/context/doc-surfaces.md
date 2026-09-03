# Doc-surface matrix — which docs a change must touch

Two kinds of doc, never mixed: **📖 Reference** describes what *is* (no tasks);
**🗺 Roadmap** (`TODO.md`) is the only place with open work.
Anything auto-generated (`docs/reference/api.md` from the spec,
`docs/developer-guide/code-reference.md` from docstrings) is **never hand-written** —
improve the spec or the docstring instead.

| Change | Surfaces that must stay true |
|---|---|
| New/changed endpoint | `specs/openapi.yaml` → (api.md auto) · `CLAUDE.md` "API surface" block · `docs/user-guide/consuming-the-api.md` |
| New capability (retrieval mode, training mode, modality) | `docs/reference/PRODUCT_DEFINITION.md` (scope) · `docs/developer-guide/architecture.md` · `docs/developer-guide/learning-the-system.md` (the analogy pass) · `CLAUDE.md` "What this project is" · `README.md` if it changes the pitch |
| Service/module added or moved | `CLAUDE.md` "Key source files" · `.claude/context/repo-map.md` · `docs/developer-guide/architecture.md` |
| Ops/deploy/sizing change | `docs/reference/OPERATIONS.md` · `README.md` run instructions |
| Console UI change | `docs/user-guide/operator-console.md` (+ the relevant walkthrough) |
| Workflow/gate change | `docs/reference/SDD_WORKFLOW.md` · `CLAUDE.md` Workflow table · `.claude/context/gates.md` |
| Retrieval behaviour (hybrid, reranker, chunking, citations, OCR) | `README.md` "Give it knowledge" bullet · `docs/reference/PRODUCT_DEFINITION.md` Service A · `docs/user-guide/knowledge-and-behavior.md` retrieval box · `docs/concepts/stack.md` hybrid section · `docs/reference/COMPETITIVE_LANDSCAPE.md` retrieval note |
| Model catalog (entries, defaults, licenses, VRAM) | `docs/reference/OPERATIONS.md` sizing + "adding a base model" · `docs/user-guide/operator-console.md` Models page · `docs/user-guide/fine-tuning-use-cases.md` if the validated base changed · `README.md` quick start if the default changed |
| Training/eval semantics (prompt render, masking, metrics, gate rule) | `docs/reference/PRODUCT_DEFINITION.md` eval-gate paragraph · `docs/developer-guide/learning-the-system.md` gate section · `docs/user-guide/fine-tuning-use-cases.md` (re-measured numbers only) · `CLAUDE.md` one-liner on the gate if the rule changed |
| Anything shipped | `TODO.md`: tick the task + one **Done.** paragraph + refresh the **Status snapshot** date/row |

Rules: never add open tasks to a reference doc; never let `TODO.md` re-describe
architecture (link to the reference). Every internal link must resolve —
`make docs-build` is `--strict` and runs in the CI fast gate.
