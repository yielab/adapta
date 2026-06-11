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

Next: **[Consuming the API](consuming-the-api.md)** — wiring a real application
to the endpoint.
