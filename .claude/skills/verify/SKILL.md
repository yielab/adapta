---
name: verify
description: Pick and run the cheapest sufficient verification gate for a change in Adapta, and interpret a failing gate. Use before committing, when a make target fails, or when asked to "check", "test", or "run CI" here.
---

# Verify

Read `.claude/context/gates.md` — it is the ladder (change type → target) plus the
trap list. Do not paste it back; act on it.

## Rules

0. **A `TODO.md` task block names its gate.** Run that one first; the ladder below is for
   changes that have no block, or when the named gate cannot observe the change.
1. **Match the gate to the diff.** A docstring change does not need `ci-full`; a spec
   change does need `check-models` + `test-contracts`. Escalate one rung at a time.
2. **In-container.** `docker compose exec app make <target>`. `make up` / `down` /
   `status` / `docs-*` / `console-build` run on the host.
3. **Stack up?** `make status` before anything needing the live server (`test-contracts`,
   integration, e2e). Don't edit repo files while a live run is in flight — hot reload
   restarts uvicorn and kills the run with a fake transport error.
4. **Read the failure, not the whole log.** Pipe: `… 2>&1 | tail -40`, or filter to the
   failing test id, then open only that test and the file it names.
5. **Never weaken a gate to make it pass** — coverage floor, eval threshold, strict docs
   build, `check-leaks`, `check-models` are the product's guarantees. If a gate is wrong,
   say so and fix the gate deliberately as its own change.
6. **Report faithfully.** If a gate was skipped, say which and why.

## Failure → first place to look

| Symptom | Cause |
|---|---|
| `check-models` drift | you edited the spec without `make generate`, or hand-edited generated models |
| `test_generated_models_wired` fails | a router reintroduced a local DTO |
| `check-leaks` fails | a `detail=str(e)` crept back in |
| `lint-imports` fails | a layer violation (api → services → core/db/domain only) |
| `KeyError('_type')` 500 on indexing | chromadb pip/image version skew — `make check-chroma` |
| docs build fails `--strict` | a broken internal link |
| worker behavior unchanged after an edit | worker does not hot-reload — `docker compose restart worker` |
| fine-tune eval scores look different from the recorded ones | training prompt render / label masking changed (§E1.3–E1.4): re-run `tests/integration/test_lora_use_cases.py` on GPU and update `docs/user-guide/fine-tuning-use-cases.md` — never edit the numbers by hand |
| `test_rag_hybrid` passes but a keyword-only chunk is not retrieved live | the sparse leg only re-ranks vector candidates (pre-§E3.2) — expected until the Postgres FTS leg lands |
