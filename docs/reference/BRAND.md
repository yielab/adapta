# 📖 Brand — Brain From Cero

> **Kind:** Reference. This document defines *what the brand is* — name, positioning, voice,
> color, type, and logo. It carries **no open tasks**. The work to apply this system to the
> product lives in the roadmap: [TODO.md §B — Brand rollout](../roadmap.md).
>
> **Single source of truth.** When a color, font, or string here disagrees with the running
> product, the product is wrong — fix the product, not this doc. The design tokens in
> `brain/console/src/tokens.css` and the palette in `mkdocs.yml` are *generated from this page*.

---

## 0. Project status

Brain From Cero is a **one-person project** with a significant portion of its implementation
written using AI-assisted code generation (Claude). It is at **prototype maturity**: the pieces
are all wired up — RAG, LoRA training, eval gate, multi-tenant serving, image-understanding
fine-tunes — but the GPU training path has limited CI coverage, and the system has not been
validated at real team scale or independently audited.

If you're considering deploying this with sensitive data, read the relevant code paths yourself.
AI-generated code is a reasonable starting point, not a correctness guarantee. The auth, error
handling, and eval gate paths in particular deserve independent review.

This is stated here because the product's core promise is data privacy and eval-gated serving.
The gap between what the system does mechanically and what has been independently tested should
be clear upfront.

---

## 1. Brand in one line

**Brain From Cero — private model customization, on your own hardware.**

The name comes from "cero," Spanish for *zero*: you start from a blank slate and build a model
that is entirely yours. It reads as a typo to English speakers — that is a real credibility cost
on first contact. The tradeoff is accepted for now; the name should be explained early rather than
assumed to parse on its own.

### Positioning statement

For teams that can't send training data to a cloud API: run this on your own hardware. Upload
documents for cited retrieval (RAG). Train a LoRA adapter on your data to change how the model
responds. Combine both on the same endpoint. An adapter that doesn't clear the held-out eval gate
is blocked from serving — mechanically, not by policy. No telemetry; embeddings and vectors stay
local.

The specific claim is narrow: **the composition**. RAG tooling is a crowded space (Dify, RAGFlow,
AnythingLLM, many others with large teams and years of production hardening). Fine-tuning tooling
is also crowded (Unsloth, LLaMA-Factory, Axolotl). The combination — retrieval + behavior training
+ eval gate, behind one OpenAI-compatible endpoint, self-hosted — is less crowded. That is the
differentiator, not the individual pieces.

What this is **not**: not a workflow/agent builder, not a deep-document parser, not a chat UI.
It is the model-customization-and-serving layer. Don't enter comparisons the project wasn't
designed to win.

### Taglines

| Use | Line |
|---|---|
| **Primary** (hero, console login, README) | **Your model. Your data. Your servers.** |
| Product idea (sub-hero) | *Build a private brain from zero.* |
| RAG / Knowledge mode | *Give it your knowledge.* |
| Fine-tune / Behavior mode | *Change how it behaves.* |
| Trust / safety (eval gate) | *Nothing unverified ever serves.* |

> The two mode lines are **locked product framing**, not marketing decoration: the UI never calls
> RAG "training." See [PRODUCT_DEFINITION.md](PRODUCT_DEFINITION.md) and the voice rules below.

---

## 2. Voice & tone

The product already has a voice: **developer-direct, precise, assumption-light, never hyped.**
The brand keeps it. We are infrastructure, not a growth-hacked SaaS.

**Principles**

1. **Verbs, not adverbs.** We *upload, index, train, compose, serve, evaluate*. We never
   *unlock, supercharge, harness,* or *empower*.
2. **State the mechanism.** "Held-out eval, response-only loss" beats "trusted AI." Naming the
   machinery *is* the reassurance for this audience.
3. **Privacy is stated flatly, once, and not oversold.** "Your data never leaves your
   infrastructure." No fear-mongering, no badges of compliance we don't have.
4. **Two modes, two questions — never merged.** Specializing a model is always framed as a
   choice between **Give it knowledge** (RAG) and **Change how it behaves** (fine-tuning). Do not
   call RAG "training," do not call fine-tuning "uploading knowledge." This is a product rule.
5. **Errors are honest and typed.** User-facing copy mirrors the `DomainError`
   discipline: a safe, plain message — never a stack trace, never false comfort.
6. **State project maturity plainly.** This is one-person, AI-assisted work at prototype
   maturity. Copy does not claim production-readiness the codebase hasn't earned. Where
   something is early-stage or untested at scale, name it — the audience will find out anyway.

**Voice quick-test** — if a sentence would feel at home in a YC pitch deck, rewrite it.

