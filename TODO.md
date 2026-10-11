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
| **Post-audit follow-ups (§F)** | Opened 2026-10-10 from the §E Follow-up lines; **9 of 10 closed 2026-10-10**: extraction `null` + page deadline (F1.1), `migrate-test` on a scratch DB (F1.2), freeform eval sets cannot gate — user decision (F1.3), retrieval deterministic, 0/45 differ across builds (F1.4), teacher-URL SSRF guard (F1.5), counters dropped — migration 0022 (F2.1), job TTL + Ollama client (F2.2), svelte-check clean + training-era proof specs gone (F2.3), condensation measured 0.50 → 0.75 follow-up recall and kept ON — user decision (F3.1). **Open: F1.6** — a second model OOM-kills the app (4 GB). Recovery (watchdog + restart) and a per-load leak fix landed; the 3B can still OOM the app — stopped for review (see the block's Progress). Known: the integration suite truncates the dev DB by design (re-seeds the admin); `alembic check` drift predating 0022. |

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
| F2.2 | 2 | haiku | offline | F1.1 | F1.1 (`worker/main.py`) | done 2026-10-10 |
| F2.3 | 2 | haiku | offline | none | — | done 2026-10-10 |
| F1.4 | 2 | sonnet | live | none | F2.1, F3.1 (`rag.py`) | done 2026-10-10 |
| F2.1 | 3 | sonnet | live | F1.2 | F1.4, F3.1 (`rag.py`, `chat.py`) | done 2026-10-10 |
| F1.3 | 3 | sonnet + human decision | live | none | — | done 2026-10-10 |
| F3.1 | 3 | sonnet + human decision | live | F1.4 | F1.4, F2.1 (`chat.py`, golden harness) | done 2026-10-10 |
| F1.6 | 4 | sonnet | live | none | — | open — stopped after 2 red live runs (see Progress) |

### F1. Correctness

### F1.6 [BE/INFRA] Loading a second model OOM-kills the app, and nothing brings it back
- **Context.** Found in the F2.1 live slot (2026-10-10 23:19 and 23:22, kernel `Memory cgroup out of memory: Killed
  process … python`, anon-rss 3.1 GB): the `app` container has `memory: 4g`; the 1.5B default is preloaded and
  `max_loaded_models = 2` is a *count*, so serving a project on `qwen2.5-3b-instruct` loads it beside the 1.5B and the
  embedding model and crosses the limit. The kernel kills the uvicorn server process; the `--reload` supervisor (PID 1)
  does not respawn it, so the API stops answering while `docker ps` still shows the container healthy for a while.
  A self-hosted operator sees a dead API after the first chat on a bigger base.
- **Scope.** Two halves, both small: (1) never load past the memory the container has — evict by **budget**
  (sum of loaded GGUF sizes + a per-model overhead vs. a budget derived from the cgroup limit or a setting), wrapping
  `model_manager.py` rather than rewriting it; (2) a dead server must not look alive — the container must exit or
  restart when the server process dies (e.g. the healthcheck fails fast and compose `restart: unless-stopped` acts on
  exit, or the entrypoint runs without the reload supervisor outside development). Pick the smallest pair; no new service.
- **Steps.** (1) Reproduce: preloaded 1.5B, then a chat on a 3B project; record RSS. (2) Budget eviction before load;
  measure that the same sequence evicts the 1.5B and survives. (3) Make a killed server visible/recovered; prove it
  by `kill -9` of the server process. (4) Document the memory rule (which bases fit in 4 GB at once).
- **Files.** `adapta/core/model_manager.py` (wrap: a budget check around `_evict_lru_if_needed` / the load path),
  `adapta/config.py`, `adapta/core/memory_budget.py` (new), `adapta/domain/errors.py`, `docker-compose.yml` (restart + budget env), `entrypoint.sh`, `tests/test_model_memory_budget.py`,
  `docs/reference/OPERATIONS.md`.
- **Contract impact.** None.
- **Gate.** live: preloaded 1.5B + chat on a 3B project → 200 and no `Killed process` in `journalctl -k`; `kill -9` of
  the server process → API back within the healthcheck window; `make ci`; `tests/integration/test_rag_e2e.py`.
- **Acceptance.** The F2.1 sequence (adapter e2e, then RAG e2e on 3B) runs twice with no OOM kill; a killed server
  recovers without a human.
- **Close.** OPERATIONS.md (memory sizing); CHANGELOG.
- **Depends.** none.
- **Agent.** sonnet · live · Handoff names the budget setting, its default, and how a dead server now recovers.
- **Progress (2026-10-11, live gate red twice — stopped for review).** Landed on develop (cf14487, c1a9fe3):
  (1) **recovery — green:** `entrypoint.sh` watchdogs `/health` in reload mode and exits after 6 failed probes;
  `app` has `restart: unless-stopped`; measured twice: server killed → container back in ~60 s.
  (2) **budget eviction before load** (`ModelManager._make_room_for`, `adapta/core/memory_budget.py`,
  `ADAPTA_MODEL_MEMORY_BUDGET_MB` = 0 → cgroup limit − `ADAPTA_MODEL_MEMORY_RESERVE_MB` 1024; typed
  `ModelTooLargeForMemory` 503) — evictions fire as designed (`budget 3072 MiB, need 2692 MiB`).
  (3) **leak found and fixed:** the executor Future kept every loaded `Llama` alive, so eviction never freed
  memory (measured in-process: 1.5B unloaded → anon unchanged; `Llama.close()` → freed).
  **Still red:** adapter e2e + `test_rag_e2e` twice → tests pass, but one kill in run 2 at anon-rss 3.57 GB +
  file-rss 2.0 GB, right after the 3B reloaded with every other model evicted; cgroup anon after run 1 was
  2973 MiB. Next: measure in the app process (not a script) what anon remains after each eviction — the KV
  cache/llama scratch of the 3B, the embedder, the chat/eval paths holding a `Llama` reference (handles,
  `_configs`), or glibc not returning freed arenas (`malloc_trim`) — and whether the estimate (×1.15 + 64 KiB/token
  + 256 MiB) undercounts the 3B. Decide then whether a 4 GB app can hold a 3B at all, or the limit/default changes.

### F2. Hygiene

### F3. Measure what shipped on by default

---

## Definition of done (per task)

A task is done only when: (1) its contract changed first if it touches API/schema/model; (2) the relevant gate is **green in CI**, not just locally; (3) no `detail=str(e)` reintroduced; (4) generated artifacts regenerated, not hand-edited; (5) docs updated in the same PR.

---
