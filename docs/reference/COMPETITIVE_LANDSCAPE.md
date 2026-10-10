# Competitive landscape

> **Kind: 📖 Reference.** This page describes what *is* — verified competitor capabilities with primary
> source citations. Open tasks live in the [Roadmap](../roadmap.md). Last updated: 2026-06-25.

!!! warning "Competitor facts are dated 2026-06-25; Adapta's column is current (2026-10-10)"
    Adapta no longer trains adapters (E4.1, 2026-10-10). It **verifies and serves** adapters
    you bring: import, CPU eval gate, promote/rollback ([guide](../user-guide/bring-your-own-adapter.md)).
    Unsloth, Axolotl and LLaMA-Factory are therefore **upstream tools** (where an adapter is
    made), not competitors. The competitor rows below were not re-verified after 2026-06-25,
    and the new "Serves an imported adapter" column is filled only where the existing sources
    already say so (`–` = not assessed).

Adapta occupies a genuinely rare niche: **no single confirmed competitor matches its full combination**
of self-hosted RAG + an imported-LoRA lifecycle (import, CPU eval gate, promote/rollback) + an
automated *blocking* eval gate + OpenAI-compatible serving that *composes* RAG retrieval and the
adapter in a single endpoint call. Training happens elsewhere; Adapta does not do it.

---

## The composition matrix

