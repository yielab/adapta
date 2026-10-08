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
- **Gate** — the one `make` target (or GPU suite) that proves it; escalate only if that gate cannot see the change.
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
  `adapta-app` image (command in gates.md). `live`, `gpu` and `rebuild` gates run on the main checkout, one at
  a time, with no other edit landing there meanwhile — hot reload kills live tests and `make up` restarts
  every container. Worktrees are not bind-mounted, so editing there is always safe.
- **Closing writes two notes, then moves the block.** **Done.** (≤ 8 lines) and **Handoff.** (what downstream
  blocks must now use: names, signatures, the migration revision taken, moved anchors, measured numbers). The
  block then goes to `CHANGELOG.md`; only its board row stays here. The lead reads Handoff there.
- **Tier is a floor, not a ceiling.** `haiku` rows are mechanical and fully specified; `sonnet` rows need
  design judgement; `sonnet + human decision` rows stop after the measurement so the user can decide.

---

## Status snapshot (updated 2026-10-08)

| Area | State |
|---|---|
| Product build (phases 0–5), operator console, image fine-tunes, brand, positioning | ✅ complete — history in [CHANGELOG.md](CHANGELOG.md) |
| SDD gates | Pillar 2 ✅ `make migrate-test` · Pillar 3 ✅ eval gate validated on GPU (`test_eval_gate`, `test_lora_e2e`) · **Pillar 1 🟥 red** since the 2026-09-17 rebuild (schemathesis 4.x, 9–11 failures — E1.11) |
| CI fast gate (`make ci`) | ✅ green again 2026-10-08 — E1.14 closed the 4 mypy errors (ruff + mypy clean, 269 unit tests pass); last run in the pre-E1.10 image, re-run after the pinned rebuild |
| **Audit 2026-09-03 (§E)** | 🟥 **open** — 10/35 done (E1.1–E1.9 shipped 2026-09-17, E1.14 on 2026-10-08). Wave 0 in flight: E1.10 merged, waiting on the rebuild + GPU gate (board: ready-for-live), then E1.11; then E1.12/E1.13, E2 (Ollama + launch kit), E3 (Postgres chunks → real hybrid FTS, Docling + RapidOCR, citations with page/OCR provenance, system prompt + threshold + filters, multilingual, queued indexing, golden set), E4 (task metrics in the gate, adapter promotion/rollback, synthesis re-aimed, JSON mode, multi-turn), E5 (contextual retrieval, RAG gate, history-aware retrieval, VLM extraction). Scheduling: the §E board. |

---

## E. Audit 2026-09-03 — correctness, real hybrid RAG, scanned documents, governed adapters (opened 2026-09-03)

> **Source.** Product audit of 2026-09-03: code read with `file:line` evidence, GitHub API and a
> verified ecosystem scan. Headline: the product thesis (RAG + gated fine-tune composed on one
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
> Postgres, the loaded VLM, the eval-gate machinery), or (c) is a differentiator nobody ships. One
> dependency that replaces several beats wiring four. **Deferred until a real user asks:** guardrails,
> connectors (folder/S3 sync at most), Helm, OIDC, GraphRAG/RAPTOR, ColPali, DPO in the console,
> continued training, Grafana dashboards. **Not built:** human-review queue UI, bounding-box editor,
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
| E1.14 | 0 | haiku | offline | none | E1.13, E3.2/E3.5 (`chat.py`) | done 2026-10-08 |
| E1.10 | 0 | sonnet | rebuild + gpu | none | E3.3b | ready-for-live (develop `411c5d3`; rebuild pending) |
| E1.11 | 0 | sonnet | live | E1.10 | any in-flight `specs/openapi.yaml` edit | open |
| E1.12 | 1 | haiku | gpu | none | E1.13 | open |
| E2.1 | 1 | sonnet | live | none | E4.4 | open |
| E2.3 | 1 | haiku | offline | E1.11 (no claim about a red gate) | E3.2, E3.3b (README bullets, text merge) | open |
| E3.1 | 1 | sonnet | live | none | E3.7, E3.2 | open |
| E3.3a | 1 | sonnet + human decision | offline | none | — | open |
| E3.8 | 1 | sonnet | live | none — must land before E3.2 | — | open |
| E1.13 | 2 | sonnet | gpu | E1.12 | E1.12 | open |
| E2.2 | 2 | sonnet | live | E2.1, E1.11 | E4.2 (`endpoints.py`, `EndpointPanel.svelte`, spec endpoint section) | open |
| E3.2 | 2 | sonnet | live | E3.1, E3.8 (baseline recorded before this lands) | E3.7, E3.5 | open |
| E3.3b | 2 | sonnet | rebuild + live | E3.3a (commit), E3.1 | E1.10, E3.7, E3.4 | open |
| E3.7 | 2 | sonnet | live | E3.1 | E3.1/E3.3b, E4.1/E4.5 | open |
| E4.2 | 2 | sonnet | live | E1.11 | E2.2 (same files) | open |
| E4.4 | 2 | sonnet | live | E1.11 | E3.5/E5.3, E2.1, E4.1 | open |
| E3.4 | 3 | sonnet | live | E3.1, E3.3b, E1.11 | E3.5 (spec, `Playground.svelte`), E3.3b | open |
| E3.5 | 3 | sonnet | live | E3.2, E1.11 | E3.4 (spec, `Playground.svelte`), E4.4 and E5.3 | open |
| E3.6 | 3 | sonnet + human decision | live | E3.1, E3.2, E3.8 | E3.2 | open |
| E4.1 | 3 | sonnet | gpu | E1.12, E1.11 | E4.5 | open |
| E4.3 | 3 | sonnet | live | E3.8, E1.11 | E4.1/E4.5, E5.1 (`synthesis.py` helper) | open |
| E4.5 | 3 | sonnet | gpu | E1.12 | E4.1 (same files) | open |
| E5.1 | 4 | sonnet | live | E3.1, E3.7, E3.8 | E5.2, E4.3 | open |
| E5.2 | 4 | sonnet | live | E3.8, E3.7, E4.3 | E5.1, E4.2 | open |
| E5.3 | 4 | sonnet | live | E3.2, E3.5, E3.8 | E4.4/E3.5 | open |
| E5.4 | 4 | sonnet | gpu | E3.3b, E3.4, E3.5, E3.7 | E5.1/E5.2, E3.4 | open |

