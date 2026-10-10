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

## Status snapshot (updated 2026-10-10, §E complete)

| Area | State |
|---|---|
| Product build (phases 0–5), operator console, image fine-tunes, brand, positioning | ✅ complete — history in [CHANGELOG.md](CHANGELOG.md) |
| Fine-tuning direction | **Decided 2026-10-09: bring your own adapter (§E4).** Training removed 2026-10-10 (E4.1); no service needs a GPU. Shipped end to end 2026-10-10: import (E4.2), CPU gate (E4.3/E4.4), promote/rollback (E4.5), console flow (E4.6), eval-set synthesis (E4.8). Pitch + import guide: E4.7. |
| SDD gates | Pillar 2 ✅ `make migrate-test` · Pillar 3: the GPU perplexity gate is replaced by the CPU task-metric gate on imported adapters (E4.3/E4.4) · Pillar 1 ✅ `make test-contracts` green (E1.11; re-run 2026-10-10 after E4.8: 40 operations, 2320 cases, 0 failures, authenticated) |
| CI fast gate (`make ci`) | ✅ green 2026-10-10 after E1.15: ruff + mypy clean, 350 unit tests |
| **Audit 2026-09-03 (§E)** | ✅ **all 39 blocks closed 2026-10-10** (E1.15 added after a live Chroma hang + socket leak). Bring-your-own-adapter end to end (import → CPU gate → promote/rollback, console, Ollama export); hybrid + multilingual retrieval (golden 0.978) with a per-project RAG gate, deterministic abstention, filters, citations with page/OCR; Docling + OCR ingestion on a queued worker, opt-in visual extraction; optional Ollama backend; JSON mode. Opt-ins measured honestly: contextual retrieval and history condensation showed no gain on the golden corpus. Open follow-ups live in each block's CHANGELOG entry. Next: no §E block is open; the highest-value follow-ups are the `"null"` field-string bug (E5.4), measuring the 7B vision default, multi-turn golden questions (E5.3), running `migrate-test` against a scratch DB (E2.3), and a long-document corpus for contextual retrieval (E5.1). |
| **Post-audit follow-ups (§F)** | Opened 2026-10-10: 9 blocks from the §E Follow-up lines — 5 correctness (extraction `"null"`, migrate-test wipes the dev DB, freeform gate passes garbage, non-deterministic retrieval, teacher-URL SSRF), 3 hygiene, 1 measurement (condensation default). Wave 1: F1.1, F1.2, F1.5. |

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
| E1.15 | 3 | sonnet | live | none | E3.5 (`rag.py`), E5.1 (`rag.py`, `worker/main.py`) | done 2026-10-10 |
| E1.10 | 0 | sonnet | rebuild (app image only) | none | E3.3b, E4.1 | done 2026-10-09 |
| E1.11 | 0 | sonnet | live | E1.10 | any in-flight `specs/openapi.yaml` edit | done 2026-10-09 |
| E2.1 | 1 | sonnet | live | none | E4.1, E4.9 (`core/backends/`) | done 2026-10-10 |
| E3.1 | 1 | sonnet | live | none | E3.7, E3.2 | done 2026-10-09 |
| E3.3a | 1 | sonnet + human decision | offline | none | — | done 2026-10-10 |
| E3.8 | 1 | sonnet | live | none — must land before E3.2 | — | done 2026-10-09 |
| E4.1 | 1 | sonnet | rebuild + live (exclusive) | E1.11 | E2.1, E3.3b, E3.7 | done 2026-10-10 |
| E3.2 | 2 | sonnet | live | E3.1, E3.8 (baseline recorded before this lands) | E3.7, E3.5 | done 2026-10-10 |
| E3.3b | 2 | sonnet | rebuild + live | E3.3a (commit), E3.1 | E4.1, E4.2, E4.4 (`pyproject.toml`, `Dockerfile`), E3.7, E3.4 | done 2026-10-10 |
| E3.7 | 2 | sonnet | live | E3.1, E4.1 | E3.1/E3.3b, E4.4 (`worker/main.py`) | done 2026-10-10 |
| E4.2 | 2 | sonnet | live | E4.1 | E4.3 (spec, migrations), E4.5, E2.2 | done 2026-10-10 |
| E4.3 | 2 | sonnet | live | E4.1 | E4.2 (spec, migrations) | done 2026-10-10 |
| E4.8 | 2 | sonnet | live | E3.8, E4.1 | E4.6, E5.1 | done 2026-10-10 |
| E4.9 | 2 | sonnet | live | E1.11 | E2.1, E3.5/E5.3, E4.6 | done 2026-10-10 |
| E3.4 | 3 | sonnet | live | E3.1, E3.3b, E1.11 | E3.5 (spec, `Playground.svelte`), E3.3b | done 2026-10-10 |
| E3.5 | 3 | sonnet | live | E3.2, E1.11 | E3.4 (spec, `Playground.svelte`), E4.9 and E5.3 | done 2026-10-10 |
| E3.6 | 3 | sonnet + human decision | live | E3.1, E3.2, E3.8 | E3.2 | done 2026-10-10 |
| E4.4 | 3 | sonnet | rebuild + live | E4.2, E4.3 | E3.7, E3.3b | done 2026-10-10 |
| E5.1 | 3 | sonnet | live | E3.1, E3.7, E3.8 | E5.2, E4.8 | done 2026-10-10 |
| E5.2 | 3 | sonnet | live | E3.8, E3.7, E4.8 | E5.1, E4.5 | done 2026-10-10 |
| E2.2 | 4 | sonnet | live | E2.1, E4.4 | E4.5 (`endpoints.py`, `EndpointPanel.svelte`) | done 2026-10-10 |
| E4.5 | 4 | sonnet | live | E4.4 | E2.2, E4.6, E5.2 | done 2026-10-10 |
| E4.6 | 4 | sonnet | live | E4.4 | E4.5, E4.8, E4.9 | done 2026-10-10 |
| E5.3 | 4 | sonnet | live | E3.2, E3.5, E3.8 | E4.9/E3.5 | done 2026-10-10 |
| E5.4 | 4 | sonnet | live | E3.3b, E3.4, E3.5, E3.7 | E5.1/E5.2, E3.4 | done 2026-10-10 |
| E4.7 | 5 | sonnet | offline | E4.4, E4.5, E4.6 | E2.3 (README) | done 2026-10-10 |
| E2.3 | 6 | haiku | offline | E1.11, E4.7 | E3.2, E3.3b, E4.7 (README) | done 2026-10-10 |

