# 🗺 Roadmap — Adapta

> **This file is the ROADMAP: the single source of open work.** If a task isn't here, it isn't planned.
> Shipped work does not stay here: a closed block moves to [CHANGELOG.md](CHANGELOG.md) in the commit that
> closes it. Reference docs describe what *is* and never carry tasks:
> [PRODUCT_DEFINITION.md](docs/reference/PRODUCT_DEFINITION.md) (what we build) ·
> [SDD_WORKFLOW.md](docs/reference/SDD_WORKFLOW.md) (how we work: three contracts) ·
> [OPERATIONS.md](docs/reference/OPERATIONS.md) (run it) · [README.md](README.md) · [CLAUDE.md](CLAUDE.md)
> (agent working agreement) · the MkDocs site under `docs/`.
>
> **Legend:** `[ ]` open · board status `open` / `in progress` / `ready-for-live` / `done`.
> **Priority:** **P0** blocks a trustworthy `main` · **P1** needed before first customer · **P2** nice-to-have.

---

## How to pick up a task

Every open task is written so a developer or AI agent can execute it without prior context. Each carries:

- **Context** — why it exists / what's wrong today.
- **Scope** — the boundary (what is and isn't included).
- **Steps** — the concrete sequence of changes.
- **Files** — where the work lands.
- **Contract impact** — which SDD pillar(s) fire ([SDD_WORKFLOW.md](docs/reference/SDD_WORKFLOW.md)); change the contract **first**.
- **Gate** — the one `make` target (or opt-in integration suite) that proves it; escalate only if that gate cannot see the change.
- **Acceptance** — the observable, testable condition that closes it.
- **Close** — the doc surfaces to update, then the closure note.

**Read budget (agents):** locate the block with `grep -n '^### <id>' TODO.md`, read only that block
(`sed -n`), then only the files its **Files** line names. Do not read a whole section or this file end to
end to pick up one task. **Close** by writing **Done.** (≤ 8 lines: what changed · gate run + result · anything
skipped) and **Handoff.** under the block, then **moving the whole block to [CHANGELOG.md](CHANGELOG.md)**
(top dated section) and flipping its board row to `done YYYY-MM-DD` — then stop; out-of-scope findings become
a `Follow-up.` line (which stays here, under the board), never extra diff.

Honour the [Definition of done](#definition-of-done-per-task) on every task. Work inside the dev container
(`docker compose up -d` → `docker compose exec app make <target>`); never `pip install` by hand.

**Running the roadmap with several agents (lead + Sonnet/Haiku workers — added 2026-10-08).** Every open
block also carries **Depends.** (what must be `done` first; what it unblocks) and **Agent.** (model tier,
gate class, blocks that touch the same files, what its hand-off must name). The **§E board** is the
scheduling view; [`.claude/skills/orchestrate/SKILL.md`](.claude/skills/orchestrate/SKILL.md) is the
procedure. Rules that keep parallel work from colliding:

- **Line anchors in Files are hints.** They drift once an upstream block lands. Locate by the symbol the
  block names (`def retrieve`, `Citation:`), treat the number as approximate, and still do not widen the read.
- **A worker edits only** the files its Files line names, its own block, and its own board row. The Status
  snapshot and other blocks' Files lines belong to the lead, who applies them from the worker's **Handoff.**
- **Gate classes decide where work runs.** `offline` gates run from a git worktree against the built
  `adapta-app` image (command in gates.md). `live` and `rebuild` gates run on the main checkout, one at
  a time, with no other edit landing there meanwhile — hot reload kills live tests and `make up` restarts
  every container. Worktrees are not bind-mounted, so editing there is always safe.
- **Closing writes two notes, then moves the block.** **Done.** (≤ 8 lines) and **Handoff.** (what downstream
  blocks must now use: names, signatures, the migration revision taken, moved anchors, measured numbers). The
  block then goes to `CHANGELOG.md`; only its board row stays here. The lead reads Handoff there.
- **Tier is a floor, not a ceiling.** `haiku` rows are mechanical and fully specified; `sonnet` rows need
  design judgement; `sonnet + human decision` rows stop after the measurement so the user can decide.

---

## Status snapshot (updated 2026-10-09)

| Area | State |
|---|---|
| Product build (phases 0–5), operator console, image fine-tunes, brand, positioning | ✅ complete — history in [CHANGELOG.md](CHANGELOG.md) |
| Fine-tuning direction | **Decided 2026-10-09: bring your own adapter (§E4).** Adapta stops training; it imports a GGUF or PEFT LoRA, gates it on CPU against the base on the project's eval set, and serves it with RAG. Until E4.1 lands the training code still exists; after it no service needs a GPU. |
| SDD gates | Pillar 2 ✅ `make migrate-test` · Pillar 3: the GPU perplexity gate is replaced by the CPU task-metric gate on imported adapters (E4.3/E4.4) · Pillar 1 ✅ `make test-contracts` green twice 2026-10-09 (E1.11): 35 operations, ~2,060 cases, authenticated |
| CI fast gate (`make ci`) | ✅ green 2026-10-09 in the pinned app image (E1.10): ruff + mypy clean, 269 unit tests pass |
| **Audit 2026-09-03 (§E)** | 🟥 **open** — 11/37 done (E1.1–E1.9 shipped 2026-09-17, E1.14 on 2026-10-08, E1.10 on 2026-10-09). Wave 0: E1.11 left. Then E4.1 removes training and the GPU from the stack, alongside E2 (Ollama + launch kit) and E3 (Postgres chunks → real hybrid FTS, Docling + RapidOCR, citations with page/OCR provenance, system prompt + threshold + filters, multilingual, queued indexing, golden set); E4 (adapter import, CPU eval gate, adapter job, promotion/rollback, console flow, import guide, synthesis for eval sets, JSON mode); E5 (contextual retrieval, RAG gate, history-aware retrieval, visual extraction with the vision base). Scheduling: the §E board. |

---

## E. Audit 2026-09-03 — correctness, real hybrid RAG, scanned documents, governed adapters (opened 2026-09-03)

> **Source.** Product audit of 2026-09-03: code read with `file:line` evidence, GitHub API and a
> verified ecosystem scan. Headline: the product thesis (RAG + a gated adapter composed on one
> self-hosted OpenAI-compatible endpoint, Apache-2.0, orgs/keys in the box) is still unclaimed by any
> open-source project — but the shipped product is below what the README claims in five places:
> (1) "hybrid" retrieval only re-ranks the vector candidates (`adapta/services/rag.py:239`);
> (2) text SFT trains/evaluates on a prompt format the endpoint never serves (`trainer.py:117-125`
> vs `chat_templates.py:53-61`) and its loss is not response-only (`trainer.py:236-240`);
> (3) the gate measures perplexity only — every task metric is `None` (`evaluator.py:314-326`);
> (4) three of five catalog models are *Qwen Research License* (non-commercial), the default included;
> (5) ingestion has no OCR — scanned PDFs are rejected (`documents.py:134-135`) and images not accepted
> (`files.py:34`) although the §V VLM already reads invoices.
>
> **Scope guard (anti-over-engineering — a standing rule for this section).** A task is admitted only
> if it (a) fixes something that is false or broken today, (b) reuses what already exists (Redis queue,
> Postgres, the loaded VLM, the eval-gate rule), or (c) is a differentiator nobody ships. One
> dependency that replaces several beats wiring four. **Deferred until a real user asks:** guardrails,
> connectors (folder/S3 sync at most), Helm, OIDC, GraphRAG/RAPTOR, ColPali, Grafana dashboards. **Not built:** human-review queue UI, bounding-box editor,
> 50 connectors, a second vector store, multi-tenant SaaS.
>
> **Read budget.** Pick a block with `grep -n '^### E' TODO.md`; read that block and the files its
> **Files** line names — nothing else (see "How to pick up a task").
>
> **Labels** `[BE]` `[FE]` `[DOCS]` `[TEST]` `[INFRA]`. **Dependency order, tiers and gate classes** live
> in the board below and in each block's own **Depends.** / **Agent.** lines — the prose version was
> removed 2026-10-08 because a block-only reader never saw it.
>
> **Migration filenames in blocks are nominal** (`0010_chunks` …): take the next free revision at
> implementation time, keep the slug, report the real number in **Handoff.**

#### §E board — scheduling view for the lead agent (one row per open block; workers flip only their own row)

Status values: `open` · `in progress (agent)` · `ready-for-live (branch)` · `done YYYY-MM-DD`. A row may start
when every block in *Depends on* is `done`; rows sharing a *Serialize with* entry never run concurrently; gate
classes are defined in [`.claude/context/gates.md`](.claude/context/gates.md) ("Gate classes"). Procedure:
`.claude/skills/orchestrate/SKILL.md`. The lead refreshes the Status snapshot once per wave; workers never do.

| Block | Wave | Tier | Gate class | Depends on | Serialize with | Status |
|---|---|---|---|---|---|---|
| E1.14 | 0 | haiku | offline | none | E3.2/E3.5 (`chat.py`) | done 2026-10-08 |
| E1.10 | 0 | sonnet | rebuild (app image only) | none | E3.3b, E4.1 | done 2026-10-09 |
| E1.11 | 0 | sonnet | live | E1.10 | any in-flight `specs/openapi.yaml` edit | done 2026-10-09 |
| E2.1 | 1 | sonnet | live | none | E4.1, E4.9 (`core/backends/`) | open |
| E3.1 | 1 | sonnet | live | none | E3.7, E3.2 | done 2026-10-09 |
| E3.3a | 1 | sonnet + human decision | offline | none | — | open |
| E3.8 | 1 | sonnet | live | none — must land before E3.2 | — | done 2026-10-09 |
| E4.1 | 1 | sonnet | rebuild + live (exclusive) | E1.11 | E2.1, E3.3b, E3.7 | open |
| E3.2 | 2 | sonnet | live | E3.1, E3.8 (baseline recorded before this lands) | E3.7, E3.5 | open |
| E3.3b | 2 | sonnet | rebuild + live | E3.3a (commit), E3.1 | E4.1, E4.2, E4.4 (`pyproject.toml`, `Dockerfile`), E3.7, E3.4 | open |
| E3.7 | 2 | sonnet | live | E3.1, E4.1 | E3.1/E3.3b, E4.4 (`worker/main.py`) | open |
| E4.2 | 2 | sonnet | rebuild + live | E4.1 | E4.3 (spec, migrations), E4.5, E2.2 | open |
| E4.3 | 2 | sonnet | live | E4.1 | E4.2 (spec, migrations) | open |
| E4.8 | 2 | sonnet | live | E3.8, E4.1 | E4.6, E5.1 | open |
| E4.9 | 2 | sonnet | live | E1.11 | E2.1, E3.5/E5.3, E4.6 | open |
| E3.4 | 3 | sonnet | live | E3.1, E3.3b, E1.11 | E3.5 (spec, `Playground.svelte`), E3.3b | open |
| E3.5 | 3 | sonnet | live | E3.2, E1.11 | E3.4 (spec, `Playground.svelte`), E4.9 and E5.3 | open |
| E3.6 | 3 | sonnet + human decision | live | E3.1, E3.2, E3.8 | E3.2 | open |
| E4.4 | 3 | sonnet | rebuild + live | E4.2, E4.3 | E3.7, E3.3b | open |
| E5.1 | 3 | sonnet | live | E3.1, E3.7, E3.8 | E5.2, E4.8 | open |
| E5.2 | 3 | sonnet | live | E3.8, E3.7, E4.8 | E5.1, E4.5 | open |
| E2.2 | 4 | sonnet | live | E2.1, E4.4 | E4.5 (`endpoints.py`, `EndpointPanel.svelte`) | open |
| E4.5 | 4 | sonnet | live | E4.4 | E2.2, E4.6, E5.2 | open |
| E4.6 | 4 | sonnet | live | E4.4 | E4.5, E4.8, E4.9 | open |
| E5.3 | 4 | sonnet | live | E3.2, E3.5, E3.8 | E4.9/E3.5 | open |
| E5.4 | 4 | sonnet | live | E3.3b, E3.4, E3.5, E3.7 | E5.1/E5.2, E3.4 | open |
| E4.7 | 5 | sonnet | offline | E4.4, E4.5, E4.6 | E2.3 (README) | open |
| E2.3 | 6 | haiku | offline | E1.11, E4.7 | E3.2, E3.3b, E4.7 (README) | open |

### E1. P0 — corrections that change the publishable evidence (weeks 1–2)

E1.1–E1.9 shipped 2026-09-17 → [CHANGELOG.md](CHANGELOG.md). E1.14 closed 2026-10-08, E1.10 and E1.11 on 2026-10-09 — wave 0 is done.


### E2. Distribution + launch kit (weeks 2–3)

### E2.1 `[BE+INFRA]` Ollama as an inference backend for base-model and RAG-only endpoints (P1)
- [ ] **Context.** `adapta/core/backends/` already abstracts serving (`ServingBackend` ABC; llama-cpp
  default). Ollama (180k★, MIT) is the substrate the local-AI ecosystem
  builds on — Open WebUI grew by attaching to it, and every "works with Ollama" integration is a free
  acquisition channel. RAG-only and base endpoints don't need an in-process llama-cpp when an Ollama
  host exists.
- **Depends.** none. **Unblocks.** E2.2.
- **Agent.** sonnet · gate class **live (`--profile ollama`)** · serialize with: E4.1, E4.9
  (`core/backends/*.py`) · **Handoff.** must name `ollama_model_map` keys and the routing rule.
- **Scope.** Read-only client for adapter-less text requests via Ollama's OpenAI-compatible
  `/v1/chat/completions`. Out: serving imported adapters through Ollama at runtime (E2.2 exports
  them), vision.
- **Steps.** (1) `core/backends/ollama_backend.py`: `OllamaBackend(ServingBackend)` with httpx (already
  a dep), implementing the same interface as `llamacpp.py` — `prepare()`, non-streaming + streaming, usage from Ollama's
  `prompt_eval_count`/`eval_count` (exact token counts). (2) Routing in
  `core/backends/__init__.py`: `ADAPTA_SERVING_BACKEND=ollama` sends adapter-less text requests to
  Ollama; adapters and vision stay on llama-cpp. (3) `config.py`: `ollama_base_url`,
  `ollama_model_map` (catalog name → Ollama tag; default map for the Apache entries of E1.2).
  (4) `docker-compose.yml`: optional `ollama` service under `profiles: [ollama]` (official image,
  CPU; an operator with a GPU adds `devices` in their own override). (5) `tests/test_backend_ollama.py`: mocked httpx transport — routing,
  usage mapping, streaming frames. (6) OPERATIONS §9-style runbook "Serve RAG through Ollama".
- **Files.** `adapta/core/backends/base.py`, `adapta/core/backends/llamacpp.py` (interface),
  `adapta/core/backends/__init__.py` (routing), `adapta/config.py`, `docker-compose.yml`,
  `docs/reference/OPERATIONS.md` §9.
- **Contract impact.** None (env config).
- **Gate.** `make test` → live: `docker compose --profile ollama up -d` + one RAG chat in the playground.
- **Acceptance.** With the profile on, a RAG project's endpoint answers through Ollama with exact token
  counts and citations; llama-cpp still serves adapters and vision; `make ci` green.
- **Close.** OPERATIONS §9 sibling section; README "Using the API" one line; Status snapshot.

### E2.2 `[BE]` Export a gated adapter as an Ollama Modelfile bundle (P2)
- [ ] **Context.** Ollama imports LoRA adapters with a `Modelfile` (`FROM <base>` + `ADAPTER <path>`).
  Every `passed` adapter has a GGUF LoRA (E4.4); exporting it with the base tag, template and gate line
  lets any Ollama user run a gate-verified adapter — the adapter travels to 180k★ of users.
- **Depends.** E2.1, E4.4. **Unblocks.** none.
- **Agent.** sonnet · gate class **live** · serialize with: E4.5 (`endpoints.py`,
  `EndpointPanel.svelte`, spec endpoint section) · **Handoff.** must name the route and zip layout.
- **Scope.** A zip `{adapter.gguf, Modelfile, README.txt}` for endpoints serving a `passed` adapter. Out: pushing to
  ollama.com.
- **Steps.** (1) Spec `GET /v1/projects/{id}/endpoint/export?format=ollama` → `application/zip`,
  writer role, 404 without a gated adapter. (2) Handler builds the zip in a temp dir: the GGUF LoRA, a
  `Modelfile` (`FROM` = the catalog entry's Ollama tag from E2.1's map, `ADAPTER ./adapter.gguf`,
  `TEMPLATE`/`PARAMETER stop` from `chat_templates.py`), and a README carrying the gate line (score,
  base, delta, date). (3) Console `EndpointPanel.svelte`: "Export for Ollama". (4) Tests: zip
  contents + Modelfile text; 404 path.
- **Files.** `specs/openapi.yaml` (endpoint section), `adapta/api/v1/endpoints.py`,
  `adapta/core/chat_templates.py`, `adapta/services/adapters.py`,
  `adapta/console/src/views/EndpointPanel.svelte`, `tests/test_adapter_upload.py`.
- **Contract impact.** API (new route).
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `make test-contracts`.
- **Acceptance.** `ollama create adapta-demo -f Modelfile` on a host with the base tag yields a model
  that answers in the adapter's shape (manual check, recorded in the Done note).
- **Close.** consuming-the-api "Export to Ollama"; Status snapshot.

### E2.3 `[DOCS]` Launch kit: README first screen, migration guides, honest status (P1)
- [ ] **Context.** The licensing advantage (Apache-2.0 with orgs/keys in the box, versus Open WebUI's
  >50-user branding clause, Dify's multi-tenant ban, Kiln's proprietary desktop app, Onyx's SSO/RBAC in
  EE) lives only in COMPETITIVE_LANDSCAPE. Flowise (55k★, Apache-2.0) archived 2026-08-13; Cognita and
  Verba archived; R2R stale since 2025-11 — their users are looking for a home now. The README status
  note ("working prototype — not production-hardened") is honest but reads as self-sabotage.
- **Depends.** E1.11 (no claim about a red gate), E4.7 (the pitch it builds on). **Unblocks.** none.
- **Agent.** haiku · gate class **offline (`make docs-build`)** · serialize with: E3.2, E3.3b, E4.7
  (README — text merge) · **Handoff.** must name none (self-contained).
- **Scope.** Copy + one new user-guide page. Claim nothing a closed block hasn't made true.
- **Steps.** (1) README: a 6-row "what you get under Apache-2.0" table (feature · Adapta · the
  restriction elsewhere, each cell linking the other project's license page) above the fold; status
  note → "beta: works end to end; audit the auth and eval-gate paths before sensitive data".
  (2) `docs/user-guide/migrating.md`: from Flowise / Cognita / R2R — concept mapping (flow → project,
  document store → files, chain → endpoint), what has no equivalent (the canvas), a 10-line curl path.
  (3) COMPETITIVE_LANDSCAPE: license-restriction column with citations; rows for Kiln and BISHENG
  (verified 2026-09-03). (4) `mkdocs.yml` nav + hub links.
- **Files.** `README.md`, `docs/user-guide/migrating.md` (new), `docs/user-guide/index.md`,
  `docs/reference/COMPETITIVE_LANDSCAPE.md`, `mkdocs.yml`.
- **Contract impact.** None.
- **Gate.** `make docs-build` (host, `--strict`).
- **Acceptance.** Every cell of the new table links a primary source; the migration page is in nav; the
  README status note no longer says "prototype".
- **Close.** Self-contained; Status snapshot.

### E3. P1 — real hybrid RAG + scanned documents (weeks 3–7)

### E3.2 `[BE]` Real hybrid retrieval: Postgres full-text leg over the whole corpus, fused with the vector leg (P1)
- [ ] **Context.** `_bm25_scores` runs over the ≤ 20 Chroma candidates (`rag.py:239`): IDF over 20
  documents, and a keyword-only chunk the embedder missed can never be recalled; it is recomputed per
  query with an O(|q|·N·L) loop (`rag.py:91`). This is the README's "hybrid" claim, and it does not hold.
- **Depends.** E3.1, E3.8 (baseline recorded **before** this lands). **Unblocks.** E3.5, E3.6, E5.3.
- **Agent.** sonnet · gate class **live (rag e2e, then `make golden`)** · serialize with: E3.7
  (`rag.py`), E3.5 (`rag.py`, `chat.py`) · **Handoff.** must name `retrieve()` signature, new config
  keys, the log-line format, recall@5 before/after.
- **Scope.** Sparse leg = Postgres FTS over `chunks.tsv` (E3.1); RRF over two *independent* top-N
  lists; delete `_bm25_scores`. Reranker unchanged. Out: multi-query (E5.3), thresholds (E3.5).
- **Steps.** (1) `config.py`: `rag_fts_config` (`simple` | `english` | `spanish`; default `simple`
  until E3.6), `rag_sparse_fetch_multiplier` (default 4). (2) `retrieve`: run the Chroma query and
  `SELECT id, ts_rank_cd(tsv, websearch_to_tsquery(:cfg, :q)) AS r FROM chunks WHERE project_id=:p
  AND tsv @@ websearch_to_tsquery(:cfg, :q) ORDER BY r DESC LIMIT :n` in the same thread (sync session)
  so the 10 s guard in `chat.py:30-41` still wraps the whole path. (3) Union by chunk id,
  `_rrf_fuse(vec_order, fts_order)`, hydrate text/metadata from Postgres with one
  `WHERE id = ANY(:ids)`. (4) Rerank top `top_k*2` as today. (5) Delete `_bm25_scores` and
  `_tokenize`; rewrite the BM25 tests as FTS tests. (6) One structured log line per retrieval: query
  hash, ids, fused ranks, reranker scores, ms.
- **Files.** `adapta/services/rag.py:56-110, 196-277`, `adapta/services/chat.py:30-41`,
  `adapta/config.py:80-95`, `tests/test_rag_hybrid.py`, `docs/concepts/stack.md` (hybrid section),
  `README.md` "Give it knowledge" bullet.
- **Contract impact.** None.
- **Gate.** `make test` → `tests/integration/test_rag_e2e.py` (add the exact-code case).
- **Acceptance.** New test: a chunk outside the vector top-20 with an exact keyword match is returned;
  `_bm25_scores` is gone; the retrieval log line exists; e2e green.
- **Close.** README bullet, PRODUCT_DEFINITION Service A, knowledge-and-behavior retrieval box,
  concepts/stack.md, COMPETITIVE_LANDSCAPE retrieval note (the claim becomes true — date it); Status
  snapshot.

### E3.3a `[INFRA+TEST]` Spike: measure Docling + RapidOCR before adopting it (P1 · half a day · kill-or-commit)
- [ ] **Context.** Docling (MIT, ~66k★) replaces `pypdf` + `python-docx` + the HTML regex and adds
  page/heading/table provenance and OCR only where a page has no text layer
  (`OcrMode.PDF_AWARE_LAYOUT_REGIONS`, the default). Its docs suggest ≈ 500 MB installed; the tech
  report (arXiv 2501.17887) measures median 0.79 s/page, p95 16 s on an 8-core x86. Base
  `pip install docling` ships **no** OCR engine — `docling[rapidocr]` is required. The scope guard
  says: measure before committing ~500 MB.
- **Depends.** none. **Unblocks.** E3.3b (the commit/fall-back decision).
- **Agent.** sonnet + **human decision** · gate class **offline (scratch container from the
  `adapta-app` image; the stack is not needed)** · serialize with: none · **Handoff.** must name the
  four numbers and the decision line — the lead shows them to the user before E3.3b starts.
- **Scope.** A throwaway container + four numbers. No product code.
- **Steps.** (1) `docker compose run --rm app pip install "docling[rapidocr]"` in a scratch container
  (never the host, never the running image). (2) Measure: image-size delta; s/page on three PDFs
  (native 20 pp, scanned 5 pp, mixed) with `latin_PP-OCRv5_rec_mobile`; peak RAM. (3) Confirm: page
  numbers per element, a DOCX table → markdown, per-line OCR confidence from RapidOCR. (4) Record in
  OPERATIONS ("Ingestion sizing", 6 lines) and decide: commit (E3.3b) or fall back to Tier 0
  (`rapidocr` + `pypdfium2`, no layout).
- **Files.** Scratch only; `docs/reference/OPERATIONS.md` (new subsection). The Done note carries the
  numbers.
- **Contract impact.** None.
- **Gate.** None (spike); the Done note is the artefact.
- **Acceptance.** MB, s/page ×3, RAM recorded + the decision line "commit E3.3b" or "fall back to
  Tier 0 (re-scope E3.3b)".
- **Close.** OPERATIONS subsection; Status snapshot.

### E3.3b `[BE]` One parser: Docling (+RapidOCR) for PDF/DOCX/HTML/images, page-aware chunking (P1)
- [ ] **Context.** `documents.py` flattens newlines before chunking (`:98`) so pages are unrecoverable;
  DOCX tables are dropped (`:49`); HTML is stripped by regex (`:60`); scanned PDFs are rejected
  (`:134-135`); images are not accepted (`files.py:34`). E3.3a measured the replacement.
- **Depends.** E3.3a (commit), E3.1. **Unblocks.** E3.4, E5.4.
- **Agent.** sonnet · gate class **rebuild + live** · serialize with: E4.1, E4.2, E4.4
  (`pyproject.toml`, `Dockerfile`), E3.7 (`documents.py`), E3.4 (`RagFlow.svelte`) · **Handoff.** must name the `Chunk` fields, accepted
  extensions, `ocr_review_threshold`, image-size delta and s/page.
- **Scope.** Parser + chunker + accepted types + OCR metadata. Out: VLM extraction (E5.4), review UI.
- **Steps.** (1) `pyproject.toml`: `docling[rapidocr]`; drop `pypdf`, `python-docx`, `markdown` if
  nothing else imports them (`grep -rn` in `adapta/` only). `make up`. (2) `documents.py`:
  `parse(path) -> DoclingDocument` with `RapidOcrOptions(lang=["latin"])`, `do_ocr=True`, default OCR
  mode; `chunk(doc)` via `HybridChunker` (tokenizer = the embedding model) emitting
  `Chunk(text, index, page, section, ocr, ocr_confidence)` — page from element provenance, `ocr` true
  when the page had no text cells, `ocr_confidence` = mean RapidOCR line score for that page (else
  NULL). Tables → markdown; a table over the chunk budget splits by rows repeating the header.
  (3) `files.py` `_ALLOWED_EXTENSIONS` += `.png .jpg .jpeg .tif .tiff`; console `accept` list aligned
  (fixes the `.markdown` mismatch, B8). (4) `needs_review = ocr and ocr_confidence <
  settings.ocr_review_threshold` (default 0.90), stored on the E3.1 columns. (5) Tests: parser cases
  per format from small fixtures under `tests/fixtures/` (add a 1-page scanned PDF and a PNG); page
  numbers asserted; a low-confidence fixture sets `needs_review`.
- **Files.** `pyproject.toml`, `adapta/services/documents.py` (rewrite), `adapta/api/v1/files.py:28-40`,
  `adapta/console/src/views/RagFlow.svelte:188-237`, `adapta/config.py`, `tests/test_basic.py:45-100`,
  `tests/fixtures/` (new); `Dockerfile` only if RapidOCR needs a system lib (it should not).
- **Contract impact.** None yet (metadata stays internal until E3.4 exposes it).
- **Gate.** `make up` (rebuild) → `make test` → `tests/integration/test_rag_e2e.py` with the scanned
  fixture.
- **Acceptance.** A scanned PDF indexes with `ocr=true` and page numbers; a PNG invoice indexes; a DOCX
  table survives as markdown in a chunk; the "OCR scanned PDFs first" guidance is deleted from the
  console and docs; image-size delta and s/page recorded next to E3.3a's numbers.
- **Close.** knowledge-and-behavior (supported inputs), operator-console files table, OPERATIONS
  sizing, README bullet ("scanned PDFs and images included"), CLAUDE.md "Knowledge (RAG)" line; Status
  snapshot.

### E3.4 `[BE+FE]` Citations with text, page and OCR provenance; review flags in the files table (P1)
- [ ] **Context.** Citations are `{index, source, score}` (`rag.py:294-298`, spec `Citation`); the
  console already tries to render `c.text` the server never sends (`Playground.svelte:283`). With
  E3.1/E3.3b the data exists.
- **Depends.** E3.1, E3.3b, E1.11. **Unblocks.** E5.4.
- **Agent.** sonnet · gate class **live (+ `make console-build` on the main checkout)** · serialize
  with: E3.5 (spec, `Playground.svelte`), E3.3b (`RagFlow.svelte`) · **Handoff.** must name the
  final `Citation` fields.
- **Scope.** API shape + console rendering. Out: bbox highlighting.
- **Steps.** (1) Spec `Citation` += `text`, `page` (nullable), `file_id`, `ocr` (bool), `confidence`
  (nullable); `FileResponse` += `pages_needing_review` (int). `make generate`. (2) `format_citations`
  fills them from the hydrated rows. (3) `files.py` list/get compute `pages_needing_review` in one
  aggregate query. (4) Console: Playground citation card shows `source · p.N · OCR conf 0.83` with the
  text in a collapsible; RagFlow file table shows a warning chip "N pages low-confidence OCR" with the
  guidance ("re-scan, or re-read with the visual extractor when available"). (5) Tests:
  `format_citations` shape; contract gate.
- **Files.** `specs/openapi.yaml` (`grep -n "Citation:"`, `FileResponse`), `adapta/services/rag.py:279-298`,
  `adapta/api/v1/files.py:40-60`, `adapta/console/src/lib/types.ts` (`grep -n Citation`),
  `adapta/console/src/views/Playground.svelte:270-295`, `adapta/console/src/views/RagFlow.svelte:251-287`,
  `tests/test_rag_hybrid.py:271-291`, `docs/user-guide/consuming-the-api.md` (citations).
- **Contract impact.** API.
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `make test-contracts` → `make console-build`.
- **Acceptance.** A chat response cites `factura.pdf · p.2 · OCR 0.83` with the chunk text; the files
  table flags low-confidence pages; contract gate green.
- **Close.** consuming-the-api citations; operator-console playground + files; Status snapshot.

### E3.5 `[BE+FE]` Per-project system prompt, retrieval threshold + abstention, request-level filters (P1)
- [ ] **Context.** No project system-prompt column (`db/models.py:209-262`); `api/v1/chat.py:151-159`
  never passes one; a client `system` message lands *after* the RAG block (`chat_templates.py:53-60`).
  Retrieval always injects `top_k` chunks with no minimum score (`rag.py:277`), and with zero chunks
  the model gets no system prompt at all (`chat.py:190-191`). `collection.query` has no `where`
  (`rag.py:226-230`); the request has no filter field.
- **Depends.** E3.2, E1.11. **Unblocks.** E5.3, E5.4.
- **Agent.** sonnet · gate class **live** · serialize with: E3.4 (spec, `Playground.svelte`), E4.9
  and E5.3 (`chat.py`) · **Handoff.** must name the `adapta.*` request namespace shape, the
  `_build_system` order, the migration revision.
- **Scope.** Three small, related knobs. Out: ACL (open a block when a user asks), multi-query.
- **Steps.** (1) Migration `0011_project_system_prompt`: `projects.system_prompt TEXT NULL`. Spec:
  `ProjectCreateRequest`/`ProjectResponse` += `system_prompt`; add `PATCH /v1/projects/{id}` if no
  update route exists (check the spec first). (2) `_build_system` order: project prompt → RAG block →
  abstention line ("If the answer is not in the context, say you can't find it in the documents") →
  the client `system` merged as a paragraph, not a later turn. (3) `config.py` `rag_min_score`
  (default 0.2 on the reranker scale; 0 disables): chunks below are dropped; zero chunks →
  `citations: []` with the abstention line still present. (4) Spec `ChatCompletionRequest` += optional
  `adapta: {filters: {file_ids?, page_min?, page_max?, needs_review?}, top_k?}` (namespaced so OpenAI
  clients ignore it); `rag.py` applies it as Chroma `where` on `file_id` and SQL `WHERE` on the FTS
  leg; `top_k` bounded. (5) Console: project Settings tab gets the system-prompt textarea; Playground a
  file-filter multiselect. (6) Tests: `_build_system` ordering; threshold drops; filters reach both
  legs (mocked).
- **Files.** `migrations/versions/0011_project_system_prompt.py`, `adapta/db/models.py:209-262`,
  `specs/openapi.yaml` (projects + chat request), `adapta/services/chat.py:187-198, 240-300`,
  `adapta/services/rag.py:196-277`, `adapta/api/v1/chat.py:120-160`, `adapta/api/v1/projects.py`,
  `adapta/console/src/views/Project.svelte`, `adapta/console/src/views/Playground.svelte`,
  `tests/test_context_fit.py`, `tests/test_rag_hybrid.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate` → `make migrate-test` → `make validate-spec` → `make generate` →
  `make check-models` → `make test` → `make test-contracts` → `make console-build`.
- **Acceptance.** An out-of-corpus question yields "I can't find that in the documents" with
  `citations: []`; a request filtered to one file cites only it; the project prompt precedes the RAG
  block in the rendered prompt (unit test).
- **Close.** consuming-the-api (`adapta` extension), operator-console settings + playground,
  PRODUCT_DEFINITION Service A; Status snapshot.

### E3.6 `[BE]` Multilingual defaults + safe embedding-model migration (P1)
- [ ] **Context.** `all-MiniLM-L6-v2` (`config.py:80`) and `cross-encoder/ms-marco-MiniLM-L-6-v2`
  (`config.py:89`) are English models; the FTS config from E3.2 defaults to `simple`. The author
  documents in Spanish and the ecosystem is English-first — a cheap, verifiable differentiator. E1.8
  made a model swap a typed 409; there is still no re-embed tool.
- **Depends.** E3.1, E3.2, E3.8. **Unblocks.** none.
- **Agent.** sonnet + **human decision** · gate class **live (rag e2e + `make golden`)** · serialize
  with: E3.2 (`config.py`) · **Handoff.** must name the measured table (recall@5, latency, RAM per
  candidate) — the lead shows it to the user before `config.py` defaults change.
- **Scope.** New defaults chosen by measurement + a re-embed script. Candidates on the E3.8 golden set:
  embeddings `intfloat/multilingual-e5-small` (384d, drop-in dimension) vs `BAAI/bge-m3` (1024d,
  heavier); reranker `BAAI/bge-reranker-v2-m3`. Pick by recall@5 (es+en) and CPU latency; record both.
  Out: per-project embedding models.
- **Steps.** (1) `scripts/reembed.py`: per project, read chunks from Postgres (E3.1), re-embed with
  `settings.embedding_model`, rebuild the Chroma collection, update `Collection.embedding_model`;
  idempotent, resumable per project. (2) Measure the candidates with `make golden`; set `config.py`
  defaults; `rag_fts_config` default from `ADAPTA_LANG` (`spanish` | `english`, fallback `simple`).
  (3) `embeddings.py`: assert the dimension on load and persist it on `Collection` (nullable column
  via `0012_collection_dim` if `db/models.py:311` has none). (4) OPERATIONS: "Changing the embedding
  model" = set env → `scripts/reembed.py` → restart; RAM/latency table for both candidates.
- **Files.** `adapta/config.py:78-95`, `adapta/services/embeddings.py:40-91, 145-156`, new
  `scripts/reembed.py`, `docs/reference/OPERATIONS.md`, `.env.example`, `tests/test_rag_hybrid.py`
  (dimension guard).
- **Contract impact.** DB only if the dimension column is new.
- **Gate.** `make test` → `tests/integration/test_rag_e2e.py` (add one Spanish and one English query
  over a bilingual fixture) → `make golden`.
- **Acceptance.** Bilingual e2e green; the chosen defaults with measured recall/latency are in
  OPERATIONS; `scripts/reembed.py` migrates a project end to end on the live stack.
- **Close.** OPERATIONS, README ("Spanish and English out of the box"), knowledge-and-behavior; Status
  snapshot.

### E3.7 `[BE]` Indexing as a queued job with retry + per-request retrieval metrics (P1)
- [ ] **Context.** Indexing runs in a FastAPI `BackgroundTasks` closure (`files.py:182`): no retry, no
  visibility, rows stuck in `processing` after a restart (the sweeper does not cover index rows). `core/metrics.py:177-221` has no retrieval metrics. **Measured 2026-10-09 (E3.8):** ~30 concurrent uploads start ~30
  background tasks and exhaust the DB pool (`QueuePool limit of size 10 overflow 20 reached`; `GET /files` then hangs) — the
  golden harness uploads in batches of 4 until this block bounds indexing concurrency. Since E3.1 the upload handler
  parses + chunks synchronously and passes `chunks` to `_index_file`; collection get-or-create and counters are race-free.
- **Depends.** E3.1, E4.1 (the worker's `kind` dispatch table). **Unblocks.** E5.1, E5.2, E5.4.
- **Agent.** sonnet · gate class **live (`docker compose restart worker` + rag e2e + sweep test)** ·
  serialize with: E3.1/E3.3b (`files.py`, `documents.py`), E4.4 (`worker/main.py`,
  `services/jobs.py`, `services/maintenance.py`) ·
  **Handoff.** must name the job payload shape (`kind`), `_run_index_job`, the metric names, the
  gates.md trap added.
- **Scope.** Reuse the Redis BLPOP queue and E4.1's `kind` dispatch table. Out: a second worker
  process, priorities.
- **Steps.** (1) Register `_run_index_job` under `kind: "index"` in the worker's dispatch table.
  (2) `files.py` enqueues `{kind: "index", id: file_id}`; the worker writes `pending → processing → indexed/failed`; one
  retry on transient failure; the sweeper learns the `index` kind. (3) Hot-reload trap: changes to
  `adapta/services/documents.py` now need `docker compose restart worker` — add to gates.md.
  (4) Metrics: `adapta_rag_retrieval_seconds` (histogram), `adapta_rag_chunks_returned`,
  `adapta_rag_reranker_seconds`, `adapta_index_seconds_per_page`. (5) Tests: `test_jobs.py` kind
  dispatch; `test_observability.py` metric names; `test_stuck_task_sweep.py` covers index rows.
- **Files.** `adapta/services/jobs.py`, `adapta/worker/main.py` (dispatch table + `_run_index_job`),
  `adapta/api/v1/files.py:80-135`, `adapta/services/maintenance.py`, `adapta/core/metrics.py:177-221`,
  `adapta/services/rag.py`, `.claude/context/gates.md`, `tests/test_jobs.py`,
  `tests/test_observability.py`, `tests/integration/test_stuck_task_sweep.py`.
- **Contract impact.** None (`FileResponse.status` values unchanged).
- **Gate.** `make test` → `docker compose restart worker` → `tests/integration/test_rag_e2e.py` +
  `test_stuck_task_sweep.py`.
- **Acceptance.** Killing the app mid-index leaves no row in `processing` after the sweeper runs;
  `/metrics` exposes the four new series; e2e green.
- **Close.** architecture.md (ingestion on the queue), OPERATIONS (worker restarts), gates.md trap;
  Status snapshot.

### E4. Bring your own adapter — Adapta verifies and serves adapters; it does not train them (weeks 3–9)

> **Decision (2026-10-09).** In-product QLoRA training is removed. It needed a CUDA host, a 7.4 GB worker
> image and a torch/triton/bitsandbytes/peft/trl set whose drift broke every training job on one rebuild
> (E1.9), and its GPU-only gates serialized the roadmap — for a capability whose real use is narrow
> (classification, output format, extraction on small bases; knowledge belongs in RAG). What stays is the
> differentiator: an adapter serves only after it beats the base on the project's own eval set, and it
> composes with RAG on one OpenAI-compatible endpoint. Operators train where they already do (Unsloth,
> Axolotl, TRL, Colab) and import the result.
>
> **Fixed choices.** Accepted: a GGUF LoRA, or a PEFT adapter (`adapter_model.safetensors` +
> `adapter_config.json`) converted on CPU — never pickle (`.bin`, `.pt`). An eval set is mandatory: no eval
> set, no gate, no serving. Text adapters only (vision adapters: §E6). No training code ships in the repo;
> the import guide (E4.7) states what an external run must match.
>
> **One image, all CPU.** After E4.1 the worker runs the `app` image and consumes queued job kinds
> (`adapter` E4.4, `index` E3.7, `extract` E5.4); no service reserves a GPU. Optional llama.cpp GPU offload
> for serving (`ADAPTA_N_GPU_LAYERS`) is unaffected.

### E4.1 `[INFRA+BE+FE]` Remove in-product training: CUDA worker, GPU reservation, trainer, `/jobs`, vLLM (P1)
- [ ] **Context.** Training is the only reason the stack needs CUDA: `Dockerfile:98-145` (worker-builder +
  worker stages), `docker-compose.yml:72-111` (`devices: nvidia.com/gpu=all`), `docker-compose.cpu.yml`,
  `Makefile:21-26, 65-75` (GPU detection, `up-cpu`), `pyproject.toml` `[training]`. The vLLM sidecar
  (`core/backends/vllm_backend.py`, compose `vllm-server`) exists only to pack trained LoRAs on a GPU.
- **Depends.** E1.11. **Unblocks.** E3.7, E4.2, E4.3, E4.8.
- **Agent.** sonnet · gate class **rebuild + live (exclusive)** · serialize with: E2.1 (`core/backends/`),
  E3.3b (`pyproject.toml`, `Dockerfile`), E3.7 (`worker/main.py`) · **Handoff.** must name the migration
  revision, the worker dispatch-table name, the fixture paths, the app image size.
- **Scope.** Delete outright — no shim, no "training disabled" message, no compatibility path. Out: the
  import path (E4.2–E4.4), the new console flow (E4.6), the pitch docs (E4.7 rewrites them once).
- **Steps.** (1) **First**, copy two 0.5B fixtures out of `data/adapters/` into `tests/fixtures/adapters/`:
  the use-case matrix's passing classification adapter and its gate-failing control — `adapter_config.json`,
  `adapter_model.safetensors`, `adapter.gguf` when present, the held-out `dataset_eval.jsonl` (identify by
  `training_metadata.json`). They cannot be re-trained after this block. (2) Delete `adapta/training/`,
  `services/adapters.py` (JSON registry), `api/v1/jobs.py`, `core/backends/vllm_backend.py`,
  `core/gpu.py` `torch_cuda_status`, `catalog.train_vram_gb`, the vllm settings. Keep the SFT-row validator
  from `services/training.py` as `services/datasets.py`; drop its DPO, vision-bundle, enqueue and recovery
  code. (3) Spec: delete `/jobs*`, `JobCreateRequest`, `JobResponse`, `JobSummary`, `TrainingConfigInput`,
  `AdapterProvenance`, `BaseModelInfo.train_vram_gb`. Migration `drop_training`: `training_jobs`,
  `datasets.modality`, `datasets.num_images`; `ProjectStatus.training` goes. `create_endpoint` on a
  `finetune` project raises `InvalidRequest("Import an adapter first")`. Schema
  `training_dataset.schema.json` → `eval_dataset.schema.json`, SFT row only. (4) `worker/main.py`: keep
  loop, heartbeat, healthcheck, SIGTERM requeue; dispatch on `meta["kind"]` through an empty handler table;
  an unknown kind fails the job with a typed error. (5) Infra: delete both worker stages,
  `docker-compose.cpu.yml`, `vllm-server`, GPU detection + `up-cpu`; worker = `target: app` + its command;
  same in `docker-compose.prod.yml`. `pyproject.toml`: delete `[training]`; move the `torch<3` and
  `transformers<6` bounds into main deps (sentence-transformers needs both). (6) Tests + console: delete
  what trains or imports `adapta.training` (`grep -rlE 'adapta\.training|/jobs|ADAPTA_RUN_(LORA|VLM)'
  tests/`); console keeps dataset upload/review, loses the train step, gate panel and VRAM column.
- **Files.** `Dockerfile`, `docker-compose.yml`, `docker-compose.cpu.yml`, `docker-compose.prod.yml`,
  `Makefile`, `pyproject.toml`, `adapta/training/`, `adapta/worker/main.py`, `adapta/services/{training,adapters,jobs,maintenance}.py`,
  `adapta/api/v1/{jobs,endpoints,datasets,synthesis}.py`, `adapta/api/app.py:330-360`, `adapta/core/{gpu,model_catalog,adapter_conversion}.py`,
  `adapta/core/backends/`, `adapta/config.py`, `adapta/db/models.py`, `migrations/versions/`, `specs/openapi.yaml`,
  `specs/schemas/training_dataset.schema.json`, `adapta/console/src/views/{FinetuneFlow,Models,EndpointPanel}.svelte`,
  `adapta/console/src/lib/types.ts`, `tests/`.
- **Contract impact.** API + DB + model (schema rename).
- **Gate.** `make up` (no CUDA wheel downloaded) → `make migrate-test` → `make validate-spec` →
  `make generate` → `make check-models` → `make ci` → `make test-contracts` → `make console-build` →
  `tests/integration/test_rag_e2e.py`.
- **Acceptance.** One Adapta image; `make up` succeeds on a host without the NVIDIA toolkit and with no
  override file; `grep -rnE 'peft|trl|bitsandbytes|vllm|torch\.cuda' adapta/ pyproject.toml Dockerfile docker-compose*.yml`
  is empty; RAG e2e and the contract gate green; the fixtures are committed.
- **Close.** CLAUDE.md (Stack, hard constraint #1 list, Workflow pillar 3, API surface); `gates.md` (drop
  the `gpu` class and training rows); `repo-map.md`; `stack` skill; OPERATIONS (sizing, GPU sections);
  architecture.md; README run instructions; delete `fine-tuning-walkthrough.md`, `fine-tuning-use-cases.md`,
  `vlm-fine-tuning.md`, `ocr-vision-walkthrough.md` + their `mkdocs.yml` nav and inbound links; Status snapshot.

### E4.2 `[BE]` Adapter contract: `adapters` table, upload route, endpoint bound to an adapter (P1)
- [ ] **Context.** After E4.1 a `finetune` project has no way to obtain a servable adapter, and
  `Endpoint.adapter_path` (`db/models.py:428-430`) is a bare path with no provenance that
  `api/v1/chat.py:135` serves as-is.
- **Depends.** E4.1. **Unblocks.** E4.4.
- **Agent.** sonnet · gate class **rebuild + live** (new pip dependency) · serialize with: E4.3 (spec,
  migrations), E4.5 and E2.2 (`endpoints.py`) · **Handoff.** must name the table columns, routes, status
  enum, error classes and migration revision.
- **Scope.** Contract, upload, static validation, storage; an accepted adapter lands `uploaded`. Out:
  conversion, load probe and scoring (E4.4), promotion (E4.5).
- **Steps.** (1) Migration `adapters`: `adapters(id, project_id FK CASCADE, name, base_model, format
  gguf|peft, peft_dir NULL, gguf_path NULL, sha256, size_bytes, eval_dataset_id FK datasets, status
  uploaded|processing|passed|failed, failure_reason NULL, eval_metrics JSONB NULL, created_by FK users,
  created_at)`; `endpoints.adapter_path` → `endpoints.adapter_id` (FK, nullable). (2) Spec:
  `POST /v1/projects/{id}/adapters` (multipart: one `.gguf`, or a `.zip` holding exactly
  `adapter_model.safetensors` + `adapter_config.json`; `eval_dataset_id` required; writer) → 202
  `AdapterResponse`; `GET …/adapters`, `GET …/adapters/{aid}`, `DELETE …/adapters/{aid}` (409 while bound);
  `EndpointResponse.adapter: AdapterResponse`. (3) `services/adapters.py` validation, each failure a typed
  `DomainError` naming the expected value: extension + magic bytes; zip members exact (no dirs, no `..`,
  nothing else); `settings.adapter_max_upload_mb` (512); PEFT `peft_type == "LORA"` and
  `base_model_name_or_path` ∈ the catalog entry's `hf_repo_id` + new `adapter_base_aliases` (Unsloth repos);
  GGUF `general.type == "adapter"`, `adapter.type == "lora"`, architecture = the base's (read with `gguf`,
  added to `pyproject.toml`). Stored under `adapters_dir/{id}/`. (4) `create_endpoint` on `finetune`: latest
  `passed` adapter, else `InvalidRequest`; chat resolves the GGUF through `adapter_id`. (5) Tests: every
  rejection, zip traversal, endpoint refuses a non-passed adapter.
- **Files.** `migrations/versions/` (new), `adapta/db/models.py` (`Endpoint`, new `Adapter`),
  `specs/openapi.yaml` (endpoint section + new paths), `adapta/services/adapters.py` (new),
  `adapta/api/v1/adapters.py` (new), `adapta/api/app.py` (router), `adapta/api/v1/endpoints.py:126-190`,
  `adapta/api/v1/chat.py:130-160`, `adapta/core/model_catalog.py`, `adapta/domain/errors.py`,
  `adapta/config.py`, `pyproject.toml`, `tests/test_adapter_upload.py` (new).
- **Contract impact.** API + DB.
- **Gate.** `make up` → `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → `make test-contracts`.
- **Acceptance.** The E4.1 fixture zip returns 202 `uploaded` with its sha256; a `.bin`, a zip with an
  extra member, a mismatched base and an oversized file each return a typed 4xx naming the problem; a
  `finetune` endpoint cannot be created while no adapter is `passed`.
- **Close.** CLAUDE.md API surface; consuming-the-api; Status snapshot.

### E4.3 `[BE]` CPU eval gate: task metrics through the serving path, adapter vs base (P1)
- [ ] **Context.** E4.1 deleted the GPU gate (response-only perplexity on a 4-bit bitsandbytes load, CUDA
  only). Perplexity never said whether the task improved — every task metric was `None` (audit finding 3).
  An externally trained adapter can also use a prompt format the endpoint never serves; only generating
  through the serving path measures that.
- **Depends.** E4.1. **Unblocks.** E4.4.
- **Agent.** sonnet · gate class **live** (opt-in slow test needs the 0.5B GGUF under `data/`) · serialize
  with: E4.2 (spec, migrations) · **Handoff.** must name the scorer signature, the `eval_metrics` shape,
  the rule's settings and the measured CPU seconds per row.
- **Scope.** A pure scoring module plus the eval-set contract. Out: running it in the worker (E4.4),
  LLM-as-judge, perplexity, multi-turn rows (§E6).
- **Steps.** (1) Contract: `Dataset.task` (`classify | extract | freeform`, required on upload — migration +
  spec); an eval set has 20–200 rows (typed error outside). (2) `services/eval_gate.py`:
  `score(base_model, gguf_lora_path | None, rows, task) -> TaskScore`, greedy, through the same
  chat-template render and `model_manager` load the endpoint uses (wrap only). Metrics: `classify` = label
  accuracy after strip/lower; `extract` = JSON-parse rate × mean per-key exact match; `freeform` = token F1
  vs the reference. (3) `passes(adapter, base)`: adapter ≥ base + `eval_min_improvement` (0.05) **or**
  (adapter ≥ `eval_absolute_floor` (0.8) **and** adapter ≥ base); persist both scores, the delta, the rule
  that decided and 5 sample predictions. (4) Tests: metric math and rule cases (unit); opt-in
  `tests/test_eval_gate_cpu.py` scores the E4.1 fixtures — the classification adapter passes, the control fails.
- **Files.** `specs/schemas/eval_dataset.schema.json`, `specs/openapi.yaml` (dataset upload + response),
  `migrations/versions/` (new), `adapta/db/models.py` (`Dataset`), `adapta/services/datasets.py`,
  `adapta/services/eval_gate.py` (new), `adapta/core/chat_templates.py`, `adapta/core/model_manager.py`
  (wrap only), `adapta/config.py`, `tests/test_eval_gate.py` (new), `tests/test_eval_gate_cpu.py` (new).
- **Contract impact.** Model + API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` → `make test`
  → `ADAPTA_RUN_EVAL_CPU=1 tests/test_eval_gate_cpu.py`.
- **Acceptance.** On CPU the fixture adapter passes with its accuracy and the base's both recorded; the
  control fails; an eval set of 10 rows or with no `task` is rejected with a typed error.
- **Close.** PRODUCT_DEFINITION eval-gate paragraph; learning-the-system gate section; CLAUDE.md gate
  one-liner and Workflow pillar 3 (adapter + eval set → gate); SDD_WORKFLOW pillar 3; Status snapshot.

### E4.4 `[BE+INFRA]` Adapter job on the CPU worker: convert, probe, score, decide (P1)
- [ ] **Context.** `core/adapter_conversion.py` wraps llama.cpp's official `convert_lora_to_gguf.py`, but the
  converter was vendored only into the deleted worker stage, and `--base-model-id` fetches the base config
  from the Hub, which fails air-gapped. A wrong-shape adapter surfaces only when the endpoint loads it.
- **Depends.** E4.2, E4.3. **Unblocks.** E4.5, E4.6, E2.2.
- **Agent.** sonnet · gate class **rebuild + live** · serialize with: E3.7 (`worker/main.py`,
  `services/jobs.py`, `services/maintenance.py`), E3.3b (`Dockerfile`) · **Handoff.** must name the handler,
  where base configs live, seconds per stage for the fixture.
- **Scope.** `uploaded → processing → passed | failed`, text adapters. Out: promotion (E4.5).
- **Steps.** (1) `Dockerfile` `app` stage vendors the two converter scripts at the pinned llama.cpp tag
  (torch CPU, `gguf`, `safetensors` are already in the image). (2) Pulling a catalog base also stores its
  `config.json` under `models_dir/<gguf_subdir>/hf_config/`; the converter always runs with `--base <dir>`;
  delete the `--base-model-id` and vision-staging branches. (3) Upload enqueues `{kind: "adapter", id}`;
  the handler converts (PEFT), probe-loads base + LoRA through `model_manager` with a 1-token generation
  (failure → `AdapterIncompatible`), runs E4.3's scorer for base and adapter, writes `eval_metrics` +
  status. (4) The sweeper fails adapters left `processing` by a restart. (5) Opt-in
  `tests/integration/test_adapter_import_e2e.py`: fixture zip → `passed` → endpoint → chat answers with the
  trained label; control → `failed`, endpoint refused; same project with an indexed file → citations plus
  the adapter's output shape.
- **Files.** `Dockerfile` (`app` stage), `adapta/core/adapter_conversion.py`, `adapta/core/model_manager.py`
  (wrap only), `adapta/worker/main.py`, `adapta/services/{adapters,jobs,maintenance}.py`,
  `adapta/api/v1/adapters.py`, `adapta/domain/errors.py`, `tests/integration/test_adapter_import_e2e.py` (new).
- **Contract impact.** None (statuses defined in E4.2).
- **Gate.** `make up` → `make test` → `docker compose restart worker` →
  `ADAPTA_RUN_ADAPTER_E2E=1 HF_HUB_OFFLINE=1 tests/integration/test_adapter_import_e2e.py`.
- **Acceptance.** A PEFT upload reaches `passed` with no GPU and no Hub access; the control fails with
  both scores in `eval_metrics`; killing the worker mid-job leaves no adapter `processing` after the sweep.
- **Close.** OPERATIONS (import timing, air-gapped base configs, worker restarts); architecture.md
  (adapter job); `gates.md` row (adapter import → this e2e); Status snapshot.

### E4.5 `[BE+FE]` Adapter promotion, rollback and an audit trail (P2)
- [ ] **Context.** E4.2 binds `Endpoint.adapter_id` at creation and nothing changes it; a project can hold
  several `passed` adapters but none can be compared or swapped, and nobody records who did what.
- **Depends.** E4.4. **Unblocks.** E4.7.
- **Agent.** sonnet · gate class **live** · serialize with: E2.2 (`endpoints.py`, `EndpointPanel.svelte`),
  E4.6 and E5.2 (`EndpointPanel.svelte`) · **Handoff.** must name the migration revision, the promote route,
  the eviction wrapper.
- **Scope.** List passed adapters with scores; promote one; rollback = promote the previous; every change
  logged. Out: A/B traffic split, shadow mode.
- **Steps.** (1) Migration `adapter_events(id, endpoint_id, adapter_id, action promote|rollback,
  actor_user_id, created_at)`. (2) Spec: `POST /v1/projects/{id}/endpoint/promote {adapter_id}` (writer;
  adapter must be `passed`), `GET /v1/projects/{id}/endpoint/history`. (3) `endpoints.py`: promote swaps
  `adapter_id`, evicts the old `(base, adapter)` cache entry, writes the event. (4) Console
  `EndpointPanel.svelte`: adapters table (task metric vs base, date, Promote), history, current badge.
  (5) Tests: promote/rollback state machine; viewer 403; eviction called.
- **Files.** `migrations/versions/` (new), `adapta/db/models.py`, `specs/openapi.yaml` (endpoint section),
  `adapta/api/v1/endpoints.py`, `adapta/core/model_manager.py` (an `evict(key)` wrapper if absent),
  `adapta/console/src/views/EndpointPanel.svelte`, `tests/test_adapter_upload.py`,
  `tests/integration/test_c_phase_rbac.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` → `make test`
  → `make test-contracts` → `make console-build`.
- **Acceptance.** Promoting a second passed adapter changes what the endpoint serves without a restart;
  rollback restores the first; history shows actor and scores; a failed adapter cannot be promoted (400).
- **Close.** operator-console endpoint section, consuming-the-api, PRODUCT_DEFINITION serving paragraph,
  CLAUDE.md API surface; Status snapshot.

### E4.6 `[FE]` Console: "change how it behaves" becomes eval set → import → verify → serve (P1)
- [ ] **Context.** After E4.1 `FinetuneFlow.svelte` only uploads and reviews datasets; nothing imports an
  adapter or shows why one passed or failed.
- **Depends.** E4.4. **Unblocks.** E4.7.
- **Agent.** sonnet · gate class **live** (+ `make console-build`) · serialize with: E4.5
  (`EndpointPanel.svelte`), E4.8 and E4.9 (the same view) · **Handoff.** must name the view and the
  refreshed screenshot paths.
- **Scope.** Four steps in the existing project view: (1) eval set — upload or synthesize, pick the task;
  (2) adapter — drop a `.gguf` or `.zip`; (3) verification — live status, then the task metric vs base, the
  deciding rule and sample predictions, or the typed failure reason; (4) create the endpoint. A short "where
  do I train it?" box links the E4.7 guide. Out: anything that trains.
- **Steps.** Rename the view `AdapterFlow.svelte` and rebuild it on the E4.2/E4.3 types; poll
  `GET …/adapters/{aid}` while `processing`; the Models page shows the accepted base ids and aliases per
  catalog entry; `make screenshots` refreshes the console captures.
- **Files.** `adapta/console/src/views/FinetuneFlow.svelte` → `AdapterFlow.svelte`,
  `adapta/console/src/views/{Project,Models}.svelte`, `adapta/console/src/lib/{api,types}.ts`,
  `docs/screenshots/`.
- **Contract impact.** None.
- **Gate.** `make console-build` → live walk-through importing the E4.1 fixture.
- **Acceptance.** An operator imports the fixture and serves it without leaving the console; the control
  shows its failure reason with both measured scores.
- **Close.** operator-console (behaviour section rewritten); Status snapshot.

### E4.7 `[DOCS]` Import guide and pitch: "bring your own adapter" wherever training was claimed (P1)
- [ ] **Context.** README, PRODUCT_DEFINITION, BRAND, COMPETITIVE_LANDSCAPE, knowledge-and-behavior,
  learning-the-system and concepts still describe in-product QLoRA; E4.1 deleted the training-only pages.
- **Depends.** E4.4, E4.5, E4.6. **Unblocks.** E2.3.
- **Agent.** sonnet · gate class **offline** (`make docs-build`) · serialize with: E2.3 (README) ·
  **Handoff.** must name the new page path.
- **Scope.** One new page `docs/user-guide/bring-your-own-adapter.md`: what Adapta expects (catalog base and
  accepted aliases, the base's own chat template — ChatML for Qwen2.5 — response-only loss recommended,
  accepted formats), the eval-set format and how to pick the task, how the gate decides, one worked command
  sequence each for Unsloth and TRL (commands in the page, no scripts in the repo). Then rewrite the pitch
  surfaces. Out: any claim E4.4's e2e did not prove.
- **Steps.** (1) The page + `mkdocs.yml` nav. (2) README pitch + "change how it behaves" bullet;
  PRODUCT_DEFINITION Service B; CLAUDE.md "What this project is"; BRAND; COMPETITIVE_LANDSCAPE (Unsloth
  and Axolotl move from competitors to upstream tools); knowledge-and-behavior "when to use which" (prompt
  → JSON mode → adapter); learning-the-system; concepts.
- **Files.** `docs/user-guide/bring-your-own-adapter.md` (new), `mkdocs.yml`, `README.md`, `CLAUDE.md`,
  `docs/reference/{PRODUCT_DEFINITION,BRAND,COMPETITIVE_LANDSCAPE}.md`,
  `docs/user-guide/{index,knowledge-and-behavior}.md`, `docs/developer-guide/learning-the-system.md`,
  `docs/concepts/{index,stack}.md`, `docs/index.md`.
- **Contract impact.** None.
- **Gate.** `make docs-build` (host, `--strict`).
- **Acceptance.** `grep -rniE 'qlora|train(s|ing)? (a|the|your) (model|adapter)|training job' README.md CLAUDE.md docs/`
  hits only the guide's "train it elsewhere" section; the guide is in nav.
- **Close.** Self-contained; Status snapshot.

### E4.8 `[BE+FE]` Synthesis re-aimed: RAG eval sets and adapter eval sets, optional teacher (P2)
- [ ] **Context.** The synthesis prompt asks for "comprehension" Q/A "based solely on the passage"
  (`synthesis.py:34-48`) — fact pairs; the generator is the same small model; dedup is exact-string
  (`:154-157`). After E4.1 its output can no longer train anything, but both gates need eval sets.
- **Depends.** E3.8, E4.1. **Unblocks.** E5.2.
- **Agent.** sonnet · gate class **live** · serialize with: E4.6 (console view), E5.1 (`synthesis.py`
  helper) · **Handoff.** must name the `Dataset.kind` values and that `rag_eval` rows equal E3.8's format.
- **Scope.** Two modes plus an optional stronger generator. Out: quality scoring beyond parse + dedup.
- **Steps.** (1) Spec `SynthesizeRequest.mode: "rag_eval" | "behavior"` (default `rag_eval`),
  `style_instructions` (for `behavior`), optional `teacher_base_url` / `teacher_model` (any
  OpenAI-compatible endpoint). (2) `rag_eval` writes `{question, answer, source_chunk_id}` rows in the
  E3.8/E5.2 golden format, `Dataset.kind = rag_eval` (migration `dataset_kind`). (3) `behavior` writes
  `{prompt, response}` rows whose *shape* varies while facts are quoted from the chunk — usable as an E4.3
  eval set, or downloaded (`GET …/datasets/{did}/download`, JSONL) to train an adapter elsewhere.
  (4) Near-duplicate filter with the embedding service (cosine > 0.92 dropped). (5) Console: mode radio with
  one guidance line each. (6) Tests: parsing per mode; dedup; download.
- **Files.** `specs/openapi.yaml` (`SynthesizeRequest`, `DatasetResponse.kind`, download path),
  `migrations/versions/` (new), `adapta/services/synthesis.py`, `adapta/api/v1/{synthesis,datasets}.py`,
  `adapta/db/models.py`, `adapta/console/src/views/FinetuneFlow.svelte` (synthesis section),
  `tests/test_synthesis_helpers.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → `make test-contracts`.
- **Acceptance.** `rag_eval` output loads into the E3.8 harness unchanged; a `behavior` set uploads as an
  E4.3 eval set and downloads as JSONL; the console default is `rag_eval`.
- **Close.** knowledge-and-behavior, operator-console; Status snapshot.

### E4.9 `[BE]` JSON mode on the endpoint — try it before importing an extraction adapter (P2)
- [ ] **Context.** Extraction is the most common adapter task, yet llama.cpp's grammar-constrained decoding
  (`response_format` `json_object` / `json_schema`) is not exposed. The console should say "try JSON mode
  first".
- **Depends.** E1.11. **Unblocks.** none.
- **Agent.** sonnet · gate class **live** (`test_inference_slow` needs the GGUF under `data/`) · serialize
  with: E3.5/E5.3 (`chat.py`), E2.1 (`core/backends/`), E4.6 (console view) · **Handoff.** must name the
  kwarg forwarded and which backends honour it.
- **Scope.** Pass-through of `response_format` to `create_chat_completion` (a call argument, not an engine
  change); Ollama (E2.1) forwards the same field. Out: validating output beyond the grammar.
- **Steps.** (1) Spec `ChatCompletionRequest.response_format` (OpenAI shape). (2) `inference.py`
  `generate_chat`: forward it in kwargs (wrap only). (3) Backends forward as-is. (4) Playground "JSON"
  toggle; the console's extraction task copy: "Try JSON mode on the base model first — import an adapter
  if the fields are still wrong". (5) Tests: request model accepts it; `test_inference_slow.py` asserts
  parseable JSON.
- **Files.** `specs/openapi.yaml` (`ChatCompletionRequest`), `adapta/services/chat.py`,
  `adapta/core/inference.py:183-230` (kwargs only), `adapta/core/backends/*.py`,
  `adapta/console/src/views/Playground.svelte`, the console adapter view, `tests/test_inference_slow.py`.
- **Contract impact.** API.
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `tests/test_inference_slow.py` (local GGUF).
- **Acceptance.** `response_format: {type: json_object}` yields parseable JSON on the base model; the
  console points extraction users to it first.
- **Close.** consuming-the-api; knowledge-and-behavior "when to use which" extraction row; Status snapshot.

### E5. Differentiation (weeks 10–13)

### E5.1 `[BE]` Contextual retrieval at index time, opt-in per project (P2)
- [ ] **Context.** Anthropic's contextual retrieval (prepend an LLM-written situating sentence to each
  chunk before embedding and full-text indexing) cut top-20 retrieval failures by 49 % (67 % with
  reranking). No open-source platform in the 2026-09 scan ships it. Adapta's generator is local, so it
  costs minutes, not API dollars.
- **Depends.** E3.1, E3.7, E3.8. **Unblocks.** none.
- **Agent.** sonnet · gate class **live (`make golden` before/after)** · serialize with: E5.2
  (`worker/main.py`), E4.8 (`synthesis.py`) · **Handoff.** must name the recall@5 delta and the flag
  name.
- **Scope.** Per-project flag; the sentence is generated by the project's base model (or the E4.8
  teacher) and stored in `chunks.context`; embeddings and `tsv` cover `context + text`; citations still
  show the raw `text`. Out: on by default (CPU latency), late chunking.
- **Steps.** (1) Migration `0015_chunk_context`: `chunks.context TEXT NULL`; `tsv` regenerated over
  `coalesce(context,'') || ' ' || text`; `projects.contextual_retrieval BOOL DEFAULT false` + spec
  field. (2) Index job (E3.7): when enabled, one prompt per chunk with the whole document (or the page
  window when it exceeds the context) → ≤ 60-token sentence; batched on the worker; timed. (3)
  `retrieve` unchanged. (4) `make golden` before/after on the E3.8 set — that delta is the launch
  number.
- **Files.** `migrations/versions/0015_chunk_context.py`, `adapta/db/models.py`, `specs/openapi.yaml`
  (project fields), `adapta/worker/main.py` (`_run_index_job`), `adapta/services/rag.py:150-195`,
  `adapta/services/synthesis.py` (reuse its chat-call helper), `tests/integration/test_rag_golden.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → `make golden` (before/after).
- **Acceptance.** The recall@5 delta is in the Done note and in concepts/stack.md; indexing time per
  page is in OPERATIONS; the flag is off by default.
- **Close.** concepts/stack.md, knowledge-and-behavior (one paragraph + when to enable), OPERATIONS
  timing, README bullet only if the delta earns a claim; Status snapshot.

### E5.2 `[BE+FE]` RAG gate: per-project golden set, recall@k on the endpoint dashboard, regression warning (P2)
- [ ] **Context.** The eval gate is the brand ("nothing unverified serves"); RAG has no equivalent — a
  config or model change can silently degrade retrieval. E3.8 gives the harness and E4.8 `rag_eval`
  generates a per-project set.
- **Depends.** E3.8, E3.7, E4.8. **Unblocks.** none.
- **Agent.** sonnet · gate class **live** · serialize with: E5.1 (`worker/main.py`), E4.5
  (`EndpointPanel.svelte`) · **Handoff.** must name the `rag_eval` job kind and the summary fields.
- **Scope.** Store a golden set per project; compute recall@5/MRR on demand and after every re-index;
  show it on the endpoint Overview; **warn** on regression (blocking is a later decision once users
  ask). Out: LLM-judge faithfulness.
- **Steps.** (1) Spec: `POST /v1/projects/{id}/golden` (JSONL upload or an `eval` dataset id),
  `POST /v1/projects/{id}/golden/run` (202 → worker job `kind: "rag_eval"`),
  `GET /v1/projects/{id}/golden/results`. Migration `0016_rag_eval_runs`. (2) The job runs
  `retrieve()` per question and stores metrics + per-question hits. (3) `RetrievalSummary` += latest
  recall@5, MRR, run date, delta vs previous; Overview shows a "Retrieval quality" tile with a warning
  chip when delta < −0.05. (4) Auto-run after any index job when a golden set exists. (5) Tests:
  metric math; job dispatch; summary fields.
- **Files.** `specs/openapi.yaml`, `migrations/versions/0016_rag_eval_runs.py`, `adapta/db/models.py`,
  new `adapta/api/v1/golden.py` + `adapta/services/golden.py`, `adapta/worker/main.py`,
  `adapta/services/project_summary.py`, `adapta/console/src/views/Overview.svelte`,
  `adapta/console/src/views/EndpointPanel.svelte`, `tests/test_provenance.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → `make test-contracts` → `make console-build`.
- **Acceptance.** Uploading a 20-question set and re-indexing produces a recall@5 tile; setting
  `rag_top_k` to 1 triggers the regression chip on the next run.
- **Close.** PRODUCT_DEFINITION (RAG-gate paragraph mirroring the fine-tune gate), operator-console
  overview, CLAUDE.md API surface; Status snapshot.

### E5.3 `[BE]` History-aware retrieval: condense the conversation into a standalone query (P2)
- [ ] **Context.** Retrieval embeds only the last user message (`chat.py:293`, `:481`); "and the second
  one?" retrieves on that string. Multi-query/HyDE were deliberately deferred; condensation is the
  cheap half.
- **Depends.** E3.2, E3.5, E3.8. **Unblocks.** none.
- **Agent.** sonnet · gate class **live (`make golden`)** · serialize with: E4.9/E3.5 (`chat.py`) ·
  **Handoff.** must name the `retrieve(queries)` signature.
- **Scope.** With ≥ 2 user turns and RAG active, ask the served model for a one-line standalone
  question (≤ 40 tokens, greedy) and retrieve on it **and** the original — both go into RRF; never
  drop the original. Opt-out `adapta.condense: false`. Out: multi-query expansion.
- **Steps.** (1) `chat.py` `_condense_query(messages)` on the same backend handle (metered, logged).
  (2) `rag.py` `retrieve(queries: list[str])`: vector + FTS per query, one RRF over all lists.
  (3) Condensation + retrieval share the existing 10 s guard. (4) Tests: single-turn skips it;
  two-turn calls it once; fusion includes the original.
- **Files.** `adapta/services/chat.py:280-300, 470-490`, `adapta/services/rag.py:196-277`,
  `tests/test_context_fit.py`, `tests/test_rag_hybrid.py`, `docs/user-guide/consuming-the-api.md`.
- **Contract impact.** API (`adapta.condense`, extends E3.5's namespace).
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `make golden` (add 5 two-turn questions to the set).
- **Acceptance.** The two-turn golden questions gain recall; single-turn latency unchanged; usage
  counts the condensation tokens.
- **Close.** consuming-the-api; knowledge-and-behavior retrieval box; Status snapshot.

### E5.4 `[BE+FE]` Visual extraction in ingestion: the vision base fills structured metadata and re-reads low-confidence pages (P2)
- [ ] **Context.** After E3.3b scanned invoices index with page text and OCR confidence; after E3.4 the
  operator sees `needs_review` pages. The catalog's vision base already reads images through the serving
  path (`services/chat.py` `_chat_vision`), and ingestion never uses it. On CPU it takes ≈ 40 s per image
  (llama.cpp issue #17801), so it runs only on the pages that need it, as a queued job.
- **Depends.** E3.3b, E3.4, E3.5, E3.7. **Unblocks.** none.
- **Agent.** sonnet · gate class **live** · serialize with: E5.1/E5.2 (`worker/main.py`), E3.4
  (`RagFlow.svelte`) · **Handoff.** must name the `fields` header format and the measured s/page.
- **Scope.** A queued `kind: "extract"` job: for a file's `needs_review` pages (all pages on request), run
  the Apache vision base with a project-defined JSON-schema prompt → `chunks.fields JSONB`; replace the page
  text when OCR confidence was below threshold and the output is non-empty; clear `needs_review`. Fields
  are filterable through E3.5's `adapta.filters` and injected as a one-line header in the chunk. Out:
  vision adapters (§E6), bbox UI, human approval queue, aggregations (offer a CSV of `fields`).
- **Steps.** (1) Migration `chunk_fields`: `chunks.fields JSONB NULL`, `projects.extraction_schema JSONB
  NULL`. Spec: the project field, `POST /v1/projects/{id}/files/{fid}/extract` (202),
  `GET /v1/projects/{id}/fields.csv`. (2) Worker handler `extract` in the dispatch table: loads the vision
  base through `model_manager` (wrap only) and the same image content-part path as `_chat_vision`; prompt =
  schema + "return JSON only"; parse with the synthesis helper. (3) `rag.py`: header
  `"Invoice · {vendor} · {date} · {total}"` when `fields` is present; filters on `fields ->> key`.
  (4) Console: file-row action "Extract fields" with the per-page time estimate, fields drawer, CSV
  download. (5) Tests: parser + header; dispatch; RBAC.
- **Files.** `migrations/versions/` (new), `specs/openapi.yaml`, `adapta/worker/main.py`,
  `adapta/services/chat.py` (`_chat_vision`, reuse), `adapta/core/model_manager.py` (wrap only),
  `adapta/services/rag.py`, `adapta/api/v1/files.py`, `adapta/console/src/views/RagFlow.svelte`,
  `tests/test_rag_hybrid.py`, `tests/integration/test_rag_e2e.py` (one opt-in extraction on the scanned fixture).
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → `ADAPTA_RUN_EXTRACT=1 tests/integration/test_rag_e2e.py`.
- **Acceptance.** An invoice PNG indexed with low OCR confidence gets `fields = {vendor, total, …}`,
  `needs_review` clears, a filtered question ("Qorvex invoices") cites only those files, the CSV lists
  them, and s/page is recorded in OPERATIONS.
- **Close.** knowledge-and-behavior (scanned documents), PRODUCT_DEFINITION Service A (bounded:
  extraction, not analytics), OPERATIONS timing, CLAUDE.md API surface; Status snapshot.

### E6. Deferred — recorded, not promised (open a block only when a user asks)
- Guardrails (LLM Guard) · connectors beyond folder/S3 sync · Helm · OIDC · GraphRAG/RAPTOR · ColPali ·
  Grafana dashboards (G4) · rate limiting on `/v1/chat/completions` (G3) · audit
  log/soft-delete (§7.5) · document-level ACL (needs E3.1: `chunks.principals` + a mandatory filter) ·
  Qwen3 family onboarding (new conversion spike).
- Adapter import, later scope (§E4 shipped text-only): vision (VLM) adapters — conversion with the
  mmproj and image eval sets · multi-turn eval rows · LLM-as-judge for `freeform` eval sets · in-product
  training, only if a paying user cannot train elsewhere.


Carried over when the shipped sections moved to the changelog (2026-10-08):
- Multimodal RAG (CLIP image *retrieval* — distinct from §V image *understanding*) · hosted/multi-tenant SaaS
  edition · heavy MLOps (MLflow, DVC) · additional API protocols (Anthropic/MCP/Responses) · license/packaging
  decision (open-core vs commercial self-hosted).
- Soft-delete + audit log (formerly §7.5): `deleted_at` on projects, an `audit_log` table, admin-only permanent
  delete. Data-safety, not a security boundary; evaluate when multi-admin deployments appear.
- Coverage ratchet (formerly §1.2): the global floor stays at 30 % until a model-bearing CI job runs the opt-in
  suites (`chat.py`, `rag.py`, `embeddings.py` are exercised only by the RAG e2e + slow tests).
- Adapta as an assistant inside Tack: [docs/adr/0001-adapta-as-tack-assistant.md](docs/adr/0001-adapta-as-tack-assistant.md)
  (status: proposed; no block opened).
---

## Definition of done (per task)

A task is done only when: (1) its contract changed first if it touches API/schema/model; (2) the relevant gate is **green in CI**, not just locally; (3) no `detail=str(e)` reintroduced; (4) generated artifacts regenerated, not hand-edited; (5) docs updated in the same PR.

---
