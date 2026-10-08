---
name: orchestrate
description: Run several TODO.md blocks at once with a lead agent and Sonnet/Haiku workers — pick a wave from the §E board, dispatch each block to a worker in a git worktree, serialize the live/GPU/rebuild gates on the main checkout, collect Done + Handoff notes, merge, re-anchor dependent blocks. Use when asked to run the roadmap, a wave, or "several tasks in parallel"; for a single task use `feature` directly.
---

# Orchestrate — one lead, many workers, one live stack

The unit of work is still a `TODO.md` block (see `feature`). This skill only adds the
scheduling around it. Data lives in `TODO.md` (each block's **Depends.** / **Agent.** lines
and the **§E board**); the gate classes live in `.claude/context/gates.md`. Do not restate
either here — read them.

## 0. The constraint everything follows from

The stack bind-mounts the **main checkout** into `adapta-app` and `adapta-worker`. Any edit
there restarts uvicorn and kills a live test in flight; `make up` restarts every container.
Therefore: **workers build in git worktrees (never bind-mounted, always safe to edit) and run
`offline` gates there; the lead owns the main checkout and runs `live` / `gpu` / `rebuild`
gates one at a time.**

## 1. Lead: read the board, pick the wave

```
grep -n '#### §E board' TODO.md        # then sed -n the table only — not the blocks
```

Eligible rows: every *Depends on* is `done`. Within the eligible set, rows that share a
*Serialize with* entry run one after the other, never together. Cap at **3 workers** at once
(mypy + pytest in three containers is the CPU limit; there is one GPU). Flip each dispatched
row to `in progress (<agent>)` before spawning — that is the lock.

## 2. Dispatch one worker per block

Model = the row's *Tier* (`haiku` rows may run at low effort; `sonnet` rows at normal effort;
`sonnet + human decision` rows run normally but you stop after their numbers come back —
§5). Spawn with `isolation: worktree`. Prompt template — fill the three `<…>`:

```
Block <id> of TODO.md in /home/ox/Sites/brainFromCero. Follow the `feature` skill.
Read ONLY: `grep -n '^### <id> ' TODO.md` → that block (sed -n), then the files its
Files line names, locating by symbol (anchors are hints). Its Depends are done.
You are in a git worktree, not the live stack. Run only the offline rungs of the gate
(the worktree command in .claude/context/gates.md "Gate classes"); do NOT run live,
GPU or `make up` gates and do not start containers — the lead runs those after merge.
Edit only the block's Files, the block itself and its board row. Do not touch the
Status snapshot, other blocks, or CLAUDE.md. No pip install.
Finish with, in this order: (1) `git diff --stat`; (2) offline gate commands + results;
(3) a draft **Done.** (≤ 8 lines); (4) a draft **Handoff.** naming <what the block's
Agent line says it must name>; (5) anything out of scope as one Follow-up line.
Commit on your worktree branch with the `ship` conventions, then stop.
```

For a block whose gate class is `offline`, the worker's green gate is the gate: merge and
close (§4) without a live slot.

## 3. Collect — scope check before anything else

When a worker returns: compare its `git diff --stat` with the block's Files line. A file
outside it needs the one-line reason in the Done draft; otherwise send the worker back.
Merge the worktree branch into the working branch on the main checkout (rebase, then
fast-forward). A merge conflict means the board's *Serialize with* column was wrong — fix the
column, resolve, continue.

## 4. The live slot — one block at a time on the main checkout

Freeze: no other merge or edit lands on the main checkout until this gate finishes. Run the
block's gate exactly as its Gate line says (`stack` skill for the mechanics; `worker` needs
`docker compose restart worker` after any `adapta/training/` or `adapta/worker/` change;
`rebuild` means `make up` first). Reading a gate's output is mechanical — a Haiku may run and
report it. Then:

- **Green** → paste the result into the Done note, write **Done.** and **Handoff.** into the
  block, move the block to `CHANGELOG.md` (top dated section), flip the board row to
  `done YYYY-MM-DD`, commit (`ship`: contract +
  generated artifact + code + tests + docs + TODO tick in one commit).
- **Red** → `SendMessage` the *same* worker with the failing output (its context is intact);
  it fixes in its worktree; back to §3. Never patch a worker's block on the main checkout
  yourself — two authors on one block is how handoffs get lost.

## 5. After each close — the handoff is applied by the lead

1. Read the block's **Handoff.** line (now in `CHANGELOG.md`). For every block it *Unblocks*, re-anchor that block's
   Files line (symbol names, real migration revision, renamed config keys) — one-line edits.
2. `sonnet + human decision` rows (E3.3a, E3.6): present the measured numbers to the user
   verbatim and wait. Nothing that depends on the decision is dispatched until they answer.
3. Once per wave, not per block: refresh the Status snapshot §E row + its date.

## 6. Stop conditions

Stop and report (do not improvise) when: a live gate is red twice for the same block; a
worker's diff reaches a file two running blocks both name; `make up` would be needed while
another block is `in progress` on a `live` gate; or the user's decision in §5.2 is pending.

## Definition of done (per wave)

Every dispatched row is `done` or back to `open` with a Follow-up line · each closed block has
Done + Handoff · dependent Files lines re-anchored · one commit per block · Status snapshot §E
row refreshed once · no root-owned files in the main checkout (`--user` in the worktree command).
