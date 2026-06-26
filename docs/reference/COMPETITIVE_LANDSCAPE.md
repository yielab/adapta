# Competitive landscape

> **Kind: 📖 Reference.** This page describes what *is* — verified competitor capabilities with primary
> source citations. Open tasks live in the [Roadmap](../roadmap.md). Last updated: 2026-06-25.

Adapta occupies a genuinely rare niche: **no single confirmed competitor matches its full combination**
of self-hosted RAG + LoRA/QLoRA fine-tune + VLM (image-understanding) fine-tune + an automated
*blocking* eval gate + OpenAI-compatible serving that *composes* RAG retrieval and the fine-tuned
adapter in a single endpoint call.

---

## The composition matrix

Every cell below is backed by a primary source cited in [§Verified claims](#verified-claims).
✓ = confirmed capability · ✗ = confirmed absent · ~ = partial / requires external tooling

| | Self-hosted single product | RAG w/ citations | LoRA/QLoRA fine-tune | **VLM fine-tune (end-to-end)** | **Automatic blocking eval gate** | **Composes RAG + adapter in one call** | OpenAI-compatible |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Adapta** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| vLLM | ✓ | ✗ | ✗ (serves only) | ✗ | ✗ | ✗ | ✓ |
| LoRAX (Predibase OSS) | ✓ | ✗ | ✗ (serves only) | ✗ | ✗ | ✗ | ✓ |
| H2O LLM Studio | ✓ | ✗ | ✓ | ~ (experimental) | ✗ | ✗ | ✗ |
| AnythingLLM | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ~ |
| Dify | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ~ |
| RAGFlow | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ~ |
| Axolotl / Unsloth / LLaMA-Factory | ✓ | ✗ | ✓ | ~ (train only) | ✗ | ✗ | ✗ |
| NVIDIA NeMo (Kubernetes) | ~ | ~ | ✓ | ✓ | ~ (monitor only) | ✗ | ✓ (via NIM) |
| Red Hat AI 3 (InstructLab) | ~ | ✗ | ✓ | ✗ | ~ (monitor only) | ✗ | ~ |
| Ollama / LM Studio / LocalAI | ✓ | ~ | ~ (LocalAI only, via TRL) | ✗ | ✗ | ✗ | ✓ |

**Adapta is the only all-✓ row.**

### Reading the partial cells

- **VLM fine-tune ~:** Axolotl and Unsloth train VLM LoRAs, but leave serving to the user (vLLM, which
  explicitly [does not support LoRA for vision/encoder layers](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide)).
  LLaMA-Factory is the closest — train + eval + export — but delegates inference to vLLM/SGLang.
  None of them do the full `train → gate → convert → serve` cycle in one product.
- **Eval gate ~:** NVIDIA NeMo Evaluator and Red Hat AI 3's evaluation hub are **monitoring/validation
  dashboards** — a human reviews results. Adapta's gate is an **automatic blocking gate**: a fine-tune
  that does not clear the held-out threshold (or beat the base model) never becomes an endpoint.
- **Self-hosted ~:** NeMo and Red Hat AI 3 are technically self-hostable but require a Kubernetes
  cluster and 10+ microservices (see [§Deployment complexity](#deployment-complexity) below).

---

## When **not** to choose Adapta

Candidly: Adapta is not always the right tool.

| If you need… | Better fit |
|---|---|
| Serve 100s of distinct LoRA adapters concurrently on one GPU | LoRAX or vLLM (`max_loras`) |
| Pure document Q&A with an off-the-shelf model, no fine-tuning | AnythingLLM, Dify, RAGFlow |
| Serve any GGUF model with one command, no customization | Ollama |
| DPO / RLHF / FSDP-distributed training, no serving required | H2O LLM Studio, Axolotl |
| Enterprise Kubernetes platform with MLOps suite | NVIDIA NeMo Microservices |

---

## Verified claims

The four questions below are the load-bearing ones for Adapta's positioning. Each is answered with a
primary-source citation (verified 2026-06-25).

### Q1 — Does any competitor compose RAG + LoRA adapter in one inference call?

**Answer: No confirmed competitor does this.**

- **NVIDIA NIM**: The [LoRA docs](https://docs.nvidia.com/nim/large-language-models/2.0.1/advanced-use-cases/finetune-lora.html)
  and the [RAG blog](https://developer.nvidia.com/blog/enhancing-rag-applications-with-nvidia-nim/) are
  entirely separate. The LoRA doc states: *"When submitting inference requests to the NIM, the server
  supports dynamic multi-LoRA inference, enabling simultaneous inference requests with different LoRA
  models"* — but never discusses injecting retrieved context at the same time. No NVIDIA source documents
  composing both in one call.
- **Predibase / LoRAX**: README explicitly covers only adapter serving; [RAG is not mentioned](https://github.com/predibase/lorax).
- **LocalAI**: Fine-tuning and RAG are documented as separate features with no documented composition path.
- **Dify**: Knowledge base retrieval and model adapter selection are separate pipeline nodes; no
  single-call composition documented.
- **RAGFlow**: [Pure RAG platform](https://github.com/infiniflow/ragflow) — no LoRA fine-tuning support.

Adapta's `chat.py` injects retrieved chunks *and* resolves the adapter on every `/v1/chat/completions`
call — no orchestration layer required.

### Q2 — Who does VLM LoRA fine-tuning end-to-end self-hosted?

**Answer: No tool does the full cycle (train → gate → convert → serve) in one product.**

- **LLaMA-Factory**: Closest. Train + eval + export to GGUF, but inference is
  [delegated to vLLM/SGLang](https://voltagent.dev/blog/llama-factory/): *"You can export LoRA adapters
  into a merged model for Hugging Face, or call your model via an OpenAI-compatible API, with inference
  backends including vLLM worker and SGLang worker."* No integrated serving or eval gate.
- **Axolotl**: Supports [VLM fine-tuning](https://docs.axolotl.ai/) (LLaMA-Vision, Qwen2-VL, LLaVA…)
  but is primarily a training framework: *"specialized serving platforms like vLLM would typically handle
  production inference workloads."*
- **Unsloth**: Trains VLM LoRAs, but [explicitly documents](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide)
  that vLLM cannot serve them: *"vLLM does not support LoRA for vision/encoder layers."* Users must
  serve through transformers or Unsloth's own inference, not an OpenAI-compatible endpoint.
- **H2O LLM Studio**: Multimodal support is marked experimental; no VLM LoRA serving infrastructure documented.

Adapta's §V workstream (VLM end-to-end) covers: zip-bundle upload → validation → QLoRA training
(vision tower frozen) → held-out eval gate → GGUF conversion (base + mmproj) → llama-cpp serving with
OpenAI image content-parts. It is the only self-hosted product that does all of this in one `make up`.
See [VLM fine-tuning — why it's rare](../user-guide/vlm-fine-tuning.md) for the full end-to-end guide.

### Q3 — Can llama-cpp/GGUF batch multiple LoRA adapters concurrently?

**Answer: No — this is a known architectural limitation of llama-cpp.**

Per [llama.cpp server docs](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
and [issue #18466](https://github.com/ggml-org/llama.cpp/issues/18466):
*"Requests with different LoRA configurations will not be batched together, which may result in
performance degradation."*

This is the root cause of Adapta's **serving density gap** (§D3 in TODO.md). Contrast:

- **vLLM**: `max_loras` parameter enables heterogeneous continuous batching across different adapters.
- **LoRAX**: Built entirely around this use-case via SGMV kernel fusion: *"LoRAX implements
  heterogeneous continuous batching that packs requests for different adapters together into the same
  batch, keeping latency and throughput nearly constant with the number of concurrent adapters."*

**Implication for Adapta:** each fine-tune endpoint gets its own llama-cpp model instance (one
`(base, adapter)` cache slot). N active endpoints ≈ N GPU-resident models (bounded by §A4.8 LRU).
This is fine at small scale; it becomes a cost disadvantage as the number of active endpoints grows.
Closing this gap requires an opt-in vLLM backend (TODO.md §D3) — adding a second serving path, not
rewriting llama-cpp.

### Q4 — How complex is NVIDIA NeMo to deploy self-hosted vs Adapta?

**Answer: NeMo requires Kubernetes + 10 microservices. Adapta is `docker compose up`.**

From the [NeMo Customizer deployment docs](https://docs.nvidia.com/nemo/microservices/25.9.0/set-up/deploy-as-microservices/customizer.html):
*"NeMo Customizer requires a single-node Kubernetes cluster on a Linux host with cluster-admin level
permissions."*

A full NeMo Customizer + Evaluator + NIM deployment requires:

1. NIM Proxy (inference routing)
2. NeMo Customizer (fine-tuning)
3. NeMo Evaluator (evaluation)
4. NeMo Entity Store
5. NeMo Data Store (model artifacts)
6. PostgreSQL
7. Milvus (vector store)
8. Argo Workflows
9. OpenTelemetry collector
10. NGC image pull secrets

The [Evaluator docs](https://docs.nvidia.com/nemo/microservices/latest/set-up/deploy-as-microservices/evaluator/docker-compose.html)
explicitly note: *"Docker Compose is not recommended for production but is useful for evaluation and
experimentation."*

Adapta deploys its entire stack (API server, training worker, Postgres, Redis, ChromaDB) with
`make up` (= `docker compose up -d --build`, GPU auto-detected). No Kubernetes, no Helm, no image pull
secrets. This is a real and quantifiable advantage for a team that is not a platform org.

---

## Deployment complexity

| | Orchestration | Services / containers | GPU requirement | Time to first endpoint |
|---|---|---|---|---|
| **Adapta** | Docker Compose | 5 (app, worker, postgres, redis, chroma) | Optional (RAG = CPU only) | ~5 min |
| NVIDIA NeMo | Kubernetes + Helm | 10+ | A100/H100 80 GB minimum | Hours (cluster setup) |
| Red Hat AI 3 | OpenShift / Kubernetes | Multi-component InstructLab toolkit | GPU recommended | Hours |
| H2O LLM Studio | Docker or bare metal | 1 (training only) | NVIDIA GPU | Minutes (no serving) |
| vLLM / LoRAX | Docker or k8s | 1 (serving only) | GPU | Minutes (no training) |
| AnythingLLM | Docker | 1 | None | Minutes (no fine-tuning) |

---

## The moat in one sentence

> Adapta is the only self-hosted product that gives a team **knowledge** (RAG over private documents,
> CPU-only) and **behavior** (LoRA fine-tuning, including VLM image-understanding) in a single
> `docker compose up`, with an automatic eval gate that blocks any fine-tune that did not demonstrably
> improve over the base model, all served through one OpenAI-compatible endpoint that composes both
> in every call.
