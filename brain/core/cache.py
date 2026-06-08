"""Advanced caching system for responses and embeddings"""

import hashlib
import json
import logging
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with TTL"""
    key: str
    value: Any
    created_at: float
    ttl: int  # seconds
    hits: int = 0
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        if self.ttl <= 0:  # TTL of 0 or negative means never expires
            return False
        return (time.time() - self.created_at) > self.ttl

    def access(self):
        """Record cache hit"""
        self.hits += 1
        self.last_accessed = time.time()


@dataclass
class CacheStats:
    """Cache statistics"""
    total_entries: int
    hits: int
    misses: int
    evictions: int
    total_size_mb: float
    hit_rate: float


class LRUCache:
    """LRU cache with TTL support"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """
        Initialize cache

        Args:
            max_size: Maximum number of entries
            default_ttl: Default time-to-live in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments"""
        key_data = {
            'args': args,
            'kwargs': kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[key]

        # Check if expired
        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            return None

        # Record hit
        entry.access()
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache"""
        if ttl is None:
            ttl = self.default_ttl

        # Evict if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._evict_lru()

        entry = CacheEntry(
            key=key,
            value=value,
            created_at=time.time(),
            ttl=ttl
        )
        self._cache[key] = entry

    def _evict_lru(self):
        """Evict least recently used entry"""
        if not self._cache:
            return

        # Find LRU entry
        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
        del self._cache[lru_key]
        self._evictions += 1
        logger.debug(f"Evicted cache entry: {lru_key[:16]}...")

    def clear(self):
        """Clear all cache entries"""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cleared {count} cache entries")

    def cleanup_expired(self):
        """Remove expired entries"""
        expired = [k for k, v in self._cache.items() if v.is_expired()]
        for key in expired:
            del self._cache[key]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired cache entries")

    def get_stats(self) -> CacheStats:
        """Get cache statistics"""
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

        # Estimate size (rough approximation)
        total_size = 0
        for entry in self._cache.values():
            try:
                total_size += len(pickle.dumps(entry.value))
            except Exception:
                pass

        return CacheStats(
            total_entries=len(self._cache),
            hits=self._hits,
            misses=self._misses,
            evictions=self._evictions,
            total_size_mb=total_size / (1024 * 1024),
            hit_rate=hit_rate
        )


class ResponseCache(LRUCache):
    """Cache for model responses"""

    def get_response_key(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int
    ) -> str:
        """Generate cache key for response"""
        # Only cache if temperature is low (deterministic)
        if temperature > 0.3:
            return None

        key_data = {
            'model': model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens
        }
        return self._generate_key(key_data)

    def get_response(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int
    ) -> Optional[str]:
        """Get cached response"""
        key = self.get_response_key(model, messages, temperature, max_tokens)
        if key is None:
            return None
        return self.get(key)

    def cache_response(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        response: str,
        ttl: int = 3600
    ):
        """Cache a response"""
        key = self.get_response_key(model, messages, temperature, max_tokens)
        if key is None:
            return
        self.set(key, response, ttl)
        logger.debug(f"Cached response for model {model}")


class EmbeddingCache(LRUCache):
    """Cache for embeddings"""

    def __init__(self, cache_file: Optional[Path] = None, **kwargs):
        super().__init__(**kwargs)
        self.cache_file = cache_file
        if cache_file and cache_file.exists():
            self._load_from_disk()

    def get_embedding_key(self, text: str, model: str = "default") -> str:
        """Generate cache key for embedding"""
        return self._generate_key(text=text, model=model)

    def get_embedding(self, text: str, model: str = "default") -> Optional[List[float]]:
        """Get cached embedding"""
        key = self.get_embedding_key(text, model)
        return self.get(key)

    def cache_embedding(
        self,
        text: str,
        embedding: List[float],
        model: str = "default",
        ttl: int = 0  # Embeddings don't expire by default
    ):
        """Cache an embedding"""
        key = self.get_embedding_key(text, model)
        self.set(key, embedding, ttl)

    def _load_from_disk(self):
        """Load cache from disk"""
        try:
            with open(self.cache_file, 'rb') as f:
                data = pickle.load(f)
                self._cache = data.get('cache', {})
                self._hits = data.get('hits', 0)
                self._misses = data.get('misses', 0)
                self._evictions = data.get('evictions', 0)
            logger.info(f"Loaded {len(self._cache)} embeddings from cache")
        except Exception as e:
            logger.warning(f"Failed to load embedding cache: {e}")

    def save_to_disk(self):
        """Save cache to disk"""
        if not self.cache_file:
            return

        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'cache': self._cache,
                'hits': self._hits,
                'misses': self._misses,
                'evictions': self._evictions
            }
            with open(self.cache_file, 'wb') as f:
                pickle.dump(data, f)
            logger.info(f"Saved {len(self._cache)} embeddings to cache")
        except Exception as e:
            logger.error(f"Failed to save embedding cache: {e}")


class CacheManager:
    """Manages all caches"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize caches
        self.response_cache = ResponseCache(
            max_size=500,  # 500 responses
            default_ttl=3600  # 1 hour
        )

        self.embedding_cache = EmbeddingCache(
            cache_file=self.cache_dir / "embeddings.pkl",
            max_size=10000,  # 10k embeddings
            default_ttl=0  # Never expire
        )

        logger.info("Cache manager initialized")

    def get_all_stats(self) -> Dict[str, CacheStats]:
        """Get statistics for all caches"""
        return {
            'response': self.response_cache.get_stats(),
            'embedding': self.embedding_cache.get_stats()
        }

    def clear_all(self):
        """Clear all caches"""
        self.response_cache.clear()
        self.embedding_cache.clear()
        logger.info("All caches cleared")

    def cleanup_all(self):
        """Cleanup expired entries in all caches"""
        self.response_cache.cleanup_expired()
        self.embedding_cache.cleanup_expired()

    def save_persistent(self):
        """Save persistent caches to disk"""
        self.embedding_cache.save_to_disk()

    def __del__(self):
        """Save on destruction"""
        try:
            self.save_persistent()
        except Exception:
            pass


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get or create global cache manager"""
    global _cache_manager
    if _cache_manager is None:
        from brain.config import settings
        cache_dir = settings.data_dir / "cache"
        _cache_manager = CacheManager(cache_dir)
    return _cache_manager


def get_response_cache() -> ResponseCache:
    """Get response cache"""
    return get_cache_manager().response_cache


def get_embedding_cache() -> EmbeddingCache:
    """Get embedding cache"""
    return get_cache_manager().embedding_cache