### E1. P0 — corrections that change the publishable evidence (weeks 1–2)

E1.1–E1.9 shipped 2026-09-17 → [CHANGELOG.md](CHANGELOG.md). E1.14 closed 2026-10-08, E1.10 and E1.11 on 2026-10-09 — wave 0 is done.

### E2. Distribution + launch kit (weeks 2–3)

### E3. P1 — real hybrid RAG + scanned documents (weeks 3–7)

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

### E5. Differentiation (weeks 10–13)

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

## F. Post-audit follow-ups — bugs and debts the §E live gates surfaced (opened 2026-10-10)

> **Source.** The **Follow-up.** lines of the §E blocks in [CHANGELOG.md](CHANGELOG.md) (2026-10-08 → 2026-10-10).
> Admitted under the §E scope guard: each block fixes something false or broken today, removes dead code, or
> measures a default that was shipped without evidence. Not admitted (stay as CHANGELOG follow-ups until a user
> asks): schemathesis stateful links, worker `/metrics`, per-chunk fields drawer, per-adapter Ollama export,
> language-aware FTS, a long-document corpus for contextual retrieval (opt-in, off by default).
> **Needs the user, not an agent:** measuring the `qwen2.5-vl-7b-instruct` extraction default (multi-GB download;
> see [OPERATIONS.md](docs/reference/OPERATIONS.md)).
>
> Same rules as §E: read only your block and its **Files**; anchors are symbols; close with **Done.** + **Handoff.**,
> move the block to CHANGELOG.md, flip the board row. Migration revisions are nominal (`0022_…`): take the next free one.

#### §F board

| Block | Wave | Tier | Gate class | Depends on | Serialize with | Status |
|---|---|---|---|---|---|---|
| F1.1 | 1 | sonnet | offline | none | F2.2 (`worker/main.py`) | done 2026-10-10 |
| F1.2 | 1 | sonnet | live | none | F2.1 (migrations) | done 2026-10-10 |
| F1.5 | 1 | haiku | offline | none | — | done 2026-10-10 |
| F2.2 | 2 | haiku | offline | F1.1 | F1.1 (`worker/main.py`) | in progress (worker-f2.2) |
| F2.3 | 2 | haiku | offline | none | — | done-pending-merge (f2.3) |
| F1.4 | 2 | sonnet | live | none | F2.1, F3.1 (`rag.py`) | in progress (worker-f1.4) |
| F2.1 | 3 | sonnet | live | F1.2 | F1.4, F3.1 (`rag.py`, `chat.py`) | open |
| F1.3 | 3 | sonnet + human decision | live | none | — | open |
| F3.1 | 3 | sonnet + human decision | live | F1.4 | F1.4, F2.1 (`chat.py`, golden harness) | open |

### F1. Correctness

