# ADR 0001: Adapta as the knowledge assistant inside Tack

## Status

**Proposed** (2026-10-08). Not on the roadmap; no block opened. A separate decision from the
2026-09-03 audit (§E) and from the roadmap/repo cleanup done the same day. Owner: Santiago Yie.

## Context

Two products in the same workspace solve adjacent halves of one problem for a small company:

- **Tack** (`yielab/tack`, MIT) is a self-hosted project manager — one Rust binary, SQLite, embedded
  web UI — that already dispatches board items to coding agents through runners. It exposes a REST
  API (~90 paths, checked-in OpenAPI), an **MCP server** (`tack mcp`: `list_items`, `search_items`,
  `create_item`, `update_item`, `add_comment`, …), signed webhooks, per-item **briefs**, a per-project
  **definition of done**, and `GET /api/items/{id}/agent-context` (what an agent reads for an item:
  profile instructions + title/description + brief + definition of done). Its posture: the board
  never calls into developer machines; runners pull; ambiguous outcomes stop for operator review.
- **Adapta** (`yielab/adapta`, Apache-2.0) is a self-hosted model-customization platform: cited
  hybrid RAG over a company's documents plus gate-checked LoRA adapters, served behind one
  OpenAI-compatible endpoint with scoped `adp_*` keys. Everything stays on the company's servers.

The scenario: a company keeps its documents and institutional knowledge, runs its projects in Tack,
and wants an assistant that (a) answers questions from the company's own documents with citations,
(b) proposes tasks, (c) suggests rules, protocols and definition-of-done text grounded in those
documents, and (d) drafts documentation — all without data leaving the premises.

Constraints inherited from both products:

- Adapta's scope guard (TODO §E): connectors, a second protocol (MCP/Anthropic), guardrails and
  agent frameworks are deferred until a user asks; one dependency over four; reuse what exists.
- Adapta's product definition: **OpenAI-compatible serving is the only external protocol.**
- Tack's single shared Bearer token (no per-user identity yet) and its principle that credentials
  live at a boundary the board does not cross.
- Adapta today has no tool-calling and no JSON mode on the endpoint (roadmap E4.4), and no
  per-project system prompt (E3.5).

## Options considered

1. **Adapta grows a Tack connector** — sync Tack items/attachments into a RAG project and write
   tasks back through Tack's API. Rejected: it is exactly the connector + second-protocol work the
   scope guard defers, it puts Tack credentials inside Adapta, and it makes Adapta aware of one
   specific consumer.
2. **Tack-side assistant panel that talks to Adapta as an ordinary OpenAI-compatible endpoint.**
   Tack adds a settings entry (base URL + `adp_*` key + model slug) and an "Ask the company" panel on
   items/projects. Every call is `POST /v1/chat/completions`; Adapta changes nothing to be usable.
   Proposals (tasks, DoD text, protocol drafts) are rendered as **drafts the human accepts**, then
   written to Tack by Tack itself. Preferred — see Decision.
3. **No product change — a client that holds both.** Claude Code (or any MCP client) with `tack mcp`
   loaded and Adapta reachable as a plain OpenAI endpoint. Works today for the operator's own
   machine, proves the UX, costs zero code, but is per-developer and not a feature a company can
   switch on. Recommended as the **spike** before option 2 is built.

## Decision (proposed)

Adopt **option 2, spiked through option 3**:

- **Direction of calls: Tack → Adapta only.** Adapta never learns about Tack. The integration surface
  is the existing endpoint and key model; the Tack board (or, if the operator prefers, a runner)
  stores the `adp_*` key, mirroring how Tack already keeps provider credentials at a boundary.
- **Knowledge source:** one Adapta RAG project per company (or per Tack project when the corpus
  differs), fed by the documents the company already uploads to Adapta. Tack's own history joins
  the corpus by exporting the project (`GET /api/projects/{id}/export`) and uploading the export as
  a document — no live sync in v1.
- **Behaviour source (optional, later):** an Adapta *behaviour* adapter trained on the company's own
  well-written items, briefs and DoD texts, so proposals arrive in the house style. The composed
  endpoint (knowledge + behaviour) is exactly what Adapta already serves.
- **Four assistant actions, all human-in-the-loop:**
  1. *Answer* — question + optional item context (`agent-context`) → cited answer shown in the panel.
  2. *Propose tasks* — "break this item down" → JSON list of `{title, description, acceptance}` →
     rendered as draft subtasks; accept = Tack's own `subtasks-from-plan` / `create_item`.
  3. *Suggest rules / protocol / DoD* — from the documents → draft for the project's definition of
     done or a brief; accept = `PUT /api/items/{id}/brief` or the project setting.
  4. *Draft documentation* — a page from the corpus + the item's comments → a draft comment or
     attachment, never auto-published.
- **Adapta prerequisites, both already on the roadmap:** **E4.4 JSON mode** (so proposals parse
  reliably without tool-calling) and **E3.5 per-project system prompt + abstention** (so the
  assistant says "not in the documents" instead of inventing a rule). Nothing else is added to
  Adapta for this ADR.

## Consequences

- Positive: zero new protocol or dependency in Adapta; the feature is a thin panel + settings in
  Tack; every write to the board stays a human decision, consistent with Tack's review posture;
  the same endpoint serves other clients unchanged; licensing is compatible (MIT ↔ Apache-2.0).
- Negative: the assistant has no live view of the board beyond what Tack passes in the prompt
  (bounded by Adapta's context-fit guard); task proposals are only as good as the documents; the
  Tack board holds one more secret.
- Explicitly **not built** under this ADR: an Adapta MCP server, a Tack connector in Adapta, an
  agent loop that writes to the board unattended, an approval queue UI, analytics over items,
  multi-company tenancy in Tack.
- If accepted, the work lands as: **Tack** — a settings block + assistant panel + "accept draft"
  actions (its own ADR there); **Adapta** — only E4.4 and E3.5, which are justified on their own.
  The option-3 spike (an afternoon with `tack mcp` + an Adapta key) decides whether the panel is
  worth building.
