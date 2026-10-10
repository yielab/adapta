# Knowledge + behavior — using RAG and adapters together

The two services answer two different questions:

- **Knowledge (RAG)** changes **what the model can talk about** — it answers
  *from your documents*, with citations. No weights change.
- **An adapter (LoRA)** changes **how the model behaves** — its tone, its
  output structure, a narrow skill. It does **not** reliably add facts.

The strongest production pattern uses **both on one endpoint**: retrieval
supplies the facts, the adapter makes the answer come out in *your* voice and
*your* format. This page explains when to use which.

!!! note "Adapter import is not built yet"
    Adapta no longer trains adapters (removed 2026-10-10). You bring one, and
    importing it (with a CPU eval gate) is coming in E4.2–E4.4 — see the
    [roadmap](../roadmap.md). Until then only the knowledge half is usable end
    to end.

## When to use which — real-life cases

| Your situation | Use | Why |
|---|---|---|
| "Answer questions about our 400-page product manuals" | **Knowledge** | The facts live in documents; they change when the docs change — re-index, done. |
| "Our internal wiki updates weekly and answers must cite the source" | **Knowledge** | RAG citations point at the exact passage; updates are instant. |
| "Support replies must always follow our 5-part template and sound like us" | **Adapter** | A format/voice is a *behavior* — it lives in weights, not in any document. |
| "Classify incoming tickets into our 12 internal categories" | **Adapter** | A narrow skill with your private taxonomy; small local models learn it well from examples. |
| "Always answer in strict JSON our backend parses" | **Adapter** | Prompting drifts; an adapter makes the structure near-deterministic. |
| "A support assistant that answers **from our manuals**, **in our voice and template**" | **Both** | Facts from retrieval (cited), form from the adapter. |

!!! warning "What an adapter is *not* for"
    Don't use an adapter to teach the model facts ("memorize our price list").
    Facts belong in documents the model retrieves — they stay current and come
    back cited. An adapter that tries to memorize facts is brittle and goes
    stale on the first product change. Rule of thumb: **facts → Knowledge,
    form → Adapter.**

## How the combination works

A project of type **finetune** can *also* index documents (console: the
**Documents** step of the finetune flow; API: the same
`POST /v1/projects/{id}/files` used by RAG projects). At serve time the
endpoint composes whatever the project has:

- documents indexed → relevant passages are retrieved and injected, and the
  response carries `citations`;
- an imported adapter that passed the eval gate → it is applied on top of the base model.

A finetune project with indexed documents gets **both in the same call**.
(A pure-RAG project and a documents-free finetune project behave exactly as
before.) Bonus: those same indexed documents are what
`POST …/datasets/synthesize` reads when you bootstrap a dataset from documents.

!!! info "How retrieval works — hybrid vector + BM25"
    Retrieval is hybrid by default. A dense vector search (sentence-transformers
    embeddings) first fetches a wide candidate pool — four times the number of
    chunks that will actually be used. A sparse keyword search (BM25) then
    re-scores that same pool, and the two rankings are merged via Reciprocal
    Rank Fusion (RRF). Finally a cross-encoder reranker re-scores the shortlist
    before the top-k are injected, and the `score` in each citation comes from
    that last stage.

    The result is more accurate than pure vector search on keyword-heavy queries
    (product codes, names, exact phrases) and more robust than pure BM25 on
    paraphrase-style questions. No configuration is needed — this is always on.

    To tune it, set these on the **`app`** container (retrieval runs there, not
    in the worker):

    | Variable | Default | Effect |
    |---|---|---|
    | `ADAPTA_RAG_TOP_K` | `5` | Chunks injected into the prompt |
    | `ADAPTA_RAG_HYBRID_FETCH_MULTIPLIER` | `4` | Candidate pool = `top_k × N`; raise it if BM25 should see more |
    | `ADAPTA_RAG_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Set to `""` to disable reranking (lower latency and RAM, slightly lower accuracy) |
    | `ADAPTA_RAG_TIMEOUT_SECONDS` | `10` | Whole retrieval path; exceeding it returns a typed `504` |

## Realistic expectations

- **Knowledge is live**: add or remove a manual and re-index — the very next
  answer reflects it. No retraining.
- **Behavior is a swap**: changing the template means a new adapter (trained
  elsewhere), imported and gated again.
- The adapter only ever changes *how* answers read. If an answer's *facts* are
  wrong, fix the documents or their chunking — not the eval set.
- Start with the default `qwen2.5-1.5b-instruct` base (Apache-2.0); move up to
  `qwen2.5-7b-instruct` if quality demands it
  (`GET /v1/models` lists the catalog names).
- Requests with images (vision base models) are non-streaming, up to 4 images
  per request, and skip document retrieval. See
  [Consuming the API](consuming-the-api.md#images-vision-endpoints).