### E1. P0 — corrections that change the publishable evidence (weeks 1–2)

E1.1–E1.9 shipped 2026-09-17 → [CHANGELOG.md](CHANGELOG.md). E1.14 closed 2026-10-08. Open: E1.10 (ready-for-live) → E1.11 (wave 0 — every other
block's gate depends on them), E1.12, E1.13.


### E1.10 `[INFRA]` Pin the heavy dependencies — an unbounded floor lets any rebuild move the product (P0)
- [ ] **Context.** `pyproject.toml` declares `torch>=2.2.0` (:58) and `schemathesis>=3.28.0` (:83)
  with no upper bound. A single image rebuild on 2026-09-17 resolved torch **2.14** (broke every
  training job — E1.9) and schemathesis **4.27.3** (broke `make test-contracts` — E1.11). Neither
  was a code change; both were a floor that moved. The repo's own claim that the contract gate is
  green (CLAUDE.md, Status snapshot) dates from 2026-06-22 and is no longer true.
- **Depends.** none. **Unblocks.** E1.11 and every later rebuild (E3.3b).
- **Agent.** sonnet · gate class **rebuild + gpu (exclusive: nothing else runs)** · serialize with:
  E3.3b (`pyproject.toml`) · **Handoff.** must name the resolved-version table and each bound added.
- **Scope.** Upper bounds on the dependencies whose major versions change behaviour — torch,
  triton (transitively), transformers, peft, trl, schemathesis, chromadb. Out: a full lockfile
  (`uv.lock`/`pip-tools`) — propose it as its own block if bounds prove insufficient.
- **Steps.** (1) Record the versions the current working image resolves (`pip freeze` in both `app`
  and `worker`). (2) Add `<next-major` bounds in `pyproject.toml` for the list above, with a comment
  per line saying what breaks if it moves. (3) `make up` and confirm the resolved set is unchanged.
  (4) Note the policy in CONTRIBUTING (how to raise a bound deliberately).
- **Status 2026-10-08.** Code merged on `develop` (`a66fa15`, `411c5d3`): bounds on torch `<3`, triton `<4`,
  transformers `<6`, peft `<1`, trl `<2`, schemathesis `<5`, sqlalchemy `[asyncio]` `<3`, asyncpg `<1`, alembic `<2`,
  fastapi `<1`, pydantic `<3`, redis `<9`; chromadb stays `==1.5.9`; policy in CONTRIBUTING. First rebuild **proved the
  thesis on an unnamed package**: SQLAlchemy 2.0.54 → 2.1.4 dropped `greenlet`, app + worker died at
  `import sqlalchemy.ext.asyncio` → fixed by `sqlalchemy[asyncio]`. Second rebuild aborted (PyPI at ~270 KB/s, multi-GB
  CUDA wheels). **Remaining, on the main checkout:** `make up` → `pip freeze` in app + worker shows `greenlet` and
  only minor moves vs the table in the Handoff draft (torch 2.14.1, transformers 5.19.0, peft 0.21.2, trl 1.14.2,
  schemathesis 4.29.4) → `make ci` → `ADAPTA_RUN_LORA_E2E=1` e2e → close (Done/Handoff → CHANGELOG, OPERATIONS §3 note).
- **Files.** `pyproject.toml:50-90`, `CONTRIBUTING.md` (dependency section).
- **Contract impact.** None.
- **Gate.** `make up` → `make ci` → one real training job (`ADAPTA_RUN_LORA_E2E=1
  tests/integration/test_lora_e2e.py`), because that is the only gate that exercises torch/triton.
- **Acceptance.** A clean `make up` on another machine resolves the same major versions; raising a
  bound is a deliberate, reviewed edit rather than a silent rebuild.
- **Close.** CONTRIBUTING dependency policy; OPERATIONS upgrade section; Status snapshot.

### E1.11 `[TEST]` Restore `make test-contracts` to green (P0)
- [ ] **Context.** Schemathesis 4.27.3 reports **9–11 failures** on every run: 9 “Invalid Allow
  header” on `OPTIONS` (`/projects`, `/projects/{id}`, `/projects/{id}/files`, `…/datasets`,
  `…/datasets/synthesize`, `…/endpoint`, `…/jobs`, `…/keys`, `/settings`) and 1–2 “API rejected
  schema-compliant request” on `POST /auth/register` and `POST /auth/login` from fuzzed
  unicode/oversized emails (the auth pair is randomised per run). Verified 2026-09-17 across four
  separate runs during §E1: none touch `/v1/chat/completions`, `Citation` or `BaseModelInfo`, so
  §E did not cause them — but Pillar 1 is no longer enforced, which several docs still assert.
- **Depends.** E1.10. **Unblocks.** every block whose gate runs `make test-contracts` (E2.2, E3.4,
  E3.5, E4.1–E4.4, E5.2, E5.3).
- **Agent.** sonnet · gate class **live** · serialize with: any in-flight `specs/openapi.yaml` edit
  — land this first · **Handoff.** must name which side was fixed per failure class and the final
  operation count.
- **Scope.** Make the gate honest again: either the responses are wrong (fix them) or the spec is
  wrong (fix it). Decide per failure class, do not silence checks wholesale.
- **Steps.** (1) `OPTIONS`: decide whether the CORS middleware should emit a valid `Allow` header or
  whether those paths should declare `options` in the spec; fix the side that is actually wrong.
  (2) Auth: the fuzzed emails are schema-compliant but rejected — tighten the spec's `email` format
  and length so the contract matches the validator, rather than loosening the validator.
  (3) Re-run until 0 failures; restore the “all operations, zero 5xx” claim with its real count.
- **Files.** `adapta/api/app.py` (CORS/middleware), `specs/openapi.yaml` (`grep -n 'options:'`, the
  auth request schemas), `Makefile:128-145`, `CLAUDE.md` Workflow table (Pillar-1 line), `TODO.md` Status snapshot.
- **Contract impact.** API.
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test-contracts`
  (must be **0 failures**, not “only the known ones”).
- **Acceptance.** `make test-contracts` green twice in a row (the auth failure is randomised, so one
  green run is not proof); the Pillar-1 line in CLAUDE.md and the Status snapshot carries the new
  operation count and date.
- **Close.** CLAUDE.md Workflow table (Pillar-1 line); Status snapshot.

### E1.12 `[TEST]` The LoRA e2e must fail when the training job fails (P0)
- [ ] **Context.** `tests/integration/test_lora_e2e.py:180` asserts `body["status"] in ("succeeded",
  "failed")` and then branches: on `failed` it only checks that the endpoint is refused (`:291-293`).
  So on 2026-09-17, with **every** training job crashing on a missing C compiler (E1.9), the suite
  printed `status=failed eval_score=None` and still reported **1 passed**. A gate that cannot tell
  “the gate correctly blocked a bad adapter” from “the trainer crashed” is not a gate. The
  use-case matrix did fail, which is what surfaced the problem — the e2e should have too.
- **Depends.** none. **Unblocks.** E1.13, E4.1, E4.5, E5.4 (their GPU gates rely on an honest e2e).
- **Agent.** haiku · gate class **gpu (the negative check breaks + restarts the worker)** ·
  serialize with: E1.13 (`test_lora_e2e.py`) · **Handoff.** must name the shared terminal-state
  helper name used by both suites.
- **Scope.** The two integration suites' terminal-state assertions. Do not change the eval gate.
- **Steps.** (1) `test_lora_e2e.py`: a job whose `error_message` is set, or whose `eval_score` is
  `None`, is an **infrastructure failure** → `pytest.fail` with the worker error, never the blocked
  branch. Keep a blocked-adapter branch only for `status == "succeeded" and eval_passed is False`.
  (2) Apply the same distinction in `test_lora_use_cases.py`'s waiter so a crashed job reports the
  worker's error rather than a gate verdict. (3) Assert the negative control is blocked **because**
  it succeeded and lost to base, not because it crashed.
- **Files.** `tests/integration/test_lora_e2e.py:160-200, 285-295`,
  `tests/integration/test_lora_use_cases.py` (the job waiter + garbage scenario assertions).
- **Contract impact.** None.
- **Gate.** `ADAPTA_RUN_LORA_E2E=1 tests/integration/test_lora_e2e.py` on GPU; plus a negative check
  — temporarily break the worker (e.g. `CC=/nonexistent`) and confirm the suite now **fails**.
- **Acceptance.** A crashed training job fails the e2e with the worker's error in the message; a
  genuinely blocked adapter still passes the blocked branch.
- **Close.** Status snapshot; the §E1.12 line in the Pillar-3 row if it claims e2e coverage.

### E1.13 `[BE]` Prove training progress reaches Redis during the run, not after it (P1)
- [ ] **Context.** E1.5 replaced the SFT/DPO progress callback's bare `asyncio.create_task` (fired
  from inside the blocking HF `trainer.train()` call) with `asyncio.run_coroutine_threadsafe`. Six
  real GPU runs on 2026-09-17 produced **no** `no running event loop` / `coroutine was never awaited`
  errors, so the regression is gone — but progress publishing emits no log line, so there is no
  evidence that records reach Redis *during* training rather than in a burst once it returns. The
  console's live progress bar depends on the answer.
- **Depends.** E1.12. **Unblocks.** none.
- **Agent.** sonnet · gate class **gpu** · serialize with: E1.12 (`test_lora_e2e.py`) · **Handoff.**
  must name whether step 3 (`asyncio.to_thread`) was needed.
- **Scope.** Observability + one assertion. No change to the training loop.
- **Steps.** (1) Log one line per published progress record (step, epoch, percent) at DEBUG in the
  worker. (2) In the GPU e2e, poll `GET /jobs/{id}` while the job is `running` and assert `progress`
  strictly increases at least twice **before** the terminal state. (3) If it does not, the real bug
  is that the blocking call never yields to the loop — then move the HF call to `asyncio.to_thread`
  (it is a call site change, not a rewrite of the loop — hard constraint #1 still holds).
- **Files.** `adapta/training/trainer.py:212-234` (both `ProgressCallback` classes),
  `adapta/services/jobs.py`, `tests/integration/test_lora_e2e.py`.
- **Contract impact.** None.
- **Gate.** `make test` → `ADAPTA_RUN_LORA_E2E=1 tests/integration/test_lora_e2e.py` on GPU.
- **Acceptance.** The e2e observes progress advancing mid-run; the console's progress bar is
  demonstrably live rather than a post-hoc jump to 100 %.
- **Close.** operator-console fine-tune flow (progress bar claim); Status snapshot.

### E2. Distribution + launch kit (weeks 2–3)

### E2.1 `[BE+INFRA]` Ollama as an inference backend for base-model and RAG-only endpoints (P1)
- [ ] **Context.** `adapta/core/backends/` already abstracts serving (`ServingBackend` ABC; llama-cpp
  default; vLLM sidecar for text LoRA). Ollama (180k★, MIT) is the substrate the local-AI ecosystem
  builds on — Open WebUI grew by attaching to it, and every "works with Ollama" integration is a free
  acquisition channel. RAG-only and base endpoints don't need an in-process llama-cpp when an Ollama
  host exists.
- **Depends.** none. **Unblocks.** E2.2.
- **Agent.** sonnet · gate class **live (`--profile ollama`)** · serialize with: E4.4
  (`core/backends/*.py`) · **Handoff.** must name `ollama_model_map` keys and the routing rule.
- **Scope.** Read-only client for adapter-less text requests via Ollama's OpenAI-compatible
  `/v1/chat/completions`. Out: serving Adapta-trained adapters through Ollama at runtime (E2.2 exports
  them), vision.
- **Steps.** (1) `core/backends/ollama_backend.py`: `OllamaBackend(ServingBackend)` with httpx (already
  a dep), mirroring `vllm_backend.py` — `prepare()`, non-streaming + streaming, usage from Ollama's
  `prompt_eval_count`/`eval_count` (exact, unlike vLLM's `len//4`). (2) Routing in
  `core/backends/__init__.py`: `ADAPTA_SERVING_BACKEND=ollama` sends adapter-less text requests to
  Ollama; adapters and vision stay on llama-cpp. (3) `config.py`: `ollama_base_url`,
  `ollama_model_map` (catalog name → Ollama tag; default map for the Apache entries of E1.2).
  (4) `docker-compose.yml`: optional `ollama` service under `profiles: [ollama]` (official image, GPU
  via CDI like `vllm-server`). (5) `tests/test_backend_ollama.py`: mocked httpx transport — routing,
  usage mapping, streaming frames. (6) OPERATIONS §9-style runbook "Serve RAG through Ollama".
- **Files.** `adapta/core/backends/base.py`, `adapta/core/backends/vllm_backend.py` (pattern),
  `adapta/core/backends/__init__.py:44-64`, `adapta/config.py` (`grep -n vllm_`),
  `docker-compose.yml` (`vllm-server` block as template), `docs/reference/OPERATIONS.md` §9.
- **Contract impact.** None (env config).
- **Gate.** `make test` → live: `docker compose --profile ollama up -d` + one RAG chat in the playground.
- **Acceptance.** With the profile on, a RAG project's endpoint answers through Ollama with exact token
  counts and citations; llama-cpp untouched for adapters/vision; `make ci` green.
- **Close.** OPERATIONS §9 sibling section; README "Using the API" one line; Status snapshot.

### E2.2 `[BE]` Export a gated adapter as an Ollama Modelfile bundle (P2)
- [ ] **Context.** Ollama imports LoRA adapters with a `Modelfile` (`FROM <base>` + `ADAPTER <path>`).
  Adapta already produces a GGUF LoRA per passing job (`adapter_conversion.py`); exporting it lets any
  Ollama user run an Adapta-trained, gate-passed adapter — the adapter travels to 180k★ of users.
- **Depends.** E2.1, E1.11. **Unblocks.** none.
- **Agent.** sonnet · gate class **live** · serialize with: E4.2 (`endpoints.py`,
  `EndpointPanel.svelte`, spec endpoint section) · **Handoff.** must name the route and zip layout.
- **Scope.** A zip `{adapter.gguf, Modelfile, README.txt}` for endpoints whose adapter passed the gate;
  text adapters only (Ollama's LoRA import doesn't cover mmproj VLM adapters). Out: pushing to
  ollama.com.
- **Steps.** (1) Spec `GET /v1/projects/{id}/endpoint/export?format=ollama` → `application/zip`,
  writer role, 404 without a gated adapter. (2) Handler builds the zip in a temp dir: the GGUF LoRA, a
  `Modelfile` (`FROM` = the catalog entry's Ollama tag from E2.1's map, `ADAPTER ./adapter.gguf`,
  `TEMPLATE`/`PARAMETER stop` from `chat_templates.py`), and a README carrying the gate line (score,
  base, delta, date). (3) Console `EndpointPanel.svelte`: "Export for Ollama". (4) Tests: zip
  contents + Modelfile text; 404 path.
- **Files.** `specs/openapi.yaml` (endpoint section), `adapta/api/v1/endpoints.py`,
  `adapta/core/chat_templates.py`, `adapta/services/adapters.py`,
  `adapta/console/src/views/EndpointPanel.svelte`, `tests/test_adapter_serving.py`.
- **Contract impact.** API (new route).
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `make test-contracts`.
- **Acceptance.** `ollama create adapta-demo -f Modelfile` on a host with the base tag yields a model
  that answers in the trained shape (manual check, recorded in the Done note).
- **Close.** consuming-the-api "Export to Ollama"; Status snapshot.

### E2.3 `[DOCS]` Launch kit: README first screen, migration guides, honest status (P1)
- [ ] **Context.** The licensing advantage (Apache-2.0 with orgs/keys in the box, versus Open WebUI's
  >50-user branding clause, Dify's multi-tenant ban, Kiln's proprietary desktop app, Onyx's SSO/RBAC in
  EE) lives only in COMPETITIVE_LANDSCAPE. Flowise (55k★, Apache-2.0) archived 2026-08-13; Cognita and
  Verba archived; R2R stale since 2025-11 — their users are looking for a home now. The README status
  note ("working prototype — not production-hardened") is honest but reads as self-sabotage.
- **Depends.** E1.11 (no claim about a red gate). **Unblocks.** none.
- **Agent.** haiku · gate class **offline (`make docs-build`)** · serialize with: E3.2, E3.3b
  (README bullets — text merge) · **Handoff.** must name none (self-contained).
- **Scope.** Copy + one new user-guide page. Do it **after** E1.3/E1.4's re-measure so every number
  quoted is current; claim nothing E1 hasn't made true.
- **Steps.** (1) README: a 6-row "what you get under Apache-2.0" table (feature · Adapta · the
  restriction elsewhere, each cell linking the other project's license page) above the fold; status
  note → "beta: works end to end; audit the auth and eval-gate paths before sensitive data".
  (2) `docs/user-guide/migrating.md`: from Flowise / Cognita / R2R — concept mapping (flow → project,
  document store → files, chain → endpoint), what has no equivalent (the canvas), a 10-line curl path.
  (3) COMPETITIVE_LANDSCAPE: license-restriction column with citations; rows for Unsloth Desktop,
  Kiln, BISHENG (verified 2026-09-03). (4) `mkdocs.yml` nav + hub links.
- **Files.** `README.md`, `docs/user-guide/migrating.md` (new), `docs/user-guide/index.md`,
  `docs/reference/COMPETITIVE_LANDSCAPE.md`, `mkdocs.yml`.
- **Contract impact.** None.
- **Gate.** `make docs-build` (host, `--strict`).
- **Acceptance.** Every cell of the new table links a primary source; the migration page is in nav; the
  README status note no longer says "prototype".
- **Close.** Self-contained; Status snapshot.

### E3. P1 — real hybrid RAG + scanned documents (weeks 3–7)

### E3.1 `[BE]` Persist chunks in Postgres — the pivot pages, filters, ACL and eval hang off (P1)
- [ ] **Context.** Chunks live only in Chroma with metadata `{source, chunk_index, file_id}`
  (`rag.py:173-175`): no page, no hash, no text in Postgres → no citations with page/text, no dedup, no
  SQL filters, no full-text leg, and counters that drift (E1.8).
- **Depends.** none. **Unblocks.** E3.2, E3.3b, E3.4, E3.6, E3.7, E5.1.
- **Agent.** sonnet · gate class **live (`make migrate-test` + rag e2e)** · serialize with: E3.7
  (`files.py`), E3.2 (`rag.py`) · **Handoff.** must name the migration revision actually used, the
  ORM class name, where counts are read from.
- **Scope.** Table + write-through on index/delete; counters derived from it. Out: the FTS query leg
  (E3.2), page numbers (E3.3b fills `page`).
- **Steps.** (1) Migration `0010_chunks`: `chunks(id PK = "{file_id}_{index}", file_id FK ON DELETE
  CASCADE, project_id, chunk_index, page INT NULL, section TEXT NULL, text TEXT, content_hash CHAR(64),
  ocr BOOL DEFAULT false, ocr_confidence REAL NULL, needs_review BOOL DEFAULT false,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED)`; GIN on `tsv`; index on
  `project_id`; unique `(file_id, chunk_index)`. (2) `rag.py` `index_chunks`: insert rows in the file
  row's session **before** the Chroma upsert (Chroma failure → rollback). (3) `delete_file_chunks`:
  rows go by CASCADE; Chroma delete failures raise a typed error instead of a swallowed warning
  (`rag.py:193-194`). (4) Read `num_chunks`/`num_documents` as `SELECT count(*)` (keep the columns
  until E3.2 lands; drop them in a follow-up migration). (5) `content_hash = sha256(text)`; an upload
  whose every chunk hash already exists in the project → 409 `DuplicateDocument`. (6) Tests: migration
  round-trip; N rows on index; cascade on delete; duplicate upload 409.
- **Files.** `migrations/versions/0010_chunks.py` (new), `adapta/db/models.py:300-320`,
  `adapta/services/rag.py:150-195`, `adapta/api/v1/files.py:80-135, 194-227`,
  `adapta/domain/errors.py`, `tests/test_rag_hybrid.py`, `tests/integration/test_rag_e2e.py`.
- **Contract impact.** DB (migration 0010).
- **Gate.** `make migrate` → `make migrate-test` → `make check-leaks` → `make test` →
  `tests/integration/test_rag_e2e.py`.
- **Acceptance.** `SELECT count(*) FROM chunks WHERE project_id=…` equals the files' chunk total;
  deleting a file removes rows and vectors; re-uploading the same PDF returns 409.
- **Close.** architecture.md data model; `.claude/context/repo-map.md` (12 tables); Status snapshot.

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
- **Agent.** sonnet · gate class **rebuild + live** · serialize with: E1.10 (`pyproject.toml`), E3.7
  (`documents.py`), E3.4 (`RagFlow.svelte`) · **Handoff.** must name the `Chunk` fields, accepted
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
- **Agent.** sonnet · gate class **live** · serialize with: E3.4 (spec, `Playground.svelte`), E4.4
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
  visibility, rows stuck in `processing` after a restart (the §A4.10 sweeper covers training jobs
  only). `core/metrics.py:177-221` has no retrieval metrics.
- **Depends.** E3.1. **Unblocks.** E5.1, E5.2, E5.4 (job kinds).
- **Agent.** sonnet · gate class **live (`docker compose restart worker` + rag e2e + sweep test)** ·
  serialize with: E3.1/E3.3b (`files.py`, `documents.py`), E4.1/E4.5 (`worker/main.py`) ·
  **Handoff.** must name the job payload shape (`kind`), `_run_index_job`, the metric names, the
  gates.md trap added.
- **Scope.** Reuse the existing Redis BLPOP queue with a job `kind`; the worker runs CPU index jobs
  too (no GPU gate for that kind). Out: a second worker process, priorities.
- **Steps.** (1) `services/jobs.py`: payload gains `kind: "train" | "index"`; `worker/main.py`
  dispatches by kind **before** the GPU guard — the training path is untouched. (2) `files.py`
  enqueues `{kind: index, file_id}`; the worker writes `pending → processing → indexed/failed`; one
  retry on transient failure; the sweeper learns the `index` kind. (3) Hot-reload trap: changes to
  `adapta/services/documents.py` now need `docker compose restart worker` — add to gates.md.
  (4) Metrics: `adapta_rag_retrieval_seconds` (histogram), `adapta_rag_chunks_returned`,
  `adapta_rag_reranker_seconds`, `adapta_index_seconds_per_page`. (5) Tests: `test_jobs.py` kind
  dispatch; `test_observability.py` metric names; `test_stuck_task_sweep.py` covers index rows.
- **Files.** `adapta/services/jobs.py`, `adapta/worker/main.py:440-485` (+ `_run_index_job`),
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

### E3.8 `[TEST]` Golden set + recall@k harness — the number every later RAG change reports against (P1)
- [ ] **Context.** There is no retrieval-quality test: `test_rag_hybrid.py` is synthetic ordering and
  `test_rag_e2e.py` asserts an answer exists. E3.2, E3.6, E5.1 and E5.2 all claim improvements that
  need one number.
- **Depends.** none — must land **before E3.2**. **Unblocks.** E3.2, E3.6, E4.3, E5.1, E5.2, E5.3.
- **Agent.** sonnet · gate class **live (`make golden`)** · serialize with: none (new files + one
  Makefile target) · **Handoff.** must name the `questions.jsonl` schema, the floor file path, the
  baseline numbers.
- **Scope.** A small public bilingual corpus + questions with the expected file/page, and a harness
  reporting recall@5, MRR and p50 latency. Out: LLM-as-judge faithfulness.
- **Steps.** (1) `tests/fixtures/golden/`: ~30 public-domain documents (manuals/policies, es+en;
  2 scanned pages once E3.3b lands) + `questions.jsonl` `{q, expected_file, expected_page?, lang}`.
  (2) `tests/integration/test_rag_golden.py` (opt-in `ADAPTA_RUN_GOLDEN=1`): index once per session,
  run all questions through `retrieve()`, print a table, assert recall@5 ≥ the floor in
  `tests/fixtures/golden/floor.json` (a ratchet: raise it deliberately, never lower it silently).
  (3) `make golden` target. (4) Record the baseline on the **current** code before E3.2 lands.
- **Files.** `tests/fixtures/golden/` (new), `tests/integration/test_rag_golden.py` (new), `Makefile`,
  `docs/developer-guide/workflow.md` (one paragraph), `.claude/context/gates.md` (row: retrieval
  quality change → `make golden`).
- **Contract impact.** None.
- **Gate.** `make golden` (live stack).
- **Acceptance.** Baseline recall@5 / MRR / latency recorded in the Done note; the floor file exists;
  the harness runs in under 5 minutes on CPU.
- **Close.** workflow.md; gates.md row; Status snapshot.

### E4. P2 — fine-tuning as a governed feature (weeks 7–10)

### E4.1 `[BE]` Task metrics in the eval gate, chosen by use-case template (P2)
- [ ] **Context.** The gate is `score = exp(−loss)` only; `EvaluationMetrics.accuracy / exact_match /
  token_accuracy / bleu …` are hard-coded `None` (`evaluator.py:314-326`). For extraction, "does the
  JSON parse and match the fields?" is trivial and far more convincing than 0.33.
- **Depends.** E1.12, E1.11. **Unblocks.** none.
- **Agent.** sonnet · gate class **gpu (use-case matrix)** · serialize with: E4.5 (`evaluator.py`,
  `worker/main.py`, `FinetuneFlow.svelte`) — run E4.1 first; E4.4 (`FinetuneFlow.svelte`); E3.7
  (`worker/main.py`) · **Handoff.** must name the `task_metrics` shape and the template-floor rule.
- **Scope.** Three templates — `classify` (label accuracy after strip/lower), `extract` (JSON-parse
  rate + per-key exact match), `format` (adherence regex shipped with the dataset, or none) — computed
  by greedy generation on the held-out rows for adapter **and** base. The perplexity rule
  (`passes_eval_gate`) stays and gains an optional template floor when a template is set (e.g.
  `classify`: accuracy ≥ base + 0.10 or ≥ 0.8). Out: LLM-as-judge, human approval.
- **Steps.** (1) Model contract: `training_dataset.schema.json` optional `metadata.task` enum;
  `JobCreateRequest.task_template` optional. (2) `evaluator.py`: after loss scoring, generate on all
  held-out rows (cap 200; the 5-sample path already exists) and compute the template metrics for both
  models. (3) `training/models.py`: `EvaluationResult.task_metrics` for both; `passes_eval_gate`
  gains the template floor. (4) Worker persists them in `eval_metrics`; `FinetuneFlow.svelte` gate
  panel shows "JSON valid 96 % (base 41 %)". (5) `test_eval_gate.py`: metric functions + rule cases.
  (6) `test_lora_use_cases.py`: assert the template metrics for scenarios A/B/C.
- **Files.** `specs/schemas/training_dataset.schema.json`, `specs/openapi.yaml`
  (`grep -n JobCreateRequest`), `adapta/training/evaluator.py:139-330`,
  `adapta/training/models.py:15-72`, `adapta/worker/main.py:300-330`, `adapta/services/training.py`
  (validation), `adapta/console/src/views/FinetuneFlow.svelte:308-326`, `tests/test_eval_gate.py`,
  `tests/integration/test_lora_use_cases.py`.
- **Contract impact.** Model + API.
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` → GPU use-case
  matrix.
- **Acceptance.** The extraction run reports JSON-valid rate and per-field match vs base;
  classification reports accuracy; the garbage control fails both the loss gate and the template floor;
  the console shows the metrics.
- **Close.** PRODUCT_DEFINITION eval-gate paragraph, learning-the-system, fine-tuning-use-cases (new
  columns), CLAUDE.md gate one-liner; Status snapshot.

### E4.2 `[BE+FE]` Adapter promotion, rollback and an audit trail (P2)
- [ ] **Context.** `Endpoint.adapter_path` is written once at creation (`endpoints.py:156-184`) and no
  route updates it; the registry keeps every adapter (`adapters.py:104-105`) but nothing lists,
  compares or promotes them; nobody records who promoted what. The pitch is *governed* fine-tuning.
- **Depends.** E1.11. **Unblocks.** none.
- **Agent.** sonnet · gate class **live** · serialize with: E2.2 (same files) — run E2.2 first; E5.2
  (`EndpointPanel.svelte`) · **Handoff.** must name the migration revision, the promote route, the
  eviction wrapper name.
- **Scope.** List gated adapters; promote one; rollback = promote the previous; every change logged.
  Out: A/B traffic split, shadow mode.
- **Steps.** (1) Migration `0013_adapter_events`: `adapter_events(id, endpoint_id, job_id,
  adapter_path, action promote|rollback, actor_user_id, eval_score, base_score, delta, created_at)`.
  (2) Spec: `GET /v1/projects/{id}/adapters` (gated jobs + scores), `POST
  /v1/projects/{id}/endpoint/promote {job_id}` (writer; job must be `succeeded ∧ eval_passed`),
  `GET /v1/projects/{id}/endpoint/history`. (3) `endpoints.py`: promote updates `adapter_path`, evicts
  the cache entry for the old `(base, adapter)` key, writes the event; rollback = promote with the
  previous event's job. (4) Registry: the `adapter_events` + jobs tables become the source of truth —
  delete the JSON file I/O in `services/adapters.py`, keep the gate function. (5) Console
  `EndpointPanel.svelte`: adapters table (score, Δ, date, Promote), history list, current-adapter badge.
  (6) Tests: promote/rollback state machine; viewer 403; eviction called.
- **Files.** `migrations/versions/0013_adapter_events.py`, `adapta/db/models.py`, `specs/openapi.yaml`
  (endpoint section), `adapta/api/v1/endpoints.py:100-190`, `adapta/services/adapters.py`,
  `adapta/core/model_manager.py` (an `evict(key)` wrapper if absent — wrap, never rewrite),
  `adapta/console/src/views/EndpointPanel.svelte`, `tests/test_adapter_serving.py`,
  `tests/integration/test_c_phase_rbac.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate` → `make migrate-test` → `make validate-spec` → `make generate` →
  `make check-models` → `make test` → `make test-contracts` → `make console-build`.
- **Acceptance.** Retrain → promote changes the served adapter without a restart; rollback restores the
  previous; history shows actor + scores; a non-gated job cannot be promoted (400).
- **Close.** operator-console endpoint section, consuming-the-api, PRODUCT_DEFINITION serving
  paragraph, CLAUDE.md API surface block; Status snapshot.

### E4.3 `[BE+FE]` Synthesis re-aimed: RAG eval sets and behaviour pairs, optional teacher (P2)
- [ ] **Context.** The synthesis prompt asks for "comprehension" Q/A "based solely on the passage"
  (`synthesis.py:34-48`) — fact pairs, the one thing `knowledge-and-behavior.md:27-33` says not to
  fine-tune on; the generator is the same small model; dedup is exact-string (`:154-157`). The
  console's happy path leads users straight into it.
- **Depends.** E3.8, E1.11. **Unblocks.** E5.2.
- **Agent.** sonnet · gate class **live** · serialize with: E4.1/E4.5 (`FinetuneFlow.svelte`), E5.1
  (`synthesis.py` helper) · **Handoff.** must name the `Dataset.kind` values and that `rag_eval`
  rows equal E3.8's format.
- **Scope.** Two modes + an optional stronger generator. Out: quality scoring beyond parse + dedup.
- **Steps.** (1) Spec `SynthesizeRequest.mode: "rag_eval" | "behavior"` (default `rag_eval`),
  `style_instructions` (for `behavior`), optional `teacher_base_url` / `teacher_model` (any
  OpenAI-compatible endpoint — a bigger local model or Ollama). (2) `rag_eval` produces
  `{question, answer, source_chunk_id}` rows in the E3.8/E5.2 golden format, stored as a dataset with
  `kind = eval` (new `Dataset.kind`, migration `0014_dataset_kind`). (3) `behavior` produces
  `{prompt, response}` where the *shape* varies and facts are quoted from the chunk — the
  training-appropriate signal. (4) Near-duplicate filter with the existing embedding service
  (cosine > 0.92 dropped). (5) Console: mode radio with one guidance line each; the "Synthesize from
  documents" button defaults to `rag_eval`. (6) Tests: parsing per mode; dedup.
- **Files.** `specs/openapi.yaml` (`SynthesizeRequest`, `DatasetResponse.kind`),
  `migrations/versions/0014_dataset_kind.py`, `adapta/services/synthesis.py`,
  `adapta/api/v1/synthesis.py`, `adapta/db/models.py`,
  `adapta/console/src/views/FinetuneFlow.svelte:729-780`, `tests/test_synthesis_helpers.py`.
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → `make test-contracts`.
- **Acceptance.** `rag_eval` output loads into the E3.8 harness unchanged; `behavior` rows vary in form,
  not fact; the console default is `rag_eval`; the docs warning and the console copy agree.
- **Close.** knowledge-and-behavior, fine-tuning-walkthrough synthesis step, operator-console; Status
  snapshot.

### E4.4 `[BE]` JSON mode on the endpoint — the cheaper alternative to an extraction fine-tune (P2)
- [ ] **Context.** Extraction is the most-used fine-tune template, yet llama.cpp's grammar-constrained
  decoding (`response_format` `json_object` / `json_schema`) is not exposed. The console should be
  able to say "try JSON mode first".
- **Depends.** E1.11. **Unblocks.** none.
- **Agent.** sonnet · gate class **live (`test_inference_slow` needs the GGUF under `data/` on the
  main checkout)** · serialize with: E3.5/E5.3 (`chat.py`), E2.1 (`core/backends/`), E4.1
  (`FinetuneFlow.svelte`) · **Handoff.** must name the kwarg forwarded and which backends honour it.
- **Scope.** Pass-through of `response_format` to `create_chat_completion` (a call argument, not an
  engine change); vLLM/Ollama forward the same field. Out: validating the output beyond the grammar.
- **Steps.** (1) Spec `ChatCompletionRequest.response_format` (OpenAI shape). (2) `inference.py`
  `generate_chat`: forward it in kwargs (verify the signature accepts kwargs; wrap only).
  (3) Backends forward as-is. (4) Playground "JSON" toggle; `FinetuneFlow.svelte` extraction template
  copy: "Try JSON mode on the base model first — fine-tune if the fields are still wrong". (5) Tests:
  request model accepts it; `test_inference_slow.py` asserts parseable JSON.
- **Files.** `specs/openapi.yaml` (`ChatCompletionRequest`), `adapta/services/chat.py:300-330, 500-520`,
  `adapta/core/inference.py:183-230` (kwargs only), `adapta/core/backends/*.py`,
  `adapta/console/src/views/Playground.svelte`, `adapta/console/src/views/FinetuneFlow.svelte:686-724`,
  `tests/test_inference_slow.py`.
- **Contract impact.** API.
- **Gate.** `make validate-spec` → `make generate` → `make check-models` → `make test` →
  `tests/test_inference_slow.py` (local GGUF).
- **Acceptance.** `response_format: {type: json_object}` yields parseable JSON on the base model; the
  console copy points extraction users to it first.
- **Close.** consuming-the-api; knowledge-and-behavior "when to use which" extraction row; Status
  snapshot.

### E4.5 `[BE]` Multi-turn rows in the training dataset contract (P2)
- [ ] **Context.** Rows are `{prompt, response}` (`training_dataset.schema.json:7-79`); the worker
  synthesises a fixed 2–3 message list (`worker/main.py:169-177`) although `preprocess_function`
  already walks a `messages` list (`trainer.py:111-126`). Support-assistant datasets are conversations.
- **Depends.** E1.12. **Unblocks.** none.
- **Agent.** sonnet · gate class **gpu** · serialize with: E4.1 (same files) — run after E4.1 ·
  **Handoff.** must name the schema branch name and the eval-target rule.
- **Scope.** `MessagesRow = {messages: [{role, content}…]}` as a third `oneOf` branch (text only; last
  message `assistant`; alternating roles validated). Eval target = the last assistant turn (document
  it). Out: vision and DPO multi-turn.
- **Steps.** (1) Schema branch + `$comment`. (2) `services/training.py` `_validate_row` + the
  mixed-format rejection rule. (3) Worker passes `messages` through; E1.3's renderer handles
  multi-turn. (4) Evaluator: target = last assistant turn. (5) D6 review panel renders messages rows
  read-only. (6) Tests: validation cases; render/mask on a 4-turn row.
- **Files.** `specs/schemas/training_dataset.schema.json`, `adapta/services/training.py:250-300`,
  `adapta/worker/main.py:160-200`, `adapta/training/evaluator.py:51-112`,
  `adapta/console/src/views/FinetuneFlow.svelte` (review panel), `tests/test_dataset_review.py`,
  `tests/test_eval_gate.py`.
- **Contract impact.** Model.
- **Gate.** `make test` → one GPU SFT run on a small multi-turn dataset (a `test_lora_e2e.py` variant).
- **Acceptance.** A multi-turn JSONL uploads, validates, trains, gates and serves; a mixed-format file
  is rejected with a typed error naming the row.
- **Close.** fine-tuning-walkthrough dataset section; Status snapshot.

### E5. Differentiation (weeks 10–13)

### E5.1 `[BE]` Contextual retrieval at index time, opt-in per project (P2)
- [ ] **Context.** Anthropic's contextual retrieval (prepend an LLM-written situating sentence to each
  chunk before embedding and full-text indexing) cut top-20 retrieval failures by 49 % (67 % with
  reranking). No open-source platform in the 2026-09 scan ships it. Adapta's generator is local, so it
  costs minutes, not API dollars.
- **Depends.** E3.1, E3.7, E3.8. **Unblocks.** none.
- **Agent.** sonnet · gate class **live (`make golden` before/after)** · serialize with: E5.2
  (`worker/main.py`), E4.3 (`synthesis.py`) · **Handoff.** must name the recall@5 delta and the flag
  name.
- **Scope.** Per-project flag; the sentence is generated by the project's base model (or the E4.3
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
  config or model change can silently degrade retrieval. E3.8 gives the harness and E4.3 `rag_eval`
  generates a per-project set.
- **Depends.** E3.8, E3.7, E4.3. **Unblocks.** none.
- **Agent.** sonnet · gate class **live** · serialize with: E5.1 (`worker/main.py`), E4.2
  (`EndpointPanel.svelte`) · **Handoff.** must name the `rag_eval` job kind and the summary fields.
- **Scope.** Store a golden set per project; compute recall@5/MRR on demand and after every re-index;
  show it on the endpoint Overview; **warn** on regression (blocking is a later decision once users
  ask). Out: LLM-judge faithfulness.
- **Steps.** (1) Spec: `POST /v1/projects/{id}/golden` (JSONL upload or an `eval` dataset id),
  `POST /v1/projects/{id}/golden/run` (202 → worker job `kind: rag_eval`),
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
- **Agent.** sonnet · gate class **live (`make golden`)** · serialize with: E4.4/E3.5 (`chat.py`) ·
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

### E5.4 `[BE+FE]` Visual extraction in ingestion: the project's VLM adapter fills structured metadata and re-reads low-confidence pages (P2)
- [ ] **Context.** After E3.3b scanned invoices index with page text and confidence; after E3.4 the
  operator sees `needs_review` pages. The product already trains a VLM extractor for exactly these
  documents (§V, `ocr-vision-walkthrough.md`) and never uses it in ingestion. On CPU the VLM takes
  ≈ 40 s per image (llama.cpp issue #17801) — worker/GPU only.
- **Depends.** E3.3b, E3.4, E3.5, E3.7. **Unblocks.** none.
- **Agent.** sonnet · gate class **gpu** · serialize with: E5.1/E5.2 (`worker/main.py`), E3.4
  (`RagFlow.svelte`) · **Handoff.** must name the `fields` header format.
- **Scope.** A queued `kind: extract` job on the GPU worker: for each page image of a file (or only
  `needs_review` pages) run the project's gated VLM adapter (fallback: the Apache base VLM from E1.2)
  with a project-defined JSON-schema prompt → `chunks.fields JSONB`; replace the page text when OCR
  confidence was below threshold and the VLM output is non-empty; clear `needs_review`. Fields are
  filterable through E3.5's `adapta.filters` and injected as a one-line structured header in the
  chunk. Out: bbox UI, human approval queue, aggregations (say so in the UI; offer a CSV of `fields`).
- **Steps.** (1) Migration `0017_chunk_fields`: `chunks.fields JSONB NULL`,
  `projects.extraction_schema JSONB NULL`. Spec: the project field,
  `POST /v1/projects/{id}/files/{fid}/extract` (202), `GET /v1/projects/{id}/fields.csv`.
  (2) Worker `_run_extract_job` reuses the vision evaluator's loader (`evaluator.py:399-420`) with the
  adapter; prompt = schema + "return JSON only"; parse with the synthesis helper. (3) `rag.py`: header
  injection `"Invoice · {vendor} · {date} · {total}"` when `fields` is present; filters on
  `fields ->> key`. (4) Console: file-row action "Extract fields" (disabled without GPU, tooltip),
  fields drawer, CSV download. (5) Tests: parser + header; dispatch; RBAC.
- **Files.** `migrations/versions/0017_chunk_fields.py`, `specs/openapi.yaml`,
  `adapta/worker/main.py`, `adapta/training/evaluator.py:369-420` (import the loader; do not modify),
  `adapta/services/rag.py`, `adapta/api/v1/files.py`, `adapta/console/src/views/RagFlow.svelte`,
  `tests/test_rag_hybrid.py`, `tests/integration/test_vlm_lora_e2e.py` (one extraction call).
- **Contract impact.** API + DB.
- **Gate.** `make migrate-test` → `make validate-spec` → `make generate` → `make check-models` →
  `make test` → GPU: `test_vlm_lora_e2e.py` extended.
- **Acceptance.** An invoice PNG indexed with low OCR confidence gets `fields = {vendor, total, …}`
  from the project's own adapter, `needs_review` clears, a filtered question ("Qorvex invoices") cites
  only those files, and the CSV lists them.
- **Close.** ocr-vision-walkthrough (final section "Use it in ingestion"), knowledge-and-behavior,
  PRODUCT_DEFINITION Service A (bounded: extraction, not analytics), CLAUDE.md API surface; Status
  snapshot.

### E6. Deferred — recorded, not promised (open a block only when a user asks)
- Guardrails (LLM Guard) · connectors beyond folder/S3 sync · Helm · OIDC · GraphRAG/RAPTOR · ColPali ·
  DPO and hyperparameters in the console (F5) · continued training from an adapter and job
  cancellation (F7) · Grafana dashboards (G4) · rate limiting on `/v1/chat/completions` (G3) · audit
  log/soft-delete (§7.5) · document-level ACL (needs E3.1: `chunks.principals` + a mandatory filter) ·
  Qwen3 family onboarding (new conversion spike).


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
