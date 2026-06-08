"""Application configuration via pydantic-settings.
All env vars are prefixed BRAIN_ (e.g. BRAIN_DATABASE_URL).
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BRAIN_", env_file=".env")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = False

    # Paths
    data_dir: Path = Path("/app/data")
    models_dir: Path = Path("/app/data/models")
    uploads_dir: Path = Path("/app/data/uploads")
    adapters_dir: Path = Path("/app/data/adapters")
    datasets_dir: Path = Path("/app/data/datasets")

    # Database (Postgres via asyncpg)
    database_url: str = "postgresql+asyncpg://brain:brain@postgres:5432/brain"

    # Redis (job queue + cache)
    redis_url: str = "redis://redis:6379/0"

    # Auth (JWT)
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_use_openssl_rand_hex_32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8  # 8 hours

    # Inference
    default_model: str = "qwen2.5-3b-instruct"
    max_context_length: int = 4096
    n_threads: int = 8
    n_gpu_layers: int = 0  # 0 = CPU only; >0 = GPU layers
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 512
    use_mmap: bool = True
    use_mlock: bool = False

    # RAG / embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    rag_top_k: int = 5
    chunk_size: int = 512
    chunk_overlap: int = 64

    # Training
    eval_score_threshold: float = 0.6  # minimum eval score for an adapter to be promoted

    # CORS
    cors_origins: list[str] = ["*"]

    def ensure_dirs(self) -> None:
        for d in [self.data_dir, self.models_dir, self.uploads_dir, self.adapters_dir, self.datasets_dir]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