Every cell below is backed by a primary source cited in [§Verified claims](#verified-claims).
✓ = confirmed capability · ✗ = confirmed absent · ~ = partial / requires external tooling

| | Self-hosted single product | RAG w/ citations | Trains LoRA in-product | **Serves an imported adapter** | **Automatic blocking eval gate** | **Composes RAG + adapter in one call** | OpenAI-compatible |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Adapta** | ✓ | ✓ | ✗ (bring your own) | ✓ | ✓ | ✓ | ✓ |
| vLLM | ✓ | ✗ | ✗ | ✓ (serves) | ✗ | ✗ | ✓ |
| LoRAX (Predibase OSS) | ✓ | ✗ | ✗ | ✓ (serves) | ✗ | ✗ | ✓ |
| H2O LLM Studio | ✓ | ✗ | ✓ | – | ✗ | ✗ | ✗ |
| AnythingLLM | ✓ | ✓ | ✗ | – | ✗ | ✗ | ~ |
| Dify | ✓ | ✓ | ✗ | – | ✗ | ✗ | ~ |
| RAGFlow | ✓ | ✓ | ✗ | – | ✗ | ✗ | ~ |
| Axolotl / Unsloth / LLaMA-Factory (upstream tools) | ✓ | ✗ | ✓ | – | ✗ | ✗ | ✗ |
| NVIDIA NeMo (Kubernetes) | ~ | ~ | ✓ | – | ~ (monitor only) | ✗ | ✓ (via NIM) |
| Red Hat AI 3 (InstructLab) | ~ | ✗ | ✓ | – | ~ (monitor only) | ✗ | ~ |
| Ollama / LM Studio / LocalAI | ✓ | ~ | ~ (LocalAI only, via TRL) | – | ✗ | ✗ | ✓ |

**Adapta is the only row with ✓ in every column except in-product training, which it deliberately does not do.**

### Reading the partial cells

- **Trains LoRA in-product:** Adapta does not. Axolotl, Unsloth and LLaMA-Factory train adapters and
  leave serving to the user; Adapta takes their output (PEFT or GGUF) and adds the gate, serving and RAG.
  The guide says [what it expects](../user-guide/bring-your-own-adapter.md).
- **Eval gate ~:** NVIDIA NeMo Evaluator and Red Hat AI 3's evaluation hub are **monitoring/validation
  dashboards** — a human reviews results. Adapta's gate is an **automatic blocking gate**: an adapter
  that does not clear the held-out threshold (or beat the base model) never becomes an endpoint.
- **Self-hosted ~:** NeMo and Red Hat AI 3 are technically self-hostable but require a Kubernetes
  cluster and 10+ microservices (see [§Deployment complexity](#deployment-complexity) below).

!!! note "Retrieval quality is not a differentiator column — deliberately"
    Adapta's *RAG w/ citations* ✓ is hybrid retrieval: vector search + Postgres full-text search over the whole corpus, fused by Reciprocal
    Rank Fusion, then a cross-encoder rerank (see
    [Hybrid ranking](../concepts/stack.md#hybrid-ranking-postgres-fts-reciprocal-rank-fusion-cross-encoder)).
    That is table stakes rather than a moat — the dedicated RAG products in this matrix ship
    comparable or deeper retrieval stacks, and RAGFlow in particular invests far more in document
    parsing. The claim here is only that Adapta's RAG is not a naive single-vector lookup; the
    differentiation lives in the columns to its right.

### Licence restrictions on the application-level alternatives

Primary sources, checked 2026-10-10 (the rest of this page is dated 2026-06-25).

| Project | Restriction | Source |
|---|---|---|
| Open WebUI | Branding may not be altered or removed above 50 end users in a rolling 30 days, without permission or an enterprise licence | [LICENSE](https://github.com/open-webui/open-webui/blob/main/LICENSE) |
| Dify | No multi-tenant operation of the source without written authorization; logo and copyright may not be removed | [LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE) |
| Kiln | Core library and REST server MIT; the desktop app is source-available under the fair-code model | [README](https://github.com/Kiln-AI/Kiln) |
| Onyx | Community Edition MIT; SSO and RBAC are listed under "Onyx for Enterprise" | [README](https://github.com/onyx-dot-app/onyx) |
| Flowise | Apache-2.0, archived 2026-08-13 | [repo](https://github.com/FlowiseAI/Flowise) |
| Cognita | Apache-2.0, archived 2026-03-13 | [repo](https://github.com/truefoundry/cognita) |

Adapta is Apache-2.0 with no user-count or tenant limit. Kiln fine-tunes models and Onyx is a RAG/chat
product; neither was assessed for the composition matrix above, and BISHENG was not re-verified for this
update.

---

## When **not** to choose Adapta

Candidly: Adapta is not always the right tool.

| If you need… | Better fit |
|---|---|
| Serve 100s of distinct LoRA adapters concurrently on one GPU | LoRAX or vLLM (`max_loras`) |
| Pure document Q&A with an off-the-shelf model, no adapter | AnythingLLM, Dify, RAGFlow |
| Serve any GGUF model with one command, no customization | Ollama |
| Training itself (Adapta does not train), incl. DPO / RLHF / FSDP-distributed training | H2O LLM Studio, Axolotl, Unsloth, LLaMA-Factory |
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

### Q2 — Who trains and serves a VLM LoRA in one self-hosted product?

**Answer (as of 2026-06-25): none.** Adapta no longer attempts it: in-product training, VLM
included, was removed on 2026-10-10. It still serves vision base models, and LoRA import is for
text adapters.

- **LLaMA-Factory**: Train + eval + export to GGUF, but inference is
  [delegated to vLLM/SGLang](https://voltagent.dev/blog/llama-factory/).
- **Axolotl**: Supports [VLM fine-tuning](https://docs.axolotl.ai/) but is primarily a training framework.
- **Unsloth**: Trains VLM LoRAs, but [documents](https://unsloth.ai/docs/get-started/fine-tuning-llms-guide)
  that vLLM cannot serve them: *"vLLM does not support LoRA for vision/encoder layers."*
- **H2O LLM Studio**: Multimodal support is marked experimental.

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

**Implication for Adapta:** each adapter endpoint gets its own llama-cpp model instance (one
`(base, adapter)` cache slot). N active endpoints ≈ N resident models (bounded by §A4.8 LRU).
This is fine at small scale; it becomes a cost disadvantage as the number of active endpoints grows.
The opt-in vLLM backend that was meant to close this gap was removed on 2026-10-10 with the GPU stack.

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

Adapta deploys its entire stack (API server, worker, Postgres, Redis, ChromaDB) with
`make up` (= `docker compose up -d --build`; no GPU needed). No Kubernetes, no Helm, no image pull
secrets. This is a real and quantifiable advantage for a team that is not a platform org.

---

## Deployment complexity

| | Orchestration | Services / containers | GPU requirement | Time to first endpoint |
|---|---|---|---|---|
| **Adapta** | Docker Compose | 5 (app, worker, postgres, redis, chroma) | None (CPU only) | ~5 min |
| NVIDIA NeMo | Kubernetes + Helm | 10+ | A100/H100 80 GB minimum | Hours (cluster setup) |
| Red Hat AI 3 | OpenShift / Kubernetes | Multi-component InstructLab toolkit | GPU recommended | Hours |
| H2O LLM Studio | Docker or bare metal | 1 (training only) | NVIDIA GPU | Minutes (no serving) |
| vLLM / LoRAX | Docker or k8s | 1 (serving only) | GPU | Minutes (no training) |
| AnythingLLM | Docker | 1 | None | Minutes (no adapter lifecycle) |

---

## The moat in one sentence

> Adapta is the only self-hosted product that gives a team **knowledge** (RAG over private documents,
> CPU-only) and **behavior** (a LoRA adapter you bring, imported and verified on CPU) in a single
> `docker compose up`, with an automatic eval gate that blocks any adapter that did not demonstrably
> improve over the base model, all served through one OpenAI-compatible endpoint that composes both
> in every call.
