# Learning the system

> **Purpose.** This document explains, from first principles, the concepts the
> rest of the codebase depends on — language models, tokens, embeddings, vector
> stores, LoRA, GGUF, quantization, and the evaluation gate. It is written as an
> educational reference: each machine-learning concept is introduced on its own
> terms and then related to an established software-engineering idea, so the
> complete ecosystem can be understood whether the goal is to *operate* the
> platform or to *develop* it. No prior exposure to machine-learning
> infrastructure is assumed; familiarity with ordinary backend systems is
> sufficient to follow every section.

Most of this platform is built from conventional components: an HTTP service, a
relational database, a job queue, and a background worker. The
machine-learning-specific parts are comparatively few, and each one corresponds
to a familiar infrastructure concept. The sections below introduce those parts
individually, then assemble them into the full picture in
[§6](#6-the-complete-picture).

---

## 1. What a language model is

Set aside the term "artificial intelligence" for a moment. Mechanically, a
language model is a **pure function**:

```text
f(text_so_far) → probability distribution over the next token
```

Given some text, the model returns how likely each possible "next chunk of text"
is. Generating a sentence is therefore an iterative process: predict the next
chunk, append it, and predict again. There is no database lookup and no separate
reasoning engine — only a very large mathematical function evaluated repeatedly.

!!! analogy "Comparable to predictive text, scaled up"
    A smartphone keyboard suggests the next word from the preceding few words. A
    language model performs the same operation, but conditioned on the entire
    conversation and trained on a very large corpus. "Generating a response" is
    that prediction run forward, one chunk at a time, until a designated "stop"
    token is produced.

The "very large function" is defined by its **weights** — billions of numbers
fixed during training. Evaluating the function is called **inference**. A useful
correspondence: *compiling* a program is expensive and performed once, whereas
*running* it happens continuously. Training is analogous to compilation;
inference is analogous to execution.

### Tokens — the unit of text

Models do not operate on characters or whole words; they operate on **tokens** —
sub-word fragments. A tokenizer splits text into these fragments, each mapped to
an integer.

- Common words are usually a single token: `"the"` is one token.
- Rare or invented words are split into several. An invented word such as
  `"Zorptania"` might cost four tokens, because the model has never encountered
  it and must assemble it from smaller fragments.

!!! analogy "Tokens resemble syllables; rare words resemble spelling aloud"
    A familiar word is read as a single unit, while an unfamiliar one is spelled
    out fragment by fragment. A model behaves the same way. This has practical
    consequences: token count drives cost, context limits, and — as
    [§5](#the-eval-gate-ci-for-a-model) describes — how difficult an invented
    answer is to learn.

Every response in this platform reports `prompt_tokens`, `completion_tokens`, and
`total_tokens` for precisely this reason: the token is the unit of accounting.

### GGUF and quantization — the model as a deployable artifact

A model's weights must be stored in a file. This platform serves models in the
**GGUF** format, executed by the **llama-cpp** engine.

- **GGUF** is a single-file packaging of the weights together with metadata. It
  is comparable to a **compiled binary** of the model; `llama-cpp` is the runtime
  that loads and executes it, much as a virtual machine executes a compiled
  artifact.
- **Quantization** stores each weight at lower numeric precision (for example,
  four bits instead of sixteen) to reduce file size and memory footprint,
  trading a small amount of accuracy for a large reduction in size. A model
  labeled `Q4_K_M` is quantized to four bits.

!!! analogy "Quantization is comparable to lossy image compression"
    A raw photograph is large and pixel-perfect; a compressed (JPEG) version is a
    fraction of the size and nearly indistinguishable. Quantization applies the
    same principle to model weights: a three-billion-parameter model that would
    require roughly 12 GB at full precision fits in approximately 4 GB at four-bit
    precision, with only minor quality loss.

This is why a consumer GPU with 8 GB of memory can serve a model that nominally
requires far more: it executes the compressed form rather than the full-precision
one.

### Inference: one chef, one cutting board

The `llama-cpp` model object maintains mutable internal state during generation
(a "KV cache" — effectively a scratchpad that records the conversation so far).
**A single model instance is not safe to call concurrently.**

!!! analogy "One chef, one cutting board"
    Two cooks sharing a single cutting board mid-task will collide. Likewise, two
    requests reaching one model instance's scratchpad simultaneously corrupt each
    other, producing garbage output or a crash. The remedy is not to rewrite the
    engine but to require that callers **take turns**.

That is exactly what the implementation does: a **per-model `asyncio.Lock`**
serializes generation on each model instance (`brain/core/model_manager.py`,
`brain/core/inference.py`), generation itself runs on a **bounded thread pool**
so it does not block the asynchronous event loop, and a **timeout** caps each
call. The model cache is a bounded LRU, so a large number of endpoints cannot
exhaust memory by each pinning a full model in RAM. None of this is specific to
machine learning; it is ordinary concurrency engineering around a non-thread-safe
resource, identical in spirit to guarding any shared mutable handle.

---

## 2. Two ways to specialize a model

A base model is a generalist, whereas most deployments require a specialist.
There are two fundamentally different ways to obtain one, and conflating them is
the most common conceptual error:

| Question | Give it **knowledge** (RAG) | Change its **behavior** (fine-tuning) |
|---|---|---|
| What it addresses | "What do *the documents* say?" | "How should the model *act*?" |
| Modifies the weights? | No | Yes (through an adapter) |
| Comparable to | An **open-book examination** | **Practice until a behavior is habitual** |
| Input | Documents | Instruction examples (prompt → response) |
| Cost | Seconds, CPU | Minutes to hours, GPU |
| Reversibility | Delete a file and re-index | Re-train the adapter |

!!! tip "A working distinction"
    Facts the model should look up are a matter of **knowledge (RAG)**. A manner
    in which the model should behave is a matter of **fine-tuning**. "Answer from
    a 500-page handbook" calls for RAG; "always reply in a terse, bulleted
    support voice" calls for fine-tuning.

---

## 3. Knowledge (RAG), from first principles

**RAG** stands for **Retrieval-Augmented Generation**. The model does not
memorize the documents. Instead, at the moment a question is asked, the relevant
passages are located and supplied to the model as context, and the model is asked
to answer using them.

!!! analogy "An open-book examination with a capable research assistant"
    Rather than memorizing a textbook, an examinee whose assistant instantly
    locates the three most relevant pages and places them in view can answer from
    what is on the page. The model is the examinee; retrieval is the assistant.
    The model's effective knowledge is whatever has been placed in front of it.

Making "locate the relevant passages" work requires two machine-learning building
blocks.

### Embeddings — coordinates for meaning

An **embedding** is a function that converts a piece of text into a vector (a
list of roughly 384 numbers) such that texts with similar meaning are positioned
near one another in that vector space.

!!! analogy "Coordinates for meaning"
    Consider a map on which every sentence has a location and sentences about the
    same topic cluster together — "refund policy" and "money-back guarantee" end
    up adjacent even though they share no words. An embedding model assigns those
    coordinates. This is the opposite of a hash function, which deliberately
    scatters similar inputs to unrelated outputs; an embedding maps similar inputs
    to nearby outputs.

In this codebase, `brain/services/embeddings.py` wraps a `sentence-transformers`
model that produces these vectors, loaded lazily as a singleton.

### Vector store — a database indexed by meaning

A conventional database index retrieves rows by exact value (for example, a
B-tree on `user_id`). A **vector store** retrieves by **nearest neighbor in
meaning** — "return the chunks whose embeddings are closest to this query's
embedding." This platform uses **ChromaDB**, with one collection per project.

!!! analogy "A catalog organized by topic rather than by title"
    A title index locates a book only when its exact name is known. A
    topic-organized catalog locates books *about* a subject, even when different
    words are used. The vector store is that topic catalog; the closeness search
    (approximate nearest-neighbor) is the act of walking to the correct shelf.

### The complete RAG cycle

Combining these pieces (`brain/services/rag.py`, `brain/services/chat.py`):

```text
INDEX TIME (once, when a file is uploaded):
  document → parse → split into chunks → embed each chunk → store vectors in Chroma

QUERY TIME (on every chat request):
  question → embed it → find nearest chunks in Chroma → inject them as context
           → model generates an answer grounded in those chunks → return with citations
```

The **citations** follow directly from the mechanism: because the system selects
which chunks to place in front of the model, it can return those same chunks. The
model is not asked to invent sources; it is given them.

Two practical safeguards in the code are worth noting, both of which are ordinary
engineering. Retrieval runs **off the event loop and under a timeout**, so a
stalled vector store degrades to a `504` rather than freezing every request; and
the assembled prompt is **fitted to the model's context window**, dropping the
least-relevant chunks first if it would not otherwise fit, rather than silently
truncating the question.

---

## 4. Fine-tuning (LoRA), from first principles

Fine-tuning changes *how a model behaves* by adjusting its weights from examples.
Fully retraining a model with billions of parameters is prohibitively expensive,
however. **LoRA** (Low-Rank Adaptation) is the technique that makes the operation
affordable.

!!! analogy "Patches applied over the original, rather than rewriting it"
    Full fine-tuning rewrites the entire model to instill one new behavior, which
    is enormous and wasteful. LoRA leaves the original weights untouched and
    instead produces a small set of corrective adjustments applied on top of
    them. These adjustments — the "adapter" — are tiny, a few megabytes against a
    multi-gigabyte model, yet sufficient to shift behavior.

In software terms, the base model is a large read-only dependency, and a LoRA
adapter is a **patch or diff applied over it at load time** — comparable to a
plugin, a version-control patch, or a style override. The small patch is shipped,
not a new copy of the whole model.

### QLoRA — training against a compressed base

**QLoRA** is LoRA in which the frozen base model is **quantized to four bits**
during training (the image-compression analogy from §1 applies again). This is
what allows a genuine fine-tune to fit on an 8 GB consumer GPU: gradients are
computed only for the small adapter, while the large base model is held in its
compressed form. `brain/training/trainer.py` performs this using PEFT and TRL.

### The dataset — labeled examples

The training input is an **instruction dataset**: a JSONL file in which each line
is a `{prompt, response}` pair (optionally with a `system` message). This is
labeled training data — input paired with desired output — the same shape as any
supervised-learning task. The platform can also **synthesize** a dataset from
indexed documents (converting chunks into question/answer pairs), removing the
need to author one by hand.

### Why training uses a separate worker and queue

Training takes minutes to hours, occupies a GPU, and can fail (out-of-memory,
power loss). Such work is never performed inside a request handler, for the same
reason that resizing ten thousand images synchronously within an HTTP request
would be unacceptable.

!!! analogy "An order ticket on a kitchen rail"
    The `app` is the front of house taking orders: it writes a ticket (a
    `TrainingJob`, status `queued`) and places it on the rail (the Redis queue).
    The `worker` is the kitchen: it takes the next ticket (via BLPOP), prepares it
    on the GPU, and updates the ticket's status. The front of house never blocks
    while the kitchen works.

Because a ticket represents expensive work, the worker is **crash-durable**: a
job marked `running` whose worker has died is recovered at startup (requeued once,
then failed) rather than left indefinitely. This is standard job-queue hygiene,
applied where the stakes are higher because each job consumes GPU time.

---

## 5. The evaluation gate — continuous integration for a model {#the-eval-gate-ci-for-a-model}

Fine-tuning introduces a specific risk: it can silently make a model worse.
Unlike a code change, the difference cannot be read in a diff — the change is a
shift across billions of weights. The question, then, is how to determine whether
an adapter is safe to serve.

The answer mirrors how code is determined to be safe to ship: a test suite is run,
and deployment is refused if it fails. That is the role of the evaluation gate.

!!! analogy "A taste test on a fresh portion before a dish leaves the kitchen"
    A cook does not judge a dish by the spoon used to prepare it but by a fresh
    portion. The gate scores the adapter on a **held-out slice of the dataset it
    never trained on**, comparable to assessing a student with questions that were
    not on the study sheet. Scoring on the training data would be equivalent to
    grading an examination with the answer key in view, which reveals nothing
    about generalization.

How the score is computed (`brain/training/evaluator.py`,
`brain/training/models.py`):

1. **Held-out split.** The final ~20% of rows are reserved; training uses the
   remainder. Only the held-out rows are scored.
2. **Response-only loss.** The score measures how well the model produces the
   *target answer*; the prompt tokens are masked, so the answer is graded rather
   than the question.
3. **Score = `exp(-loss)`.** This converts average per-token "surprise"
   (perplexity) into a value between 0 and 1, where higher is better. A score of
   1.0 indicates that the held-out answers were predicted perfectly.
4. **The gate.** An adapter is permitted to serve if **either** it clears an
   **absolute bar** (default 0.6) **or** it clears a low sanity floor **and**
   surpasses the base model on the same held-out split by a margin.

The reason for the second path is itself instructive about calibrating a gate to
reality. A small base model cannot reach the absolute bar even on an ideal task
(the invented answer tokens carry an irreducible per-token cost — see the
[discussion of tokens](#tokens-the-unit-of-text)), yet an adapter that reliably
*outperforms its own starting point* has demonstrably learned the target
behavior. The gate therefore measures **improvement**, not only an absolute
threshold, which makes it a stronger signal rather than a weaker one: a
non-improving or degenerate adapter still fails both paths.

An adapter that fails the gate raises `EvalGateFailed (422)`, is **not
registered**, and **cannot back an endpoint**. This is the platform's central
safety guarantee: an unverified fine-tune never serves.

---

## 6. The complete picture

With the preceding sections in place, the [Architecture](architecture.md) page
can be read straightforwardly. The platform consists of:

- a **web service** (`app`) performing CRUD operations over **PostgreSQL**, plus
  two specialized flows;
- **RAG**, an open-book-examination model powered by **embeddings** (coordinates
  for meaning) and a **vector store** (a database indexed by meaning);
- **fine-tuning**, in which **LoRA adapters** — patches over the frozen base —
  are trained by a **GPU worker** drawing from a **Redis queue** and gated by a
  **continuous-integration-style evaluation** before they may serve;
- a single **OpenAI-compatible** API for serving, with `llama-cpp` executing
  **quantized GGUF** models under a **per-model lock**.

Every machine-learning term in that summary now has a plain engineering meaning.

### Operating versus developing the ecosystem

The same concepts support two activities, and the documentation separates them
deliberately:

- **Operating** the platform — creating projects, supplying documents or
  datasets, running training, observing the evaluation gate, and issuing keys — is
  described in the [User Guide](../user-guide/index.md). The operator's mental
  model is the left-hand column of the §2 table (knowledge vs. behavior) plus the
  gate in §5.
- **Developing** the platform — changing the API, the schema, the training path,
  or the serving path — is described in the [Workflow](workflow.md) page and the
  [Architecture](architecture.md) page. The developer's mental model adds the
  internal mechanisms in §1, §3, and §4, and the contract-driven process that
  protects them.

---

## Glossary — machine-learning term to engineering equivalent

| Term | Engineering equivalent |
|---|---|
| Inference | Executing a compiled function; the hot path |
| Training | Compilation — expensive, performed offline |
| Token | A syllable or word fragment; the unit of text and of cost |
| Weights | The billions of constants that define the model function |
| GGUF | A compiled binary of the model; `llama-cpp` is its runtime |
| Quantization | Lossy compression of weights — smaller, slightly less accurate |
| Embedding | Coordinates for meaning (similar text yields nearby vectors) |
| Vector store (Chroma) | A database indexed by meaning rather than exact value |
| RAG | An open-book examination: retrieve the relevant passages, then answer |
| Chunk | One indexed passage of a document (a "page" placed in view) |
| Citation | The chunks supplied to the model, returned for transparency |
| Fine-tuning | Practice until a behavior is habitual (modifies weights) |
| LoRA adapter | A small patch or diff applied over the frozen base weights |
| QLoRA | LoRA in which the frozen base is held at four-bit precision |
| Instruction dataset | Labeled training data: `prompt → desired response` |
| Held-out split | The fresh portion that is tasted / the unseen examination questions |
| Perplexity | Average per-token "surprise"; lower indicates a better fit |
| Evaluation gate | Continuous integration for a model — it cannot ship unless it passes |
| Base model | A large read-only dependency on which every project builds |
| Endpoint / slug | A deployed model instance and the name applications use to call it |

---

Related pages: [Architecture](architecture.md) for how these pieces are
assembled, and [Workflow](workflow.md) for how they are changed safely.
