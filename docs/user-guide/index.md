# User Guide

This guide is for the **operator** — the technical person who runs Adapta
and sets it up for their organization. You do **not** need to read the
codebase to use it.

If you are deploying the stack for the first time (installing Docker, the GPU
toolkit, downloading a base model), start with the
[README quick start](https://github.com/yielab/adapta#quick-start) —
that covers getting the containers running. This guide picks up **once the stack
is up** and walks through actually using it.

## What you can do

Everything in the product happens inside a **Project**. A project is one of two
types, and the type decides how you specialize the model:

| You want to… | Project type | What you provide | Hardware |
|---|---|---|---|
| Make a model answer **from your documents** | **Knowledge (RAG)** | Documents (PDF, DOCX, TXT, MD, HTML) | CPU |
| Change **how a model behaves** (tone, format, a skill) | **Fine-tuning (LoRA)** | An instruction dataset (or synthesize one from documents) | GPU |
| Make a model **read your images** (invoices, forms, QC photos) | **Fine-tuning (LoRA)** on a *vision* base model | A `.zip` bundle of image + prompt → response examples | GPU |

Image *understanding* only — the platform never generates images. See
[Image understanding](knowledge-and-behavior.md#image-understanding-vision-fine-tunes)
for the bundle format and a worked example.

!!! note "These are different mechanisms, not two kinds of 'training'"
    The console never calls RAG "training." When you create a project it asks
    **"How do you want to specialize your model?"** → *Give it knowledge* (RAG)
    vs *Change how it behaves* (fine-tuning). If you're unsure which you need,
    the rule of thumb: **facts the model should look up → Knowledge; a way the
    model should act → Fine-tuning.**

## The two paths, end to end

**Knowledge (RAG):**

```text
upload documents → they're indexed → create an endpoint → get an API key
→ your app calls the endpoint → answers come back grounded in your docs, with citations
```

**Fine-tuning (LoRA):**

```text
upload (or synthesize) a dataset → start a training job → watch the eval gate
→ if it passes, create an endpoint → get an API key → your app calls the endpoint
```

The fine-tune path has one gate the RAG path doesn't: a trained adapter **cannot
serve until it passes evaluation**. This is deliberate — it's the product's
safety promise that an unverified fine-tune never reaches your users. See
[the eval gate](operator-console.md#the-evaluation-gate) below.

**Both together (the production pattern):** a fine-tune project can *also*
index documents. Its endpoint then answers **from your documents, in your
trained voice and format** — facts from retrieval (with citations), form from
the adapter, in one call. See
[Knowledge + behavior together](knowledge-and-behavior.md) for a worked
real-life example.

## Where to go next

- **[Operator console](operator-console.md)** — the browser walkthrough for both
  flows, from register to a live endpoint.
- **[Knowledge + behavior together](knowledge-and-behavior.md)** — when to use
  RAG vs fine-tuning (real-life cases) and the combined pattern end to end.
- **[Consuming the API](consuming-the-api.md)** — how your applications actually
  call the endpoint with the OpenAI SDK, plus citations and usage.
