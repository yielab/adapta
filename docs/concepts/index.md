# AI Infrastructure Guide

Adapta is a conventional web service augmented with three AI-specific
systems. The web layer — FastAPI, PostgreSQL, Redis, Docker — follows patterns
any backend engineer will recognize. The AI layer — an inference engine, a
vector store, and a fine-tuning pipeline — follows the same engineering
principles but manages different resource constraints.

This section explains the full stack: what every component is, why it was
chosen over the alternatives, and how it fits into the whole. It is a
companion to the product itself, using it as a concrete, running example of
how AI infrastructure is built.

---

## Who this is for

<div class="grid cards" markdown>

-   **Web developers new to AI**

    ---

    You ship backend services and know databases, caches, and job queues.
    This guide connects your existing knowledge to the AI-specific pieces:
    inference engines, vector stores, and fine-tuning pipelines — each one
    explained in terms of its engineering equivalent.

    Start with [Stack & decisions](stack.md), then read
    [Learning the system](../developer-guide/learning-the-system.md)
    for the deeper conceptual tour.

-   **Technical leads and architects**

    ---

    You need decision rationale: why llama-cpp over vLLM, why ChromaDB
    over pgvector, why BLPOP over Celery, why Docker Compose over
    Kubernetes. The [Stack & decisions](stack.md) page covers each
    choice explicitly — including the alternatives considered.

-   **Product and DevOps roles**

    ---

    You work adjacent to engineering and need a clear model of what the
    system does, what hardware it needs, and how the parts relate. The
    table in [Stack & decisions](stack.md) gives you the map; this
    section doesn't require reading code.

-   **Developers contributing to the project**

    ---

    Read this section first, then [Architecture](../developer-guide/architecture.md)
    for the component diagram and request lifecycle, then
    [Workflow & contracts](../developer-guide/workflow.md) before your
    first change.

</div>

---

## The core idea

A traditional web service handles requests with business logic and a database.
An AI-serving platform adds three systems that traditional stacks don't have:

| New piece | Job | Familiar equivalent |
|---|---|---|
| **Inference engine** | Run a model function to generate text | Evaluating a compiled binary at runtime |
| **Vector store** | Retrieve documents by semantic similarity | A database index — but for meaning, not exact value |
| **Training pipeline** | Adjust model weights from labeled examples | A CI pipeline — but the artifact is a behavior change |

Everything else — HTTP routing, relational storage, async job queues, auth,
migrations — is standard web engineering. The AI pieces plug into the same
framework, not a different one.

!!! tip "Key insight for web developers"
    The hardest conceptual shift is not the machine learning — it's understanding
    that inference is **slow, stateful, and non-thread-safe** in a way that
    databases are not. The engineering response (a lock, a thread pool, a timeout,
    an LRU cache) is entirely familiar; the resource it wraps is new.

---

## How to use this section

1. **[Stack & decisions](stack.md)** — the map. Every component in the stack,
   its role, why it was chosen, and where it lives in the code. Read this for
   orientation and decision context.
2. **[Learning the system](../developer-guide/learning-the-system.md)** — the
   conceptual deep-dive. Language models, tokens, embeddings, RAG, LoRA,
   quantization, and the evaluation gate, each explained from first principles
   with engineering analogies. Read this to understand *how* the AI pieces work.
3. **[Architecture](../developer-guide/architecture.md)** — the assembly. How
   the components connect, the data model, and the full request lifecycle for
   both serving modes.

These pages are designed to be read in order by someone new to the stack.
They can also be used as standalone references once you have the full picture.
