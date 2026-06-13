# Operator console

The console is a browser UI bundled **inside the `app` container** — no extra
service, no extra port, no install. Once the stack is running, open:

```
http://<your-server>:8000/console/
```

(The bare `/` redirects there.) Everything below can also be done with raw API
calls — the console is a convenience over the same API your applications use.

---

## 1. First run: sign in or register

The first screen offers **Sign in** and **Register**. On a development stack a
default admin is already seeded (`admin@example.com` / `admin12345` — disable
with `BRAIN_SEED_DEFAULT_ADMIN=0`), so you can sign in immediately.

Registering creates a **new organization with you as its admin** — fill in an
org name, email, and password. After that, you land on the **Projects** page.
Additional team members join an existing organization via invitations (an admin
issues a one-time invite token; the new user redeems it to set a password and
join the team).

The top bar shows your user and a **team switcher** — projects are always scoped
to the active team.

---

## 2. Create a project

Click **New project**. The console asks **"How do you want to specialize your
model?"**:

- **Give it knowledge (RAG)** — for answering from your documents.
- **Change how it behaves (fine-tuning)** — for tone/format/skill.

Pick one, name the project, and choose a **base model** from the catalog (e.g.
a Qwen2.5 model). The base model is the foundation both paths build on.

The project card then opens to the flow for its type, with tabs: **Setup**,
**Endpoint & keys**, **Playground**, and **Usage**. Tabs stay disabled until
their prerequisites are met (e.g. you can't open the Playground before an
endpoint exists).

---

## 3a. Knowledge (RAG) flow

In the **Setup** tab:

1. **Upload documents** — drag-and-drop PDF, DOCX, TXT, MD, or HTML files. Each
   file is parsed, split into chunks, embedded, and stored in this project's
   private vector collection in the background.
2. **Watch the status** — each file moves `pending → processing → indexed` (or
   `failed` with a reason). The **Create endpoint** button stays disabled until
   at least one file is `indexed`.
3. **Create endpoint** — once you have indexed documents, create the endpoint.
   RAG has **no eval gate** — the model's weights aren't changing, so there's
   nothing to verify. You go straight to keys.

What you get: a model that answers **grounded in your documents, with
citations** — the source chunks it used are returned alongside the answer.

---

## 3b. Fine-tuning (LoRA) flow

In the **Setup** tab:

1. **Documents (optional)** — upload PDF/DOCX/TXT/MD/HTML, same as the RAG
   flow. They do two jobs: they are the source the **Synthesize** button reads,
   and once your endpoint is live the model **answers from them with
   citations** — knowledge from the documents, behavior from the fine-tune.
   See [Knowledge + behavior together](knowledge-and-behavior.md).

