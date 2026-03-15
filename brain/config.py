"""Configuration management for Brain"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(env_prefix="BRAIN_", env_file=".env")

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = False

    # Paths
    data_dir: Path = Path("./data")
    models_dir: Path = Path("./data/models")
    agents_dir: Path = Path("./data/agents")
    cache_dir: Path = Path("./data/cache")

    # Model settings
    default_model: str = "qwen2.5-3b-instruct"
    max_context_length: int = 4096
    n_threads: int = 8
    n_gpu_layers: int = 0  # 0 = CPU only
    use_mmap: bool = True
    use_mlock: bool = False

    # Inference settings
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 512
    stream: bool = True

    # RAG settings
    embedding_model: str = "all-MiniLM-L6-v2"
    rag_top_k: int = 3
    chunk_size: int = 512
    chunk_overlap: int = 50

    # API settings
    api_key: Optional[str] = None  # Optional for local use
    cors_origins: list[str] = ["*"]

    # Performance
    model_load_timeout: int = 300  # seconds
    request_timeout: int = 120
    max_concurrent_requests: int = 5

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
