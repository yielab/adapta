---
name: docs-sync
description: Propagate a shipped change through Adapta's documentation surfaces and the TODO.md roadmap without duplicating prose or drifting from the code. Use after implementing anything user-visible, when asked to "document X", or to open/close/re-scope a roadmap task.
---

# Docs & roadmap sync

Read `.claude/context/doc-surfaces.md` for the change-type → files matrix. Touch the
rows that apply, and nothing else.

## Two invariants

- **📖 Reference describes what is; 🗺 `TODO.md` is the only place with open work.**
  Never put a task in a reference doc; never let `TODO.md` re-describe architecture —
  link to the reference instead.
- **Never hand-write generated docs.** `docs/reference/api.md` comes from
  `specs/openapi.yaml`; `docs/developer-guide/code-reference.md` comes from docstrings.
  Improve the source.

## Editing discipline (this is where tokens get burned)

- Locate the stale paragraph with `grep -n` and rewrite **that paragraph**. Do not read
  or regenerate a whole doc to change one fact.
- Prefer one sentence + a link over restating an explanation that already exists elsewhere.
  If the same fact now lives in two docs, delete one and link.
- Dates are absolute (`2026-06-26`), never "recently".
- Check the claim against the code before writing it — docs here have historically
  overstated status.
- Don't create new `.md` files unprompted; extend an existing surface.

## Roadmap operations

- **Opening a task:** add it under the right section with the eight fields the file's
  "How to pick up a task" defines — Context (with `file:line` evidence), Scope (in **and**
  out), Steps, Files (exact paths + line anchors; this is the agent's read budget),
  Contract impact, Gate (one make target chosen from `.claude/context/gates.md`),
  Acceptance (observable), Close (which doc surfaces from `doc-surfaces.md`). Written so
  an agent with no prior context can execute it by reading **the block and its Files only**.
  A block longer than ~20 lines is two tasks.
- **Closing a task:** append `— ✅ DONE (YYYY-MM-DD)` to the heading, add **Done.** (≤ 8 lines: what
  changed · gate run + result · skipped items + why) and **Handoff.** (what downstream blocks must now
  use), then **move the whole block to `CHANGELOG.md`** under the top dated section (create one for
  today if needed), flip its §E board row to `done YYYY-MM-DD`, and refresh the **Status snapshot**
  row + date. History is kept in the changelog, never deleted. Noticed-but-out-of-scope work becomes
  one `- **Follow-up.**` line under the board or a new block — never silent extra diff.
- **Legend:** `[x]` done & verified · `[~]` partial/not wired · `[ ]` not started.
  P0 blocks a trustworthy `main` · P1 before first customer · P2 nice-to-have.

## Finish

`make docs-build` on the host — `--strict`, so a broken internal link fails the CI fast gate.
