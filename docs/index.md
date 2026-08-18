# Adapta

**A self-hosted platform for customizing and serving private language models.**
Upload documents or train a fine-tuned adapter on your own GPU — then expose
the result as an OpenAI-compatible API. Your data never leaves your servers.

!!! warning "Prototype maturity"
    This is a one-person project at prototype stage. The pieces are wired up — RAG, LoRA training, eval gate, multi-tenant serving, vision fine-tunes — but the system has not been independently audited or validated at real team scale. If you are deploying with sensitive data, review the auth, error-handling, and eval-gate code paths yourself before going to production. See [Brand §0](reference/BRAND.md#0-project-status) for the full disclosure.

This documentation serves two purposes: it is the operational and developer
reference for the platform, and it is a concrete learning resource for anyone
building or studying AI infrastructure on a real, production-grade codebase.

---

## Where to start

<div class="grid cards" markdown>

-   :material-brain: **AI Infrastructure Guide**

    ---

    Not sure what GGUF, LoRA, embeddings, or a vector store are? Start here.
    This section explains the full technology stack — every component, why it
    was chosen, and how it fits — written for engineers who know web development
    but are new to AI infrastructure.

    [:octicons-arrow-right-24: AI Infrastructure Guide](concepts/index.md)

-   :material-account-tie: **User Guide**

    ---

    For the operator running the platform. How to create projects, give a model
    knowledge from your documents, change how it behaves through fine-tuning,
    and hand an application a scoped API key.

    [:octicons-arrow-right-24: User Guide](user-guide/index.md)

-   :material-code-braces: **Developer Guide**

    ---

    For engineers working on the codebase. Architecture, the contract-driven
    workflow, the three CI gates, and the auto-generated code reference.
    Read [Learning the system](developer-guide/learning-the-system.md)
    before your first change.

    [:octicons-arrow-right-24: Developer Guide](developer-guide/index.md)

-   :material-book-open-variant: **Reference**

    ---

    The locked facts: product scope, the live API reference generated from
    the OpenAPI spec, the operations runbook, and the architecture-decision
    record.

    [:octicons-arrow-right-24: API Reference](reference/api.md)

</div>

---

## What the platform does

A company deploys Adapta on its own server with Docker Compose.
Inside that deployment, teams create **Projects**. Each project ends in a
private model **endpoint** consumed with a scoped API key:

**Knowledge (RAG)** — upload documents → they are parsed, chunked, and
embedded into a per-project vector store → each question is answered by
**hybrid retrieval** (semantic vector search + BM25 keyword search, fused and
re-scored by a cross-encoder reranker) → the model answers grounded in
your documents, with citations pointing at the source passages. The model's
weights never change. CPU-only.

**Fine-tuning (LoRA)** — provide an instruction dataset → a GPU worker trains
a LoRA adapter → the adapter must pass an evaluation gate before it can serve
→ the endpoint serves base model + adapter. On a vision base model, the dataset
is a zip bundle of image + instruction examples and the endpoint accepts images
— for invoice extraction, visual QC, document AI.

**Both together** — a fine-tune project can also index documents. Its endpoint
then injects retrieved context and applies the adapter in one call: facts from
retrieval with citations, tone and structure from the fine-tune.

The `POST /v1/chat/completions` endpoint is the only protocol customer
applications call. If your code already calls OpenAI, it already calls
Adapta.

!!! tip "New to RAG, LoRA, GGUF, or embeddings?"
    The [AI Infrastructure Guide](concepts/index.md) explains every concept in
    terms of engineering ideas you already know — databases, caches, job
    queues, and CI pipelines. No prior ML background required.

---

## Learning paths

| Your goal | Recommended path |
|---|---|
| Understand the AI infrastructure | [AI Infrastructure Guide](concepts/index.md) → [Stack & decisions](concepts/stack.md) → [Learning the system](developer-guide/learning-the-system.md) |
| Set up and use the platform | [User Guide](user-guide/index.md) → [Operator console](user-guide/operator-console.md) → [Consuming the API](user-guide/consuming-the-api.md) |
| Contribute to the codebase | [Developer Guide](developer-guide/index.md) → [Architecture](developer-guide/architecture.md) → [Workflow](developer-guide/workflow.md) |
| Understand a specific decision | [Stack & decisions](concepts/stack.md) — each component has an explicit "why not X?" section |
| Operate the platform in production | [Operations runbook](reference/OPERATIONS.md) |

---

## How this documentation stays correct

Docs rot. This system is built so the parts that drift hardest can't:

| Part | How it stays in sync |
|---|---|
| **API reference** | Rendered from `specs/openapi.yaml` — the same file the server is tested against. Change the API, the docs change. |
| **Code reference** | Auto-extracted from source docstrings (mkdocstrings). The reference *is* the code. |
| **Internal links** | `mkdocs build --strict` runs in CI. A broken internal link fails the build. |
| **Roadmap** | Canonical source at `TODO.md` in the repository — the roadmap page links to it directly rather than embedding it (the file links to source paths that only resolve in-repo). |
| **Scope vs. tasks** | Reference docs describe what *is*. The Roadmap is the only place with open work. The two are never mixed. |