2. **Provide a dataset** — either:
    - **Upload JSONL** — one instruction pair per line (`{"prompt": "...",
      "response": "..."}`, optional `system`). The file is validated against the
      dataset schema; rows that don't match are reported.
    - **Synthesize** — generate a dataset automatically from the documents you
      indexed in step 1. The platform turns your document chunks into Q/A pairs.
      This runs in the background; poll until it's ready.

    A dataset must have at least a minimum number of samples (default 10) before
    you can train on it.

    **Vision projects** (a base model labeled *vision* in the create dialog)
    upload a **`.zip` bundle** instead: your images plus one `data.jsonl`
    manifest whose rows add `"images": ["images/photo.png"]` (exactly one
    bundle-relative path per row). The console's collapsible help in the
    dataset step shows the full layout and caps; the served endpoint then
    accepts images — see
    [Image understanding](knowledge-and-behavior.md#image-understanding-vision-fine-tunes).
    Synthesize is text-only and hidden for vision projects.

3. **Start a training job** — enqueue it. A GPU worker picks it up. The job
   moves `queued → running → succeeded | failed` with a live progress bar and a
   tail of the training log.

4. **The evaluation gate** — see the dedicated section below. This is the step
   that decides whether the fine-tune is allowed to serve.

5. **Create endpoint** — enabled **only** once a job has succeeded **and** passed
   the eval gate. The endpoint serves the base model **with your trained
   adapter** applied — and, if you indexed documents in step 1, it also injects
   retrieved context and returns citations in the same call.

---

## The evaluation gate

This is the heart of the fine-tune flow and worth understanding, because it's
what protects your users from a bad fine-tune.

When training finishes, the worker scores the adapter on a **held-out slice of
your dataset it never trained on** — the same way you'd judge a student on
questions that weren't on the study sheet. The console shows the score and a
bold **PASSED** or **BLOCKED**.

An adapter **passes** if **either**:

- it clears an **absolute quality bar**, **or**
- it clearly **beats the base model** on that same held-out slice (a smaller
  base model can't always hit the absolute bar even on an ideal task, but a
  fine-tune that reliably out-performs its starting point has demonstrably
  learned the target behavior).

If it passes neither, **Create endpoint is disabled** with the reason shown —
the adapter is not registered and there is no way to serve it. This mirrors the
API's `EvalGateFailed (422)`.

!!! info "Why this gate exists"
    Fine-tuning can silently produce a worse model. Without a gate, you'd only
    discover that in production. The gate is the model-world equivalent of a CI
    test suite: nothing ships until it passes. The technical details of how the
    score is computed are in the Developer Guide's
    [Learning the system](../developer-guide/learning-the-system.md#the-eval-gate-ci-for-a-model)
    page.

---

## 4. Endpoint & keys — the handoff

In the **Endpoint & keys** tab:

- The **endpoint card** shows the endpoint **slug** — this is the value your
  application passes as the OpenAI `model` name.
- **Create a key** — you get a `brn_…` key. **The full key is shown exactly
  once**, on creation. Copy it then; afterward only a masked prefix is visible.
  Keys are scoped to this one endpoint.
- A **copy-paste OpenAI SDK snippet** is generated with this server's URL, the
  slug, and the key filled in — the bridge to the real API.

You can create multiple keys and **revoke** any of them; a revoked key stops
working immediately.

---

## 5. Playground

The **Playground** tab lets you test the endpoint from the browser using a
console-held key — the exact same request path a customer app uses. For RAG
projects it shows the **citations**; for all projects it shows **token usage**
(prompt / completion / total). It's a test tool, clearly labeled as such.

---

## 6. Usage

The **Usage** tab shows daily token rollups (newest first) and totals for the
endpoint, so you can see consumption over time.

---

---

## 7. Models catalog

The **Models** page (sidebar → *Models*) shows every base model the server knows
about and — crucially — whether it is **available** (the GGUF file is present on
the server). One entry per model, with:

- **Modality badge** — `text` or `vision`.
- **Purpose** (use-case line) and **Best for** chips — e.g. *knowledge retention*,
  *code*, *vision*.
- **Resource requirements** — approximate VRAM needed to train and RAM needed to
  serve, derived from the model's spec entry.
- **Availability status** — green *Ready* if the GGUF is on disk; amber *Not
  available* if the model is in the catalog but the file hasn't been downloaded
  yet (see [Downloading models](../reference/OPERATIONS.md)).

When you select a base model in the **New project** dialog the same information
appears as a live detail panel below the dropdown, so you can check requirements
before committing. Models that are not available are listed as disabled options —
they appear in the picker so you can see what's on offer, but the *Create* button
stays disabled until you choose one that is ready.

---

## 8. Project overview

Every project card on the Projects page carries a **stage indicator** — a
colored dot and label derived from the project's current state:

| Stage | Meaning |
| --- | --- |
| **Setting up** | Project just created, no data yet. |
| **Awaiting data** | No files or datasets uploaded. |
| **Indexing** | Documents processing in the background. |
| **Training** | A training job is running. |
| **Gate blocked** | Training finished but the eval gate was not passed. |
| **Ready to serve** | A gate-passed adapter exists; endpoint not yet created. |
| **Live** | Endpoint is active and serving. |

A **next-action hint** below the label tells you what to do next ("Upload
documents", "Start a training job", etc.).

Inside the project, the **Overview** tab gives the full picture at a glance:

- **Pipeline checklist** — which steps are done (documents indexed, dataset
  uploaded, job run, gate passed, endpoint created, key generated). Each
  incomplete step has a call-to-action link to the right tab.
- **Latest training job** verdict — eval score, gate outcome (absolute or
  improvement), and improvement over base if applicable.
- **Endpoint snapshot** — slug, status, model composition (base + adapter + retrieval
  layer), indexed-chunk count, active-key count.
- **7-day usage** — request and token totals.

The Overview tab is always visible, even for an empty project, so you can orient
yourself and find the next step without hunting through tabs.

---

## 9. Settings

The **Settings** section (sidebar → *Settings*) has four tabs.

### Account

Change your password. Enter your current password to confirm, then set a new one
(minimum 8 characters). The change takes effect immediately.

### Team

- **Members table** — all users in the team, their email addresses, roles, and
  join date. Anyone in the team can see this; only admins can invite people.
- **Invite a member** — enter an email, pick a role (`admin`, `member`, or
  `viewer`), and click *Send invite*. A one-time token is shown. Deliver it
  out-of-band to the new user; they redeem it at the console's *Accept invite*
  screen to set their password and join the team.
- **Pending invitations** — tokens that have been issued but not yet redeemed,
  with their expiry times.

**Roles:**

| Role | Projects | Files / datasets / jobs | Endpoint / keys | Platform settings |
| --- | --- | --- | --- | --- |
| admin | read + write | read + write | read + write | read + write |
| member | read + write | read + write | read + write | read-only |
| viewer | read-only | read-only | read-only | read-only |

### Platform settings

Per-team inference knobs (temperature, top-k, chunk size, RAG hit count, etc.).
Each setting shows its current value, the *source* (override you set here,
environment variable, or built-in default), and the allowed range.

Admins can set an override that replaces the env/default for this team's
endpoint. Click *Reset* to remove the override and fall back to the env value or
default. The settings page deliberately **does not expose the eval-gate threshold**
— that is a platform invariant, not an operator knob.

Priority order: DB override > environment variable > built-in default.

### System

Read-only status dashboard: Postgres, Redis, Chroma connectivity, disk usage,
and memory usage — the same signals as `GET /health/deep` presented visually.
GPU detection result is also shown here, so you can confirm that the worker has
the accelerator it needs without opening logs.

---

Next: **[Consuming the API](consuming-the-api.md)** — wiring a real application
to the endpoint.
