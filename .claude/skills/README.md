# Skill architecture — how agents work this repo without burning context

Six skills, three shared context files, one rule: **every fact lives in exactly one
place, and is loaded only when the task needs it.**

```
.claude/
  context/                 loaded on demand BY the skills — never all at once
    repo-map.md            where code lives (read instead of grepping)
    gates.md               change type → verification target + the trap list
    doc-surfaces.md        change type → docs that must stay true
  skills/
    feature/               end-to-end change under the three-contract SDD
    verify/                pick + run the cheapest sufficient gate
    docs-sync/             propagate a change through docs + TODO.md
    ship/                  commit discipline
    stack/                 run + debug the live stack (GPU, worker, chroma)
```

## Why it's shaped this way

- **CLAUDE.md is the always-on kernel** (identity, invariants, API surface). It stays
  short. Everything procedural moved into skills so it costs nothing until used.
- **Skills are procedures; context files are lookup tables.** A skill says *what to do
  and in what order*; it points at a context file for the table. No skill restates
  another's content — they cross-reference. That's what keeps a multi-skill turn from
  paying for the same paragraph twice.
- **The three contracts are the quality mechanism**, not review discipline. `feature`
  forces "contract before code"; `verify` proves it; `ship` keeps them in one commit.
  Quality is enforced by gates that run, not by prose telling an agent to be careful.
- **`TODO.md` stays the only source of open work**, so "keep improving" doesn't mean
  re-deriving priorities from the codebase each session.

## The token rules the skills encode

1. Never re-read `CLAUDE.md` — it is already in context.
2. `repo-map.md` before `grep`; scoped `grep` before repo-wide; repo-wide never at root.
3. Read big files in slices (`grep -n` for the anchor, then `sed -n`), never whole
   (`specs/openapi.yaml`, `TODO.md`, long docs).
4. One gate rung at a time — `ci-full` only for release-shaped changes.
5. Edit the stale paragraph, not the whole document.
6. Don't re-read a file you just wrote; the edit tools already failed loudly if it broke.
7. Broad sweeps go to one subagent; keep the conclusion, not the file dump.
8. **The `TODO.md` task block is the unit of context.** Pick up a task by reading its
   block and the files its Files line names — nothing else. A block that needs more than
   that to execute is under-specified: fix the block (one line), don't widen the read.
9. **Close explicitly, then stop.** Every task ends with the block's gate result and a
   ≤ 8-line **Done.** note in `TODO.md`. No drifting into the next task or into
   "while I'm here" edits — those become a `Follow-up.` line or a new block.

## Typical turn

pick task from `TODO.md` → **feature** (contract → code → test) → **verify** →
**docs-sync** → **ship**. Debugging a running system starts at **stack** instead.
Several blocks at once: **orchestrate** (lead reads the §E board, workers run **feature** in
worktrees, the lead serializes live/GPU gates on the main checkout and applies each **Handoff.**).

## Maintaining these

When something structural moves (a module, a gate, a doc surface), update the one
context file that owns it — not the skills, and not `CLAUDE.md` unless the invariant
itself changed. New recurring procedure → new skill; new lookup table → new context file.
