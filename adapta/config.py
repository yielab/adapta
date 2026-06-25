"""Application configuration via pydantic-settings.
All env vars are prefixed ADAPTA_ (e.g. ADAPTA_DATABASE_URL).
"""

from pathlib import Path

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
    default_model: str = "qwen2.5-3b-instruct"
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

    # RAG / embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    rag_top_k: int = 5
    # Cap RAG retrieval so a hung/slow Chroma degrades to a typed 504 instead of
    # blocking every chat request indefinitely (A4.12).
    rag_timeout_seconds: int = 10
    chunk_size: int = 512
    chunk_overlap: int = 64
    # Dataset synthesis: fail the run if more than this fraction of chunks errored,
    # rather than silently shipping a sparse/degraded dataset (A4.12).
    synthesis_max_error_rate: float = 0.5

    # Auth brute-force rate limiting (A4.9). Fixed-window per-IP and per-email cap on
    # the unauthenticated auth endpoints (login/register/accept-invite). Fail-open: a
    # limiter (Redis) outage must never lock everyone out of auth.
    auth_rate_limit_max: int = 20  # allowed attempts per window per key
    auth_rate_limit_window_seconds: int = 60

    # Training — eval gate. An adapter is promotable if EITHER it clears the absolute
    # score floor (a strong fine-tune), OR it clears a low sanity floor AND meaningfully
    # beats the base model on the same held-out split (it demonstrably helped). The
    # improvement path matters because the absolute score is exp(-held_out_perplexity):
    # a small base model can't reach 0.6 even on an ideal task, yet a fine-tune that
    # reliably doubles the base score has clearly learned something. Gating on
    # improvement (not just an absolute bar) was anticipated by §A3.2.
    eval_score_threshold: float = 0.6  # absolute "strong adapter" pass
    eval_min_improvement: float = 0.05  # min score gain over base for the improvement path
    eval_min_floor: float = 0.05  # sanity floor for the improvement path (not garbage)
    # Minimum dataset size to start a training job (A4.6). Below this the held-out
    # eval split collapses (e.g. 1 row → 0 held out → the gate scores the training
    # rows and only measures memorization), so we reject the job up front.
    min_training_samples: int = 10
    # Free-disk preflight for the worker (A4.12): bail before training if the
    # adapters volume has less than this much free, rather than dying deep in a run.
    min_free_disk_gb: float = 5.0

    # Image dataset bundles (§V2): caps applied while extracting/validating a
    # .zip bundle (JSONL manifest + images). Outside these a bundle is rejected
    # at validation, never accepted into a run that would die mid-train.
    max_bundle_files: int = 2000
    max_bundle_uncompressed_mb: int = 500
    max_image_mb: int = 10
    max_image_side_px: int = 8192
    # Hard cap on a single dataset UPLOAD (the compressed .zip / .jsonl on the wire),
    # enforced while streaming to disk so a hostile/oversized upload can't fill the disk
    # before validation even runs. Distinct from max_bundle_uncompressed_mb (post-extract).
    max_upload_mb: int = 1024

    # Vision serving (§V4): caps on image content-parts per chat request.
    # Decoded size/dimensions reuse max_image_mb / max_image_side_px above.
    max_images_per_request: int = 4

    # Fine-tune serving (A3.1): PEFT adapters are converted to a GGUF LoRA so the
    # single llama-cpp runtime can serve them via `lora_path`. The converter is
    # llama.cpp's official convert_lora_to_gguf.py, vendored into the worker image.
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