### F1.3 [BE] The eval gate passes a garbage adapter on `freeform` eval sets
- **Context.** E4.4 live: scored as `freeform` (token F1), the `garbage-control` fixture **passed** (0.383 vs base
  0.037) — it reproduces template words F1 rewards. The gate is the product's differentiator; today it only holds for
  `classify`/`extract`.
- **Scope.** Measure, then stop for a decision. Candidates to measure on both fixtures (`classify-pass`,
  `garbage-control`) and the 0.5B base: (a) `freeform` is not gateable — import of an adapter whose eval set is
  freeform ends `failed` with reason "freeform eval sets cannot gate; use classify or extract"; (b) a minimum absolute
  score + minimum delta for freeform; (c) exact-match share as a second freeform metric. LLM-as-judge stays deferred (§E6).
- **Steps.** (1) Reproduce the E4.4 numbers with the fixtures. (2) Compute each candidate on both fixtures without
  changing the gate. (3) Report a table and stop. (4) After the user picks: implement, update the import guide.
- **Files.** `adapta/services/eval_gate.py`, `tests/test_eval_gate*.py`, `tests/integration/test_adapter_import_e2e.py`,
  `docs/user-guide/bring-your-own-adapter.md`.
- **Contract impact.** Pillar 3 (gate rule); API only if a new failure reason enum is added (spec first).
- **Gate.** live: `ADAPTA_RUN_ADAPTER_E2E=1 HF_HUB_OFFLINE=1 pytest -m integration tests/integration/test_adapter_import_e2e.py`
  + `ADAPTA_RUN_EVAL_CPU=1 pytest -o addopts="" tests/test_eval_gate_cpu.py`.
- **Acceptance.** Under the chosen rule `garbage-control` fails on every task type and `classify-pass` still passes.
- **Close.** bring-your-own-adapter.md (what freeform sets prove); CHANGELOG.
- **Depends.** none.
- **Agent.** sonnet + human decision · live · stop after the measurement table · Handoff names the rule and threshold.

### F1.4 [BE] Retrieval is not deterministic across identically built projects
- **Context.** E3.5 live: the same question on two projects built from the same files scored a top cosine of 0.45 in
  one run and 0.29 in another. Golden recall is stable (0.978) but single questions flip, so per-project gates (E5.2)
  and abstention (`rag_min_score`) can change verdicts without any input change.
- **Scope.** Find the source (candidates: RRF ties broken by random chunk ids in `_rrf_fuse`; HNSW build randomness in
  Chroma; FTS ordering without a tie-break) and remove what is ours to remove. If HNSW is the cause, document it and
  make the fused order stable given identical candidate sets.
- **Steps.** (1) Build the golden project twice; diff per-question top-5 and scores. (2) Add a stable secondary key
  (e.g. content sha256, then chunk_index) wherever ranks tie; order FTS by `(rank desc, stable key)`. (3) Re-measure.
- **Files.** `adapta/services/rag.py` (`_rrf_fuse`, the FTS query, `retrieve`), `tests/test_rag_hybrid.py`,
  `tests/integration/test_rag_golden.py` (only for a determinism check helper).
- **Contract impact.** None.
- **Gate.** live: `make golden` twice on fresh projects → identical per-question top-5; recall@5 ≥ 0.97 floor.
- **Acceptance.** Two fresh builds of the golden project return identical top-5 for all 45 questions (or the residual
  difference is attributed to HNSW with evidence and documented).
- **Close.** knowledge-and-behavior.md retrieval box only if behaviour visible to users changed; CHANGELOG.
- **Depends.** none. Unblocks F3.1 (a stable baseline).
- **Agent.** sonnet · live · serialize with F2.1, F3.1 · Handoff names the tie-break key and the measured diff count.

### F2. Hygiene

### F2.1 [BE] Dead code and stored counters left behind by E3.1/E3.2
- **Context.** Chunk counts are computed from `chunks` since E3.2, yet `ProjectFile.num_chunks` / the collection
  counter are still stored and `services/project_summary.py` still sums `ProjectFile.num_chunks`.
  `rag.all_chunks_known` has no production caller. `chat.py` reads `handle.usage` via `getattr` only because a test fake
  lacks the attribute.
- **Scope.** Remove, don't redesign. `RAGService.retrieve` swallowing `get_collection` errors is in scope only as a
  log line at warning level (behaviour unchanged).
- **Steps.** (1) `project_summary.py` → `count_project_chunks`. (2) Drop the stored count columns that nothing reads
  (autogenerate the migration, review it). (3) Delete `all_chunks_known` + its test. (4) Fake gets `usage = None`;
  drop the `getattr`. (5) Warning log in `retrieve`.
- **Files.** `adapta/services/project_summary.py`, `adapta/db/models.py`, `migrations/versions/0022_drop_chunk_counters.py`,
  `adapta/services/rag.py`, `adapta/services/chat.py`, `tests/test_rag_hybrid.py`, the chat test fake.
