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

## Status snapshot (updated 2026-10-10, after wave 2)

| Area | State |
|---|---|
| Product build (phases 0–5), operator console, image fine-tunes, brand, positioning | ✅ complete — history in [CHANGELOG.md](CHANGELOG.md) |
| Fine-tuning direction | **Decided 2026-10-09: bring your own adapter (§E4).** Training removed 2026-10-10 (E4.1); no service needs a GPU. Import (E4.2) and CPU scorer (E4.3) shipped; the adapter job that gates and serves an import (E4.4) is in flight. |
| SDD gates | Pillar 2 ✅ `make migrate-test` · Pillar 3: the GPU perplexity gate is replaced by the CPU task-metric gate on imported adapters (E4.3/E4.4) · Pillar 1 ✅ `make test-contracts` green (E1.11; re-run 2026-10-10 after E4.1: 32 operations, 1813 cases, 0 failures, authenticated) |
| CI fast gate (`make ci`) | ✅ green 2026-10-10 after E4.1 + E3.2: ruff + mypy clean, 220 unit tests (training tests deleted with the code) |
| **Audit 2026-09-03 (§E)** | 🟥 **open** — 22/37 done (E1.1–E1.9 2026-09-17; E1.14 2026-10-08; E1.10, E1.11, E3.1, E3.8 2026-10-09; E3.2, E3.3a, E3.3b, E3.6, E4.1, E4.2, E4.3, E4.9 2026-10-10). Training gone (CPU-only, one image, 3.27 GB with Docling); retrieval real hybrid + multilingual (golden recall@5 0.978, floor 0.97); scanned PDFs/images via Docling + OCR; adapters import (E4.2) and the CPU scorer exists (E4.3); JSON mode on every endpoint. In flight: E4.4, E3.4, E2.1. Next: E2 (Ollama + launch kit) and E3 (Postgres chunks → real hybrid FTS, Docling + RapidOCR, citations with page/OCR provenance, system prompt + threshold + filters, multilingual, queued indexing, golden set); E4 (adapter import, CPU eval gate, adapter job, promotion/rollback, console flow, import guide, synthesis for eval sets, JSON mode); E5 (contextual retrieval, RAG gate, history-aware retrieval, visual extraction with the vision base). Scheduling: the §E board. |

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
| E1.15 | 3 | sonnet | live | none | E3.5 (`rag.py`), E5.1 (`rag.py`, `worker/main.py`) | open |
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
| E4.8 | 2 | sonnet | live | E3.8, E4.1 | E4.6, E5.1 | open |
| E4.9 | 2 | sonnet | live | E1.11 | E2.1, E3.5/E5.3, E4.6 | done 2026-10-10 |
| E3.4 | 3 | sonnet | live | E3.1, E3.3b, E1.11 | E3.5 (spec, `Playground.svelte`), E3.3b | done 2026-10-10 |
| E3.5 | 3 | sonnet | live | E3.2, E1.11 | E3.4 (spec, `Playground.svelte`), E4.9 and E5.3 | ready-for-live (e3.5) |
| E3.6 | 3 | sonnet + human decision | live | E3.1, E3.2, E3.8 | E3.2 | done 2026-10-10 |
| E4.4 | 3 | sonnet | rebuild + live | E4.2, E4.3 | E3.7, E3.3b | done 2026-10-10 |
| E5.1 | 3 | sonnet | live | E3.1, E3.7, E3.8 | E5.2, E4.8 | open |
| E5.2 | 3 | sonnet | live | E3.8, E3.7, E4.8 | E5.1, E4.5 | open |
| E2.2 | 4 | sonnet | live | E2.1, E4.4 | E4.5 (`endpoints.py`, `EndpointPanel.svelte`) | open |
| E4.5 | 4 | sonnet | live | E4.4 | E2.2, E4.6, E5.2 | open |
| E4.6 | 4 | sonnet | live | E4.4 | E4.5, E4.8, E4.9 | done 2026-10-10 |
| E5.3 | 4 | sonnet | live | E3.2, E3.5, E3.8 | E4.9/E3.5 | open |
| E5.4 | 4 | sonnet | live | E3.3b, E3.4, E3.5, E3.7 | E5.1/E5.2, E3.4 | open |
| E4.7 | 5 | sonnet | offline | E4.4, E4.5, E4.6 | E2.3 (README) | open |
| E2.3 | 6 | haiku | offline | E1.11, E4.7 | E3.2, E3.3b, E4.7 (README) | open |

### E1. P0 — corrections that change the publishable evidence (weeks 1–2)

E1.1–E1.9 shipped 2026-09-17 → [CHANGELOG.md](CHANGELOG.md). E1.14 closed 2026-10-08, E1.10 and E1.11 on 2026-10-09 — wave 0 is done.

