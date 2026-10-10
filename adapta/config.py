"""Application configuration via pydantic-settings.
All env vars are prefixed ADAPTA_ (e.g. ADAPTA_DATABASE_URL).
"""

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADAPTA_", env_file=".env")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = False

    # Paths — set ADAPTA_DATA_DIR to override the root; subdirs default to
    # data_dir/{models,uploads,adapters,datasets} but can be overridden individually.
    data_dir: Path = Path("/app/data")
    models_dir: Path = Path("/app/data/models")
    uploads_dir: Path = Path("/app/data/uploads")
    adapters_dir: Path = Path("/app/data/adapters")
    datasets_dir: Path = Path("/app/data/datasets")

    # Database (Postgres via asyncpg)
    database_url: str = "postgresql+asyncpg://adapta:adapta@postgres:5432/adapta"

    # Redis (job queue + cache)
    redis_url: str = "redis://redis:6379/0"

    # Auth (JWT)
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_use_openssl_rand_hex_32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8  # 8 hours

    # Development seed (adapta/db/seed.py, run by the entrypoint after migrations).
    # Only acts on an EMPTY database — a real register/bootstrap is never clobbered.
    # The compose file turns it on; disable with ADAPTA_SEED_DEFAULT_ADMIN=0 to
    # exercise the register bootstrap flow instead.
    seed_default_admin: bool = False
    default_admin_org: str = "Local Dev"
    default_admin_email: str = "admin@example.com"
    default_admin_password: str = "admin12345"

    # Inference
    default_model: str = "qwen2.5-1.5b-instruct"  # §E1.2: must resolve to a commercial_use catalog entry
    max_context_length: int = 4096
    n_threads: int = 8
    n_gpu_layers: int = 0  # 0 = CPU only; >0 = GPU layers
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 512
    # Max characters across all user messages in a single chat request (7.4).
    # Guards against unreasonably large inputs that could exhaust memory during
    # tokenization or consume excessive model context.
    max_input_chars: int = 100_000
    use_mmap: bool = True
    use_mlock: bool = False

    # Inference concurrency & safety (A4.1). llama-cpp's Llama object is NOT safe
    # for concurrent calls on one instance — two requests sharing it race the KV
    # cache (garbage output or a segfault that kills the app). Serving therefore
    # serializes per model (a lock in model_manager) and runs the blocking call on
    # a bounded pool; a per-request wall-clock cap stops a runaway generation from
    # pinning a worker forever.
    inference_max_workers: int = 2
    inference_timeout_seconds: int = 300
    # Max distinct models (base, or base+LoRA) kept loaded at once (A4.8). Since the
    # cache key includes the adapter, N fine-tune endpoints would otherwise pin N full
    # models in RAM and OOM the app container. The LRU is evicted past this bound; an
    # evicted endpoint transparently reloads on its next call. Raise it only with RAM
    # to spare (a 3B Q4 model is ~2 GB resident).
    max_loaded_models: int = 2

    # Serving backend (E2.1). "llamacpp" serves everything in-process. "ollama" sends
    # adapter-less text requests for models in `ollama_model_map` to an Ollama host;
    # adapters, vision and unmapped models stay on llama-cpp. The map is catalog name ->
    # Ollama tag (Apache-licensed entries only); override with a JSON object in
    # ADAPTA_OLLAMA_MODEL_MAP.
    serving_backend: Literal["llamacpp", "ollama"] = "llamacpp"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model_map: dict[str, str] = {
        "qwen2.5-0.5b-instruct": "qwen2.5:0.5b-instruct",
        "qwen2.5-1.5b-instruct": "qwen2.5:1.5b-instruct",
        "qwen2.5-7b-instruct": "qwen2.5:7b-instruct",
    }

    # RAG / embeddings
    # Multilingual by default (E3.6, user decision 2026-10-10): on the bilingual golden set it
    # scores recall@5 0.978 vs 0.844 for the English-only all-MiniLM-L6-v2. Changing it on a
    # deployment with indexed projects needs `scripts/reembed.py` first (OPERATIONS 6.5).
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    rag_top_k: int = 5
    # (E3.5) Chat-time relevance floor; 0 disables. Applies to RetrievedChunk.score: the
    # cross-encoder sigmoid when the reranker is on, else the vector cosine similarity
    # (1 - distance). Keyword-only hits have no cosine and are exempt. RRF scores are rank
    # arithmetic (max ~0.033), never compared against this. Not applied inside retrieve(),
    # so the golden set measures the same candidates as before.
    rag_min_score: float = 0.2
    # Hybrid retrieval (D5): fetch top_k * N vector candidates from Chroma for the
    # dense leg of the RRF fusion. 4× keeps latency low on CPU.
    rag_hybrid_fetch_multiplier: int = 4
    # Sparse leg (E3.2): Postgres full-text search over chunks.tsv, top_k * N hits.
    rag_sparse_fetch_multiplier: int = 4
    # Sparse leg drops query lexemes found in more than this fraction of the project's
    # chunks (language-agnostic statistical stopwords; E3.2). Terms in <= 3 chunks are kept.
    rag_sparse_max_df: float = 0.5
    # Text-search config for the query side: simple | english | spanish. chunks.tsv is
    # generated with 'simple' (E3.1), so anything else only matches after E3.6 regenerates it.
    rag_fts_config: Literal["simple", "english", "spanish"] = "simple"
    # Cross-encoder reranker model (D5) — OFF by default since E3.6: the only small one,
    # ms-marco-MiniLM, is English-only and cut bilingual recall@5 from 0.978 to 0.889 (and
    # tripled latency). Opt in with e.g. "cross-encoder/ms-marco-MiniLM-L-6-v2" for an
    # English-only corpus; rag_timeout_seconds guards the whole path including reranking.
    rag_reranker_model: str = ""
    # Cap RAG retrieval so a hung/slow Chroma degrades to a typed 504 instead of
    # blocking every chat request indefinitely.
    rag_timeout_seconds: int = 10
    # (E1.15) Per-request bound on every call to the Chroma server. chromadb 1.5.9 builds its
    # httpx session with timeout=None, so without this a deadlocked Chroma blocks the caller
    # forever (measured 2026-10-10). Must exceed the slowest healthy upsert of one file.
    chroma_timeout_seconds: int = 30
    # /health/deep marks Chroma "degraded" when its heartbeat takes at least this long.
    chroma_slow_ms: int = 1000
    # (E1.15) Deadline for ONE attempt of an `index` job in the worker (parse + OCR + embed +
    # upsert). A timeout is a transient failure: one retry, then the file ends `failed`.
    # Sized for the largest scanned PDF the OCR path accepts; lower it for text-only deployments.
    index_job_timeout_seconds: int = 900
    chunk_size: int = 512
    chunk_overlap: int = 64
    # OCR'd chunks whose mean line confidence is below this are flagged needs_review (E3.3b).
    ocr_review_threshold: float = 0.90
    # Dataset synthesis: fail the run if more than this fraction of chunks errored,
    # rather than silently shipping a sparse/degraded dataset.
    synthesis_max_error_rate: float = 0.5

    # Auth brute-force rate limiting: fixed-window per-IP and per-email cap on
    # the unauthenticated auth endpoints (login/register/accept-invite). Fail-open: a
    # limiter (Redis) outage must never lock everyone out of auth.
    auth_rate_limit_max: int = 20  # allowed attempts per window per key
    auth_rate_limit_window_seconds: int = 60

    # Eval gate (E4.3). An adapter is scored on a held-out eval set through the serving path
    # (greedy generation, task metric) and compared with the base model on the SAME rows. It
    # passes if EITHER it beats the base by `eval_min_improvement` (it demonstrably helped) OR
    # it clears `eval_absolute_floor` and is at least as good as the base (already strong).
    eval_min_improvement: float = 0.05
    eval_absolute_floor: float = 0.8
    # An eval set must have this many rows: fewer is noise, more is wasted CPU time.
    eval_min_rows: int = 20
    eval_max_rows: int = 200
    # Generation cap per eval row (classification labels and JSON extractions are short).
    eval_max_new_tokens: int = 128

    # Hard cap on a single dataset UPLOAD, enforced while streaming to disk so a
    # hostile/oversized upload can't fill the disk before validation even runs.
    max_upload_mb: int = 1024

    # Cap on one adapter upload (a .gguf, or a .zip of a PEFT adapter) and on the size a zip
    # may expand to — LoRA adapters are tens to hundreds of MB; this bounds a zip bomb.
    adapter_max_upload_mb: int = 512

    # Image limits for vision chat (§V4): decoded size/dimensions per image, and
    # the number of image content-parts per request.
    max_image_mb: int = 10
    max_image_side_px: int = 8192
    max_images_per_request: int = 4

    # Adapter serving (A3.1): PEFT adapters are converted to a GGUF LoRA so the
    # single llama-cpp runtime can serve them via `lora_path`. The converter is
    # llama.cpp's official convert_lora_to_gguf.py.
    lora_convert_dir: Path = Path("/opt/llamacpp")  # holds convert_lora_to_gguf.py
    lora_gguf_filename: str = "adapter.gguf"  # converted artifact, stored beside safetensors
    lora_outtype: str = "f16"  # GGUF LoRA quant for conversion (f16/f32/q8_0)

    # CORS
    cors_origins: list[str] = []  # empty = no CORS; override in production via ADAPTA_CORS_ORIGINS

    # Observability
    log_format: str = "text"  # "text" (default) or "json" for structured logs
    metrics_enabled: bool = True  # expose GET /metrics (Prometheus text format)

    @model_validator(mode="before")
    @classmethod
    def _validate_secret_key(cls, values: dict) -> dict:
        secret = values.get("secret_key", "CHANGE_ME_IN_PRODUCTION_use_openssl_rand_hex_32")
        if "CHANGE_ME" in str(secret):
            import warnings

            warnings.warn(
                "ADAPTA_SECRET_KEY is still the default placeholder. "
                "Set a strong secret with: openssl rand -hex 32",
                stacklevel=2,
            )
        return values

    @model_validator(mode="before")
    @classmethod
    def _derive_subdirs(cls, values: dict) -> dict:
        # If ADAPTA_DATA_DIR is set, re-base any subdir that wasn't explicitly
        # overridden. This runs before field parsing, so all annotations stay Path.
        data_dir = values.get("data_dir")
        if data_dir is None:
            return values
        base = Path(str(data_dir))
        for name, child in (
            ("models_dir", "models"),
            ("uploads_dir", "uploads"),
            ("adapters_dir", "adapters"),
            ("datasets_dir", "datasets"),
        ):
            if name not in values:
                values[name] = base / child
        return values

    def ensure_dirs(self) -> None:
        for d in [
            self.data_dir,
            self.models_dir,
            self.uploads_dir,
            self.adapters_dir,
            self.datasets_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
# NB: directory creation is deliberately NOT done here. Importing this module must
# stay free of filesystem side effects so the package can be imported under tests/CI
# (where the default /app paths aren't writable). Runtime entry points that actually
# need the data dirs call settings.ensure_dirs() at startup (API lifespan, worker loop).
