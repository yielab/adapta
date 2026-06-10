# User Guide

This guide is for the **operator** — the technical person who runs Brain From
Cero and sets it up for their organization. You do **not** need to read the
codebase to use it.

If you are deploying the stack for the first time (installing Docker, the GPU
toolkit, downloading a base model), start with the
[README quick start](https://github.com/santiagoyie/brainFromCero#quick-start) —
that covers getting the containers running. This guide picks up **once the stack
is up** and walks through actually using it.

## What you can do

Everything in the product happens inside a **Project**. A project is one of two
types, and the type decides how you specialize the model:

| You want to… | Project type | What you provide | Hardware |
|---|---|---|---|
| Make a model answer **from your documents** | **Knowledge (RAG)** | Documents (PDF, DOCX, TXT, MD, HTML) | CPU |
| Change **how a model behaves** (tone, format, a skill) | **Fine-tuning (LoRA)** | An instruction dataset (or synthesize one from documents) | GPU |

!!! note "These are different mechanisms, not two kinds of 'training'"
    The console never calls RAG "training." When you create a project it asks
    **"How do you want to specialize your model?"** → *Give it knowledge* (RAG)
    vs *Change how it behaves* (fine-tuning). If you're unsure which you need,
    the rule of thumb: **facts the model should look up → Knowledge; a way the
    model should act → Fine-tuning.**

## The two paths, end to end

**Knowledge (RAG):**

```
upload documents → they're indexed → create an endpoint → get an API key
→ your app calls the endpoint → answers come back grounded in your docs, with citations
```

**Fine-tuning (LoRA):**

```
upload (or synthesize) a dataset → start a training job → watch the eval gate
→ if it passes, create an endpoint → get an API key → your app calls the endpoint
```

The fine-tune path has one gate the RAG path doesn't: a trained adapter **cannot
serve until it passes evaluation**. This is deliberate — it's the product's
safety promise that an unverified fine-tune never reaches your users. See
[the eval gate](operator-console.md#the-evaluation-gate) below.

## Where to go next

- **[Operator console](operator-console.md)** — the browser walkthrough for both
  flows, from register to a live endpoint.
- **[Consuming the API](consuming-the-api.md)** — how your applications actually
  call the endpoint with the OpenAI SDK, plus citations and usage.