| ✅ On-brand | 🚫 Off-brand |
|---|---|
| "Index your documents. Answers come back cited." | "Unlock the power of your knowledge base!" |
| "Fine-tuning runs on your GPU. It fails fast if there isn't one." | "Seamlessly supercharge your AI workflows." |
| "An adapter that doesn't clear the eval gate can't serve." | "Enterprise-grade, battle-tested reliability." |
| "Early-stage. Read the auth and eval-gate code before deploying with sensitive data." | "Production-ready, hardened, trusted by teams." |

---

## 3. Color

A dark-first system (the console and docs both default to dark). The palette unifies the two
surfaces that disagree today — the console blue (`#5b8cff`) and the docs deep-purple — onto one
**Indigo** brand hue, and adds the brand's most distinctive idea: **the two modes are color-coded**.

### 3.1 Core

| Token | Hex | Role |
|---|---|---|
| `--brand` (a.k.a. `--accent`) | `#6366F1` | **Indigo** — the one brand color. Buttons, links, focus, active nav, progress. |
| `--brand-weak` | `#1B1F3A` | Indigo tint for selected/active backgrounds on dark. |
| `--brand-ink` | `#FFFFFF` | Text on a solid `--brand` fill. |

### 3.2 The two modes (the signature of the system)

The product's whole shape is *knowledge vs behavior*. Encode it in color so a glance at a project
card tells you what kind of project it is.

| Token | Hex | Mode | Meaning |
|---|---|---|---|
| `--knowledge` | `#2DD4BF` | **Knowledge (RAG)** | Teal = grounded, factual, cited. |
| `--knowledge-weak` | `#0E2E2A` | | tint background |
| `--behavior` | `#A855F7` | **Behavior (fine-tune)** | Purple = learned style/skill. |
| `--behavior-weak` | `#241337` | | tint background |

> Indigo sits *between* teal and purple on the wheel — the brand color is literally the blend of
> the two things the product does. Composition endpoints (RAG **+** adapter) may use a teal→purple
> gradient to signal "both."

### 3.3 Neutrals (dark-first)

| Token | Hex | Role |
|---|---|---|
| `--bg` | `#0E1117` | App background — "ground zero." |
| `--panel` | `#161B22` | Cards, sidebar, topbar. |
| `--panel-2` | `#1E2430` | Inset surfaces, inputs-on-panel, code blocks. |
| `--border` | `#2A313D` | Hairlines. |
| `--text` | `#E6E8EC` | Primary text. |
| `--muted` | `#9AA3B2` | Secondary text, labels. |

### 3.4 Semantic

| Token | Hex | Role |
|---|---|---|
| `--success` (`--green`) | `#22C55E` | Passed eval, healthy, ready. (Distinct from knowledge-teal.) |
| `--warning` (`--amber`) | `#F59E0B` | Pending, degraded, "needs a GPU." |
| `--danger` (`--red`) | `#EF4444` | Failed, destructive, revoke/delete. |

**Contrast:** every text/background pair must clear **WCAG AA (4.5:1)**; large text and non-text UI
clear **3:1**. `--brand` on `--bg` and all semantic colors on their `-weak` tints are AA-verified.
Don't introduce a color outside this table without checking contrast.

---

## 4. Typography

An all-open-source, self-hostable stack (no tracking, works offline — matches the on-prem ethos).

| Role | Family | Notes |
|---|---|---|
| **Display / headings / wordmark** | **Space Grotesk** | Geometric grotesk; engineered, characterful. Weights 500/700. |
| **Body / UI** | **Inter** | Neutral, dense, superb at 13–14px. Weights 400/500/600. |
| **Mono / code / keys / IDs** | **JetBrains Mono** | Already referenced in the console. Weight 400/500. |

`brn_*` API keys, endpoint slugs, model IDs, correlation IDs, and code always render in mono.

**Type scale (console, 14px base):** 22 / 16 / 13 (uppercase, tracked, `--muted`) for h1/h2/h3 —
this matches the existing console rhythm; the change is the *families*, not the sizes.

> **Fallbacks:** keep `Inter, system-ui, …` and `"JetBrains Mono", ui-monospace, …` stacks so the
> UI is correct before webfonts load. Self-host the woff2 files; do not hot-link Google Fonts (an
> on-prem box may have no outbound internet).

---

## 5. Logo & mark

### 5.1 The mark — "the zero node"

A ring (the **cero / 0**) containing three connected nodes — a small network **built from zero**.
The three nodes are colored **brand indigo · knowledge teal · behavior purple**: the mark encodes
the entire product (a brain composed of knowledge + behavior, starting from zero).