- **Contract impact.** Pillar 2 (migration); API only if a response field disappears (it must not — counts stay, computed).
- **Gate.** live: `make migrate` + `make migrate-test` (scratch DB after F1.2), `make ci`, `tests/integration/test_rag_e2e.py`.
- **Acceptance.** Project summaries report the same chunk counts as before on the golden project; no reader of the
  dropped columns remains (`git grep`).
- **Close.** CHANGELOG.
- **Depends.** F1.2.
- **Agent.** sonnet · live · serialize with F1.4, F3.1 · Handoff names the migration revision.

### F2.2 [BE] Finished job keys never expire; the Ollama backend can leak its HTTP client
- **Context.** `adapta:job:*` hashes in Redis are kept forever after a job finishes (E3.7). `ollama_backend` creates an
  `httpx.AsyncClient` in `prepare()` that is not closed when generation never runs (E1.15 follow-up 4).
- **Scope.** A TTL on terminal job states (7 days, one constant/setting) and closing the client on every path.
- **Files.** `adapta/services/jobs.py`, `adapta/worker/main.py` (only where a job reaches a terminal state),
  `adapta/core/backends/ollama_backend.py`, `tests/test_jobs*.py`, `tests/test_ollama_backend*.py`.
- **Contract impact.** None.
- **Gate.** offline: `make test`, `make ci` rungs.
- **Acceptance.** A job set to `completed`/`failed` has a TTL ≤ 7 days; a `prepare()` followed by no generation closes
  the client (test asserts `aclose` called).
- **Close.** OPERATIONS.md (job retention, one line); CHANGELOG.
- **Depends.** F1.1 (same file).
- **Agent.** haiku · offline · Handoff names the TTL constant.

### F2.3 [FE] Console warnings and training-era proof assets
- **Context.** `svelte-check` reports 4 warnings in `RagFlow.svelte` (E5.4). `e2e/usecase-proof.spec.ts`,
  `e2e/vision-proof.spec.ts` and `docs/screenshots/usecase-proof/`, `vision-proof/` were recorded for the training
  era (E4.1 follow-up 2).
- **Scope.** Zero svelte-check warnings. Delete proof specs/screenshots that exercise training; keep any that only
  exercise surviving features (check what each spec drives) and any screenshot a doc page references.
- **Files.** `adapta/console/src/**/RagFlow.svelte`, `e2e/usecase-proof.spec.ts`, `e2e/vision-proof.spec.ts`,
  `docs/screenshots/usecase-proof/`, `docs/screenshots/vision-proof/`.
- **Contract impact.** None.
- **Gate.** offline: `npm run check` (0 errors, 0 warnings) + `make console-build` in the worktree; `git grep` shows no doc
  links to deleted assets; `make docs-build` if any doc changed.
- **Acceptance.** As in Gate.
- **Close.** CHANGELOG.
- **Depends.** none.
- **Agent.** haiku · offline · Handoff lists the deleted files.

### F3. Measure what shipped on by default

### F3.1 [TEST] Multi-turn golden questions — does history condensation earn its default?
- **Context.** E5.3 ships follow-up condensation **on by default** (+1–1.7 s and ~150 prompt tokens per follow-up turn
  on CPU) with no measured recall gain: the golden set has no multi-turn questions, so the gain cannot be seen.
- **Scope.** Add ~10 bilingual follow-up questions (`history` + `q` + `expected_file`) to the golden fixtures, a harness
  path that runs them through `_retrieval_queries`, and measure recall@5 with condensation on vs off. Then stop for a
  decision on the default.
- **Files.** `tests/fixtures/golden/questions.jsonl` (or a sibling `followups.jsonl`), `tests/integration/test_rag_golden.py`,
  `adapta/services/chat.py` (`_retrieval_queries` — read only unless the harness needs a seam), `Makefile` (`golden`
  target only if a flag is needed).
- **Contract impact.** None (fixtures + harness).
- **Gate.** live: `make golden` (single-turn floor unchanged) + the follow-up run on/off.
- **Acceptance.** A table: follow-up recall@5 and p50 latency with condensation on vs off; the single-turn floor holds.
- **Close.** knowledge-and-behavior.md "Follow-up questions" tip with the measured numbers; CHANGELOG.
- **Depends.** F1.4 (stable baseline).
- **Agent.** sonnet + human decision · live · stop after the table · Handoff names the fixture file and the numbers.

---

## Definition of done (per task)

A task is done only when: (1) its contract changed first if it touches API/schema/model; (2) the relevant gate is **green in CI**, not just locally; (3) no `detail=str(e)` reintroduced; (4) generated artifacts regenerated, not hand-edited; (5) docs updated in the same PR.

---
