# Brain From Cero

**A self-hosted platform for customizing and serving private language models.**
Deploy it on your own servers, specialize a model two ways — **Knowledge (RAG)**
or **Fine-tuning (LoRA)** — and consume each as an OpenAI-compatible API. Your
data never leaves your infrastructure.

---

## What you're looking at

This is the consolidated documentation for the whole product. It is organized
into four audiences — pick the one that matches what you're trying to do:

<div class="grid cards" markdown>

-   :material-account-tie: **User Guide**

    ---

    For the **operator** running the appliance. How to use the browser console
    to create projects, give a model knowledge or change its behavior, and hand
    an application an API key.

    [:octicons-arrow-right-24: User Guide](user-guide/index.md)

-   :material-code-braces: **Developer Guide**

    ---

    For an **engineer working on the codebase**. The architecture, a
    from-first-principles **"Learning the system"** deep-dive for developers new
    to ML infrastructure, the contract-driven workflow, and the code reference.

    [:octicons-arrow-right-24: Developer Guide](developer-guide/index.md)

-   :material-book-open-variant: **Reference**

    ---

    The locked facts: product scope, the live **API reference** (generated from
    the OpenAPI spec), the operations runbook, and the architecture-decision
    record.

    [:octicons-arrow-right-24: Reference](reference/PRODUCT_DEFINITION.md)

-   :material-map: **Roadmap**

    ---

    The single source of **open work** — priorities, acceptance criteria, and
    status. Everything that isn't done yet lives here.

    [:octicons-arrow-right-24: Roadmap](roadmap.md)

</div>

---

## The product in one paragraph

A company runs Brain From Cero on its own server (Docker Compose). Inside that
deployment, teams create **Projects**. Each project is one of two types and ends
in a private **model endpoint** consumed with a scoped API key:

- **Knowledge (RAG)** — upload documents → they're embedded into a per-project
  vector store → the model answers **grounded in your documents, with
  citations**. CPU-only; the model's weights never change.
- **Fine-tuning (LoRA)** — provide an instruction dataset (or synthesize one
  from your documents) → a GPU worker trains a LoRA adapter → it must pass an
  **evaluation gate** before it can serve → the endpoint serves base model +
  adapter.

The OpenAI-compatible `POST /v1/chat/completions` is the **only** protocol a
customer's applications call. A bundled operator console drives setup in a
browser.

!!! tip "New to RAG, embeddings, LoRA, or GGUF?"
    The Developer Guide's [Learning the system](developer-guide/learning-the-system.md)
    page explains every one of these from the perspective of a backend developer
    coming from standard languages and infrastructure — using analogies to
    things you already know (databases, caches, job queues, CI gates).

---

## How this documentation stays correct

Docs rot. This system is built so the parts that drift hardest can't:

| Part | How it's kept in sync |
|---|---|
| **API reference** | Rendered directly from `specs/openapi.yaml` — the same contract the server is tested against. Change the API → the docs change. |
| **Code reference** | Auto-extracted from the source docstrings (mkdocstrings). The reference *is* the code. |
| **Internal links / nav** | `mkdocs build --strict` runs in CI; a page that points at a moved or deleted doc **fails the build**. |
| **Roadmap** | A single source ([TODO.md](roadmap.md) at the repo root) included here, never duplicated. |
| **Scope vs. tasks** | Reference docs describe *what is*; the Roadmap is the *only* place with open work. The two are never mixed. |

See the Developer Guide's [Workflow](developer-guide/workflow.md) page for the
contract-driven discipline (Extended SDD) that the same rule extends to code.