It is one flat SVG, legible at 16px (favicon) and on a billboard. This is the canonical source —
generate every raster asset from it:

```svg
<svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="64" height="64" rx="16" fill="#0E1117"/>
  <circle cx="32" cy="32" r="20" stroke="#6366F1" stroke-width="3"/>
  <circle cx="32" cy="20" r="3.6" fill="#2DD4BF"/>   <!-- knowledge -->
  <circle cx="22" cy="40" r="3.6" fill="#6366F1"/>   <!-- brand -->
  <circle cx="42" cy="40" r="3.6" fill="#A855F7"/>   <!-- behavior -->
  <path d="M32 20 L22 40 M32 20 L42 40 M22 40 L42 40"
        stroke="#6366F1" stroke-width="2" stroke-opacity="0.5" stroke-linecap="round"/>
</svg>
```

For a transparent or light-surface variant, drop the `<rect>` and keep the ring + nodes.

### 5.2 The wordmark

**Brain** in Space Grotesk 700 (`--text`), **From Cero** in Space Grotesk 500 (`--muted`) — exactly
the existing split in `Layout.svelte` (`Brain <span>From Cero</span>`), now with the brand face.

```
◐  Brain From Cero
```

- **Lockup:** mark + wordmark, horizontally, mark height = cap height × ~1.4, gap = ½ mark width.
- **Clear space:** at least the ring's diameter on all sides.
- **Minimums:** mark alone ≥ 16px; full lockup ≥ 120px wide.
- **Don'ts:** don't recolor the nodes arbitrarily, don't stretch, don't add a drop shadow, don't
  set the wordmark in another typeface, don't put the dark-badge mark on a busy photo.

### 5.3 Favicon / touch icons

From the mark: `favicon.svg` (modern), `favicon.ico` 32×32 (legacy), `apple-touch-icon.png` 180×180,
and a 512×512 maskable PWA icon. The dark rounded-rect badge variant is the default favicon so it
reads on a white browser tab.

---

## 6. Application surfaces (where the brand lives)

This is the inventory the rollout targets. Details and acceptance live in
[TODO.md §B](../roadmap.md).

| # | Surface | Files | What changes |
|---|---|---|---|
| 1 | **Console tokens** | `brain/console/src/tokens.css` (new), `app.css` | Palette + type tokens become the single source; `app.css` consumes them. |
| 2 | **Console shell** | `components/Layout.svelte`, `views/Login.svelte`, `index.html` | Logo lockup, title/meta/OG, favicon links, theme-color, mode-colored cards. |
| 3 | **Mode color-coding** | project cards, model picker, choice grid | Knowledge=teal, Behavior=purple, composition=both. |
| 4 | **Docs site** | `mkdocs.yml`, `docs/stylesheets/brand.css` (new), `docs/assets/` | Indigo palette, brand fonts, logo, favicon. |
| 5 | **API contract** | `specs/openapi.yaml` (`info` block) | Branded title/description; Swagger UI logo + colors. |
| 6 | **README** | `README.md` | Branded header, tagline, logo, badges. |
| 7 | **Package metadata** | `pyproject.toml` | `description` aligned to the positioning line. |
| 8 | **Voice pass** | console microcopy, empty states, errors | Apply §2 — verbs not adverbs, two-mode framing, honest errors. |
| 9 | **Email (future)** | invite/transactional templates (none exist yet) | When built, inherit this system. Tracked as deferred. |

**Brand string SSOT.** The product name/tagline currently lives in ~14 files. The rollout
centralizes the *console* strings in one `brand.ts` constant and the *server* strings in
`brain/config.py`, so future renames are one edit, not a grep-and-replace.

---

## 7. Quick reference (copy/paste tokens)

```css
:root {
  /* brand */
  --brand: #6366F1; --brand-weak: #1B1F3A; --brand-ink: #FFFFFF;
  --accent: var(--brand); --accent-weak: var(--brand-weak); /* back-compat aliases */
  /* modes */
  --knowledge: #2DD4BF; --knowledge-weak: #0E2E2A;
  --behavior:  #A855F7; --behavior-weak:  #241337;
  /* neutrals */
  --bg: #0E1117; --panel: #161B22; --panel-2: #1E2430;
  --border: #2A313D; --text: #E6E8EC; --muted: #9AA3B2;
  /* semantic */
  --green: #22C55E; --amber: #F59E0B; --red: #EF4444;
  /* type */
  --display: "Space Grotesk", "Inter", system-ui, sans-serif;
  --sans: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --radius: 10px;
}
```
