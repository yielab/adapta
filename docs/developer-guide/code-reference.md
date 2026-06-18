# Code reference

These pages are **generated from the source docstrings** at build time
(mkdocstrings + griffe, static analysis — no imports are executed). They can't
drift from the code, because they *are* the code. This is a curated tour of the
modules worth knowing; the full source is the ultimate reference.

!!! note
    If a symbol below has thin documentation, the fix is to improve its
    docstring in the source — not to edit this page. The page regenerates on the
    next build.

---

## Domain — errors & pure types

The dependency-free core. Every exception a service raises is one of these; the
boundary handler in `adapta/api/app.py` is the only place they're serialized.

::: adapta.domain.errors
    options:
      heading_level: 3
      show_root_heading: false
      members_order: source

---

## Configuration

All settings (DB/Redis URLs, JWT secret, directories, thresholds, the eval-gate
knobs) flow through one pydantic-settings object.

::: adapta.config
    options:
      heading_level: 3
      show_root_heading: false
      members: [Settings]

---

## Services — business logic

### Chat (the serving path)

The single real serving path: RAG retrieval + context fitting + inference +
usage metering. See the [request lifecycle](architecture.md#request-lifecycle-a-rag-chat-completion).

::: adapta.services.chat
    options:
      heading_level: 4
      show_root_heading: false

### RAG (retrieval)

::: adapta.services.rag
    options:
      heading_level: 4
      show_root_heading: false

### Embeddings

::: adapta.services.embeddings
    options:
      heading_level: 4
      show_root_heading: false

### Training (validation & enqueue)

::: adapta.services.training
    options:
      heading_level: 4
      show_root_heading: false

### Adapters (registry + eval gate)

::: adapta.services.adapters
    options:
      heading_level: 4
      show_root_heading: false

---

## Training core — the eval gate

The gate's score math and the dual (absolute-or-improvement) gate live here. See
[the eval gate explained](learning-the-system.md#the-eval-gate-ci-for-a-model).

::: adapta.training.models
    options:
      heading_level: 3
      show_root_heading: false

---

## Core — engine wrappers

### Inference engine

Wraps llama-cpp. The per-model lock, bounded executor, and streaming bridge live
here. **Do not rewrite the engine internals** — wrap and call.

::: adapta.core.inference
    options:
      heading_level: 4
      show_root_heading: false

### Model manager (cache + locks)

::: adapta.core.model_manager
    options:
      heading_level: 4
      show_root_heading: false
