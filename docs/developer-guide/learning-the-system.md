# Learning the system

> **Who this is for.** You're a competent backend developer — you've built APIs,
> run databases, used job queues, written migrations, set up CI. But the
> ML-specific parts of this codebase (embeddings, vector stores, LoRA, GGUF,
> quantization, eval gates) are unfamiliar. This page teaches them from the
> ground up by mapping each one onto something you already know.

The reassuring thesis up front: **you already understand ~90% of this system.**
It's a FastAPI service, a Postgres database, a Redis job queue, and a background
worker. The other 10% is a set of ML concepts that each have a clean analogy to
ordinary infrastructure. We'll build those up one at a time.

---

## 1. What a language model actually is

Forget "AI." Mechanically, a language model is a **pure function**:

```
f(text_so_far) → probability distribution over the next token
```

You give it some text, it tells you how likely every possible "next chunk of
text" is. To generate a sentence, you call it in a loop: predict the next chunk,
append it, predict again. That's it. There's no database lookup, no reasoning
engine — just a very large mathematical function evaluated repeatedly.

!!! analogy "It's autocomplete with a PhD"
    Your phone's keyboard suggests the next word from the last few words. A
    language model does the same thing, but conditioned on the entire
    conversation and trained on a huge corpus. "Generating a response" is just
    autocomplete run forward, one chunk at a time, until it predicts a "stop"
    token.

The "very large function" is defined by its **weights** — billions of numbers
fixed at training time. Running the function is called **inference**. (Compare:
*compiling* a program is expensive and done once; *running* it happens
constantly. Training ≈ compiling; inference ≈ running.)

### Tokens — the unit of text

Models don't see characters or words; they see **tokens** — sub-word pieces. The
tokenizer splits text into these pieces, each mapped to an integer.

- Common words are usually one token: `"the"` → 1 token.
- Rare or made-up words get split: an invented word like `"Zorptania"` might
  cost 4 tokens, because the model has never seen it and has to spell it out of
  smaller pieces.

!!! analogy "Tokens are like syllables, and rare words are like spelling out loud"
    You read "cat" as one unit but spell "Zorptania" letter-cluster by
    letter-cluster. The model is the same. This matters in practice: token count
    drives cost, context limits, and — as you'll see in the [eval gate](#the-eval-gate-ci-for-a-model)
    — how hard a made-up answer is to learn.

Every response in this product reports `prompt_tokens` / `completion_tokens` /
`total_tokens` for exactly this reason — tokens are the currency.

### GGUF and quantization — the model as a deployable artifact

The model's weights have to live in a file. We serve models in **GGUF** format,
run by the **llama-cpp** engine.

- **GGUF** is a single-file packaging of the weights plus metadata.
  - *Analogy:* it's a **compiled binary** of the model. `llama-cpp` is the
    runtime that loads and executes it — like the JVM running a `.jar`.
- **Quantization** is storing each weight at lower precision (e.g. 4 bits
  instead of 16) to shrink the file and the memory footprint, trading a little
  accuracy for a lot of size. A `Q4_K_M` model is "4-bit quantized."
  - *Analogy:* it's **JPEG for model weights.** A RAW photo is huge and
    pixel-perfect; a JPEG is a fraction of the size and almost indistinguishable.
    Quantization does the same to a model — a 3B model that would need ~12 GB at
    full precision fits in ~4 GB at 4-bit, with minor quality loss.

This is why an 8 GB consumer GPU can serve a model that "should" need far more:
it's running the JPEG, not the RAW.

### Inference: one chef, one cutting board

`llama-cpp`'s model object holds mutable internal state during generation (a
"KV cache" — think of it as the scratchpad it uses to remember the conversation
so far). **It is not safe to call concurrently on a single model instance.**

!!! analogy "One chef, one cutting board"
    Two chefs sharing one cutting board mid-chop will collide. Two requests
    hitting one model instance's scratchpad simultaneously corrupt each other —
    you get garbage output or a crash. The fix isn't to rewrite the chef; it's
    to make them **take turns**.

