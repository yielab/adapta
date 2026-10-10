# User Guide

This guide is for the **operator** — the technical person who runs Adapta
and sets it up for their organization. You do **not** need to read the
codebase to use it.

If you are deploying the stack for the first time (installing Docker,
downloading a base model), start with the
[README quick start](https://github.com/yielab/adapta#quick-start) —
that covers getting the containers running. This guide picks up **once the stack
is up** and walks through actually using it.

## What you can do

Everything in the product happens inside a **Project**. A project is one of two
types, and the type decides how you specialize the model:

| You want to… | Project type | What you provide | Hardware |
|---|---|---|---|
| Make a model answer **from your documents** | **Knowledge (RAG)** | Documents (PDF, DOCX, TXT, MD, HTML) | CPU |
| Change **how a model behaves** (tone, format, a skill) | **Finetune (adapter)** | An eval set (or synthesize one from documents) and an adapter to import (import converts and gates it on CPU) | CPU |

The platform never generates images; vision base models can read them (see
[Consuming the API](consuming-the-api.md#images-vision-endpoints)).

!!! note "These are different mechanisms, not two kinds of 'training'"
    The console never calls RAG "training." When you create a project it asks
    **"How do you want to specialize your model?"** → *Give it knowledge* (RAG)
    vs *Change how it behaves* (adapters). If you're unsure which you need,
    the rule of thumb: **facts the model should look up → Knowledge; a way the
    model should act → Adapter.**

## The two paths, end to end

**Knowledge (RAG):**

```text
upload documents → they're indexed → create an endpoint → get an API key
→ your app calls the endpoint → answers come back grounded in your docs, with citations
```

**Finetune (adapter):**

```text
upload (or synthesize) an eval set → import an adapter → it must pass the eval gate
→ create an endpoint → get an API key → your app calls the endpoint
```

In-product training was removed on 2026-10-10. Adapters are imported instead, and
the import and its CPU eval gate run on every upload; a finetune endpoint
exists once an adapter has passed the gate. The gate is the product's safety promise that an
unverified adapter never reaches your users. See
[the eval gate](operator-console.md#3b-adapter-finetune-flow) and the
[bring-your-own-adapter guide](bring-your-own-adapter.md) (what to import, how it is scored).

**Both together (the production pattern):** a finetune project can *also*
index documents. Its endpoint then answers **from your documents, in your
adapter's voice and format** — facts from retrieval (with citations), form from
the adapter, in one call. See
[Knowledge + behavior together](knowledge-and-behavior.md) for a worked
real-life example.

## Where to go next

- **[Operator console](operator-console.md)** — the browser walkthrough for both
  flows, from register to a live endpoint.
- **[Knowledge + behavior together](knowledge-and-behavior.md)** — when to use
  RAG vs adapters (real-life cases) and the combined pattern end to end.
- **[Migrating to Adapta](migrating.md)** — coming from Flowise, Cognita or R2R, or from a setup that
  trained adapters for you: concept mapping, what has no equivalent, and the API path.
- **[Consuming the API](consuming-the-api.md)** — how your applications actually
  call the endpoint with the OpenAI SDK, plus citations and usage.
