---
name: ship
description: Commit work in Adapta — what must land in the same commit, message conventions, and the pre-commit gate. Use when asked to commit, or when a change is finished and verified.
---

# Ship

## One commit = one coherent change

Contract + generated artifact + implementation + test + docs + `TODO.md` tick belong in
the **same** commit. A spec change without its regenerated models, or a feature without
its doc surfaces, leaves `main` untrustworthy between commits.

## Before committing

1. The gate from `.claude/context/gates.md` for this change type — green.
2. `git status --porcelain` + `git diff --stat` — confirm nothing unrelated rode along
   (no `site/`, `node_modules/`, `.venv/`, `data/`, `logs/`, `.coverage`, screenshots).
3. Scan the diff for secrets, absolute local paths, and debug prints.

## Message convention

`type(scope): imperative summary` — matching this repo's history:
`feat(rag):`, `refactor(core):`, `docs(roadmap):`, `security:`, `fix(worker):`.
Body: what changed and **why**, plus the roadmap id (`§D5`, `§A4.7`) when there is one.

**No AI/Claude attribution and no co-author trailer** — this repo's commits are the
user's. Commit straight to the working branch (`develop`/`main` as the user is on);
don't create a branch unless asked.

## After

Say plainly what was committed and what was verified. Don't push, tag, or open a PR
unless asked.