That's exactly what the code does: a **per-model `asyncio.Lock`** serializes
generation on each model instance (`brain/core/model_manager.py`,
`brain/core/inference.py`), the actual generation runs on a **bounded thread
pool** (so it doesn't block the async event loop), and a **timeout** caps each
call. The model cache is an LRU with a bound, so N endpoints don't OOM the box
by each pinning a full model in RAM. None of this is ML — it's ordinary
concurrency engineering around a non-thread-safe resource, the same as guarding
any shared mutable handle.

---

## 2. The two ways to specialize a model

A base model is a generalist. Customers need a specialist. There are two
fundamentally different ways to get there, and **conflating them is the #1
conceptual mistake**:

| | Give it **knowledge** (RAG) | Change its **behavior** (fine-tuning) |
|---|---|---|
| Question it answers | "What do *our documents* say?" | "How should the model *act*?" |
| Changes the weights? | **No** | **Yes** (via an adapter) |
| Analogy | An **open-book exam** | **Studying until it's second nature** |
| Input | Documents | Instruction examples (prompt→response) |
| Cost | Seconds, CPU | Minutes–hours, GPU |
| Reversible? | Delete a file, re-index | Re-train the adapter |

!!! tip "The rule of thumb"
    **Facts the model should look up → Knowledge (RAG).** **A way the model
    should behave → Fine-tuning.** "Answer from our 500-page handbook" is RAG.
    "Always reply in our terse, bulleted support voice" is fine-tuning.

---

## 3. Knowledge (RAG), from first principles

**RAG = Retrieval-Augmented Generation.** The model itself doesn't memorize your
documents. Instead, at question time we **find the relevant passages and hand
them to the model as context**, then ask it to answer using them.

!!! analogy "An open-book exam with a great research assistant"
    You don't memorize the textbook. When a question comes, an assistant
    instantly flips to the three most relevant pages, lays them in front of you,
    and you answer from what's on the page. The model is the student; retrieval
    is the assistant. The model's "knowledge" is whatever you put on the desk.

To make "find the relevant passages" work, we need two ML building blocks.

### Embeddings — coordinates for meaning

An **embedding** is a function that turns a piece of text into a vector (a list
of ~384 numbers) such that **texts with similar meaning land near each other** in
that vector space.

!!! analogy "GPS coordinates for meaning"
    Imagine a map where every sentence has a location, and sentences about the
    same topic cluster together — "refund policy" and "money-back guarantee" end
    up as neighbors even though they share no words. An embedding model assigns
    those coordinates. (Contrast a hash function, which scatters similar inputs
    to *unrelated* outputs on purpose. An embedding is the opposite: similar in
    → close out.)

In this codebase, `brain/services/embeddings.py` wraps a `sentence-transformers`
model that produces these vectors, lazily loaded as a singleton.

### Vector store — a database indexed by meaning

A normal database index lets you look up rows by exact value (a B-tree on
`user_id`). A **vector store** lets you look up by **nearest neighbor in meaning**
— "give me the chunks whose embeddings are closest to this query's embedding."
We use **ChromaDB**, one collection per project.

!!! analogy "A library card catalog organized by topic, not title"
    A title index finds a book only if you know its exact name. A topic-organized
    catalog finds books *about* what you asked, even with different words. The
    vector store is that catalog; the "closeness" search (approximate
    nearest-neighbor) is the librarian walking to the right shelf.

### The full RAG loop

Putting it together (`brain/services/rag.py`, `brain/services/chat.py`):

```
INDEX TIME (once, when a file is uploaded):
  document → parse → split into chunks → embed each chunk → store vectors in Chroma

QUERY TIME (every chat request):
  question → embed it → find nearest chunks in Chroma → inject them as context
           → model generates an answer grounded in those chunks → return with citations
```

The **citations** are simply: we know which chunks we put on the desk, so we
return them. The model isn't asked to invent sources — it's handed them.

Two practical guards you'll see in the code, both ordinary engineering:
retrieval runs **off the event loop under a timeout** (a hung vector DB degrades
to a `504`, it doesn't freeze every request), and the assembled prompt is
**fitted to the model's context window** — if it won't fit, the lowest-relevance
chunks are dropped first rather than silently truncating the question.

---

## 4. Fine-tuning (LoRA), from first principles

Fine-tuning changes *how the model behaves* by adjusting its weights from
examples. But fully retraining a multi-billion-parameter model is wildly
expensive. **LoRA** (Low-Rank Adaptation) is the trick that makes it cheap.

!!! analogy "Sticky-note patches instead of rewriting the textbook"
    Full fine-tuning rewrites the entire textbook to teach one new habit —
    enormous and wasteful. LoRA leaves the textbook (the base weights) untouched
    and writes a **thin stack of sticky-note corrections** that get applied on
    top. The notes (the "adapter") are tiny — a few megabytes against a
    multi-gigabyte model — but they're enough to shift behavior.

In software terms: **the base model is a large read-only dependency, and a LoRA
adapter is a patch/diff applied over it at load time** — like a plugin, or a
git patch, or a CSS override. You ship the small patch, not a new copy of the
whole thing.

### QLoRA — training against a compressed base

**QLoRA** = LoRA where the frozen base model is **quantized to 4-bit** during
training (recall the JPEG analogy). This is what lets a real fine-tune fit on an
8 GB consumer GPU: you only compute gradients for the small adapter, and you hold
the giant base in its compressed form. `brain/training/trainer.py` runs this with
PEFT/TRL.

### The dataset — labeled examples

The training input is an **instruction dataset**: a JSONL file where each line is
a `{prompt, response}` pair (optionally a `system` message). This is just
**labeled training data** — input → desired output — the same shape as any
supervised-learning task you've seen. The product can also **synthesize** a
dataset from your indexed documents (turn chunks into Q/A pairs) so you don't
have to hand-author one.

### Why a separate worker and queue

Training takes minutes to hours, pins a GPU, and can crash (OOM, power loss).
You would never run that inside a request handler — for the same reason you'd
never resize 10,000 images synchronously in an HTTP request.

!!! analogy "A kitchen ticket rail"
    The `app` is the front-of-house taking orders; it writes a ticket
    (`TrainingJob`, status `queued`) and clips it to the rail (the Redis queue).
    The `worker` is the kitchen: it pulls the next ticket (BLPOP), cooks it on
    the GPU, and updates the ticket's status. Front-of-house never blocks on the
    cooking.

Because a ticket represents expensive work, the worker is **crash-durable**: a
job marked `running` whose worker died is recovered at startup (requeued once,
then failed) instead of being stuck forever — standard job-queue hygiene, higher
stakes.

---

## 5. The eval gate — CI for a model {#the-eval-gate-ci-for-a-model}

Here's the problem fine-tuning creates: **a fine-tune can silently make the model
worse.** Unlike code, you can't read a diff and see the bug — the "bug" is a
shift in a billion weights. So how do you know the adapter is safe to ship?

The same way you know code is safe to ship: **you run a test suite and refuse to
deploy if it fails.** That's the eval gate.

!!! analogy "A taste test before the dish leaves the kitchen, on a fresh sample"
    The chef doesn't taste the spoon they cooked with — they taste a *fresh*
    portion. The gate scores the adapter on a **held-out slice of the dataset it
    never trained on**, the way you'd grade a student on questions that weren't on
    the study sheet. Testing on the training data would be like grading the exam
    with the answer key visible — it tells you nothing about generalization.

How the score works (`brain/training/evaluator.py`, `brain/training/models.py`):

1. **Held-out split.** The last ~20% of rows are reserved; training uses the
   rest. Only the held-out rows are scored.
2. **Response-only loss.** The score measures how well the model produces the
   *target answer* — the prompt tokens are masked out, so it's grading the
   answer, not the question.
3. **Score = `exp(-loss)`.** This turns "average per-token surprise"
   (perplexity) into a 0–1 number where higher is better. A score of 1.0 means
   the model predicted the held-out answers perfectly.
4. **The gate** — an adapter is allowed to serve if **either**:
    - it clears an **absolute bar** (default 0.6), **or**
    - it clears a low sanity floor **and beats the base model** on the same
      held-out split by a margin.

Why the second path exists is itself a nice lesson in calibrating a gate to
reality: a small base model **can't** reach the absolute bar even on an ideal
task (the made-up answer tokens carry irreducible per-token cost — see the
[token discussion](#tokens-the-unit-of-text)), but an adapter that reliably
*out-scores its own starting point* has demonstrably learned the target
behavior. So the gate measures **improvement**, not just an absolute — which
makes it a *stronger* signal, not a weaker one: a non-improving or garbage
adapter still fails both paths.

An adapter that fails the gate raises `EvalGateFailed (422)`, is **not
registered**, and **cannot back an endpoint**. That's the product's core safety
promise: an unverified fine-tune never serves.

---

## 6. The whole thing, one more time

Now the [Architecture](architecture.md) page should read as obvious. The system
is:

- a **web service** (`app`) doing CRUD over **Postgres**, plus two specialized
  flows;
- **RAG** = an open-book exam, powered by **embeddings** (coordinates for
  meaning) and a **vector store** (a meaning-indexed database);
- **fine-tuning** = sticky-note patches (**LoRA adapters**) trained by a
  **GPU worker** pulled off a **Redis queue**, gated by a **CI-for-models**
  eval step before they can serve;
- all served behind one **OpenAI-compatible** API, with `llama-cpp` running
  **quantized GGUF** models under a **per-model lock**.

Every "AI" word in that sentence now has a plain-engineering meaning.

---

## Glossary — AI term → what you already know

| AI term | Plain-engineering analogy |
|---|---|
| Inference | Running a compiled function; the hot path |
| Training | Compiling — expensive, done offline |
| Token | A syllable / word-piece; the unit of text and cost |
| Weights | The billions of constants that define the model function |
| GGUF | A compiled binary of the model; `llama-cpp` is its runtime |
| Quantization | JPEG compression for weights — smaller, slightly lossy |
| Embedding | GPS coordinates for meaning (similar text → nearby vectors) |
| Vector store (Chroma) | A database indexed by *meaning* instead of exact value |
| RAG | An open-book exam: retrieve the relevant pages, then answer |
| Chunk | One indexed passage of a document (a "page" on the desk) |
| Citation | The chunks we handed the model, returned for transparency |
| Fine-tuning | Studying until a behavior is second nature (changes weights) |
| LoRA adapter | A small patch/diff/plugin applied over the frozen base weights |
| QLoRA | LoRA where the frozen base is held in 4-bit to fit the GPU |
| Instruction dataset | Labeled training data: `prompt → desired response` |
| Held-out split | The fresh sample you taste / the exam questions not on the sheet |
| Perplexity | Average per-token "surprise"; lower = the model expected it |
| Eval gate | CI for a model — it can't ship unless it passes |
| Base model | A large read-only dependency every project builds on |
| Endpoint / slug | A deployed model instance and the name your app calls it by |

---

Next: **[Workflow & the three contracts](workflow.md)** — how to change any of
this safely.