### E1.15 `[INFRA+BE]` Survive a hung Chroma — indexing must time out, retry and say so (P0)
- [ ] **Context.** Measured 2026-10-10 on the live stack: the Chroma server (`chromadb/chroma` 1.5.9) stopped
  answering (heartbeat `ReadTimeout` after 10 s, 0 % CPU — deadlocked, not busy) after a contract-gate run plus
  concurrent indexing. The app's retrieval degraded correctly (its 10 s budget → typed 504), but the worker's index
  job blocked **forever** on the Chroma upsert: 1 file `processing`, 29 queued, worker "healthy" (the heartbeat now
  refreshes during a job). `docker restart adapta-chroma` cleared it (52 indexed, 8 failed). An earlier ~20 min worker
  stall the same day (E3.7 follow-up 4) was very likely the same hang. `rag.py` builds `chromadb.HttpClient(host,
  port)` with no timeout (`_get_chroma_client`), and the Chroma 1.x image has no curl, so compose has no healthcheck.
- **Depends.** none. **Unblocks.** nothing formally; every live gate that indexes depends on it in practice.
- **Agent.** sonnet · gate class **live** · serialize with: E3.7 follow-ups (`worker/main.py`, `rag.py`) ·
  **Handoff.** must name the timeout settings, the job-level deadline, how a Chroma hang now surfaces (status,
  `error_message`, metric/log) and the healthcheck command.
- **Scope.** (1) A request timeout on every Chroma client call (`chromadb` HttpClient settings / httpx timeout —
  check what 1.5.9 exposes; a setting `chroma_timeout_seconds`, default ~30 s). (2) A job-level deadline in the
  worker (`asyncio.wait_for` around one index job, setting `index_job_timeout_seconds`, sized from the measured s/page)
  — a timeout is a transient failure (one retry, then `failed` with a clear `error_message`). (3) A compose
  healthcheck for chroma without curl (e.g. `python -c` is absent too — use the `/api/v2/heartbeat` via a bash
  `/dev/tcp` probe or the image's own binary; verify what the image ships). (4) `/health/deep` reports Chroma latency.
  Out: replacing Chroma (E6 records the pgvector option), reproducing the deadlock's trigger.
- **Files.** `adapta/services/rag.py` (`_get_chroma_client`), `adapta/worker/main.py`, `adapta/config.py`,
  `docker-compose.yml` (chroma healthcheck), `adapta/core/health.py`, `docs/reference/OPERATIONS.md` (Chroma section),
  tests.
- **Gate.** `make test` → live: `docker pause adapta-chroma` during an upload → the file ends `failed` with a Chroma
  timeout message within the deadline, the worker keeps taking jobs, `docker unpause` → re-upload indexes; chat during
  the pause → typed 504; compose shows chroma `unhealthy` while paused.
- **Acceptance.** No indexing job can hang longer than its deadline; a paused Chroma is visible in `docker compose ps`,
  `/health/deep` and the file's `error_message`.
- **Close.** OPERATIONS (Chroma troubleshooting: restart command, symptoms); Status snapshot.


### E2. Distribution + launch kit (weeks 2–3)

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
- **Steps.** (1) Migration `0016_project_system_prompt`: `projects.system_prompt TEXT NULL`. Spec:
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
- **Files.** `migrations/versions/0016_project_system_prompt.py`, `adapta/db/models.py:209-262`,
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
- **Done.** (offline, branch `e3.5`) Migration `0016` adds `projects.system_prompt`; spec: `PATCH /projects/{id}`
  (`ProjectUpdate`), `system_prompt` on create/response, `adapta: {top_k, filters}` on the chat request, `citations: []`
  when nothing clears the threshold. `_build_system` = project prompt, RAG block, abstention line, client `system`
  (merged by `split_client_system`). `rag_min_score` (0.2) is applied in `chat._retrieve`, not in `retrieve()`, on
  `RetrievedChunk.score` (vector cosine; reranker sigmoid when on; keyword-only hits exempt). Console: Settings tab, file
  multiselect. Gates: validate-spec, generate, check-models, lint, check-leaks, test (315 passed). NOT run: migrate,
  migrate-test, test-contracts, console-build, `make golden`, live abstention check.
- **Handoff.** Request namespace: `adapta: {top_k?: 1..20, filters?: {file_ids?: [<=50], page_min?, page_max?, needs_review?}}`.
  `_build_system(base, rag, chunks, *, abstain, client_system)` order: project prompt, RAG block (or a no-match line),
  `ABSTENTION_LINE`, client system. Migration revision `0016` (down `0015`). `file_ids` is a Chroma `where` plus SQL on
  the FTS leg; page/review filters are SQL-only (Chroma has no such metadata): FTS leg in SQL, vector leg post-filtered
  over a 4x over-fetch. Also touched `tests/test_contract_edges.py` (405 `Allow` now includes PATCH) and `config.py`.

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
