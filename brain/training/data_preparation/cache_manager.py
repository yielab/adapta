"""
Advanced caching mechanism for training data collection.
Provides persistent caching with TTL, content hashing, and smart invalidation.
"""

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
import aiofiles
import pickle

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Advanced cache manager for training data collection.

    Features:
    - Content-based hashing for deduplication
    - TTL (Time To Live) support
    - Domain-specific cache strategies
    - Memory and disk caching
    - Automatic cleanup of expired entries
    - Cache statistics and metrics
    """

    def __init__(self, cache_dir: Path = None, max_memory_items: int = 1000):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory for disk cache (default: data/cache/training)
            max_memory_items: Maximum items to keep in memory cache
        """
        self.cache_dir = cache_dir or Path("data/cache/training")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Memory cache for fast access
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        self.max_memory_items = max_memory_items

        # Cache statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "disk_reads": 0,
            "disk_writes": 0
        }

        # Domain-specific TTL settings (in seconds)
        self.domain_ttl = {
            "drupal": 86400 * 7,  # 7 days for Drupal docs
            "react": 86400 * 3,   # 3 days for React (updates frequently)
            "rust": 86400 * 14,   # 14 days for Rust docs
            "default": 86400 * 5  # 5 days default
        }

    def _generate_key(self, url: str, domain: str = None) -> str:
        """Generate cache key from URL and domain."""
        key_source = f"{domain or 'default'}:{url}"
        return hashlib.sha256(key_source.encode()).hexdigest()

    def _content_hash(self, content: str) -> str:
        """Generate hash of content for deduplication."""
        return hashlib.md5(content.encode()).hexdigest()

    async def get(self, url: str, domain: str = None) -> Optional[Dict[str, Any]]:
        """
        Get cached content for URL.

        Args:
            url: URL to retrieve from cache
            domain: Domain for cache strategy

        Returns:
            Cached content or None if not found/expired
        """
        key = self._generate_key(url, domain)

        # Check memory cache first
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            if self._is_valid(entry, domain):
                self.stats["hits"] += 1
                logger.debug(f"Cache hit (memory): {url}")
                return entry["data"]
            else:
                # Expired, remove from memory
                del self.memory_cache[key]
                self.stats["evictions"] += 1

        # Check disk cache
        cache_file = self.cache_dir / f"{key}.cache"
        if cache_file.exists():
            try:
                async with aiofiles.open(cache_file, 'rb') as f:
                    content = await f.read()
                    entry = pickle.loads(content)

                if self._is_valid(entry, domain):
                    # Add to memory cache if there's space
                    if len(self.memory_cache) < self.max_memory_items:
                        self.memory_cache[key] = entry

                    self.stats["hits"] += 1
                    self.stats["disk_reads"] += 1
                    logger.debug(f"Cache hit (disk): {url}")
                    return entry["data"]
                else:
                    # Expired, delete file
                    cache_file.unlink()
                    self.stats["evictions"] += 1

            except Exception as e:
                logger.warning(f"Failed to read cache for {url}: {e}")

        self.stats["misses"] += 1
        logger.debug(f"Cache miss: {url}")
        return None

    async def set(self, url: str, data: Dict[str, Any], domain: str = None) -> None:
        """
        Store content in cache.

        Args:
            url: URL to cache
            data: Data to cache
            domain: Domain for cache strategy
        """
        key = self._generate_key(url, domain)

        # Create cache entry
        entry = {
            "url": url,
            "domain": domain,
            "data": data,
            "content_hash": self._content_hash(str(data.get("content", ""))),
            "timestamp": time.time(),
            "created_at": datetime.now().isoformat()
        }

        # Add to memory cache (with LRU eviction if needed)
        if len(self.memory_cache) >= self.max_memory_items:
            # Evict oldest entry
            oldest_key = min(self.memory_cache.keys(),
                           key=lambda k: self.memory_cache[k]["timestamp"])
            del self.memory_cache[oldest_key]
            self.stats["evictions"] += 1

        self.memory_cache[key] = entry

        # Write to disk cache
        cache_file = self.cache_dir / f"{key}.cache"
        try:
            async with aiofiles.open(cache_file, 'wb') as f:
                await f.write(pickle.dumps(entry))
            self.stats["disk_writes"] += 1
            logger.debug(f"Cached: {url}")
        except Exception as e:
            logger.warning(f"Failed to write cache for {url}: {e}")

    def _is_valid(self, entry: Dict[str, Any], domain: str = None) -> bool:
        """Check if cache entry is still valid."""
        ttl = self.domain_ttl.get(domain or "default", self.domain_ttl["default"])
        age = time.time() - entry["timestamp"]
        return age < ttl

    async def has_content(self, content: str) -> bool:
        """
        Check if content already exists in cache (deduplication).

        Args:
            content: Content to check

        Returns:
            True if content exists
        """
        content_hash = self._content_hash(content)

        # Check memory cache
        for entry in self.memory_cache.values():
            if entry.get("content_hash") == content_hash:
                return True

        # Check disk cache (only hashes, not full content)
        hash_file = self.cache_dir / "content_hashes.json"
        if hash_file.exists():
            try:
                async with aiofiles.open(hash_file, 'r') as f:
                    hashes = json.loads(await f.read())
                    return content_hash in hashes
            except:
                pass

        return False

    async def add_content_hash(self, content: str) -> None:
        """Add content hash to deduplication index."""
        content_hash = self._content_hash(content)

        hash_file = self.cache_dir / "content_hashes.json"
        hashes = set()

        if hash_file.exists():
            try:
                async with aiofiles.open(hash_file, 'r') as f:
                    hashes = set(json.loads(await f.read()))
            except:
                pass

        hashes.add(content_hash)

        try:
            async with aiofiles.open(hash_file, 'w') as f:
                await f.write(json.dumps(list(hashes)))
        except Exception as e:
            logger.warning(f"Failed to update content hashes: {e}")

    async def cleanup_expired(self, domain: str = None) -> int:
        """
        Remove expired cache entries.

        Args:
            domain: Clean specific domain or all if None

        Returns:
            Number of entries removed
        """
        removed = 0

        # Clean memory cache
        keys_to_remove = []
        for key, entry in self.memory_cache.items():
            if domain and entry.get("domain") != domain:
                continue
            if not self._is_valid(entry, entry.get("domain")):
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.memory_cache[key]
            removed += 1

        # Clean disk cache
        for cache_file in self.cache_dir.glob("*.cache"):
            try:
                async with aiofiles.open(cache_file, 'rb') as f:
                    content = await f.read()
                    entry = pickle.loads(content)

                if domain and entry.get("domain") != domain:
                    continue

                if not self._is_valid(entry, entry.get("domain")):
                    cache_file.unlink()
                    removed += 1
            except Exception as e:
                logger.warning(f"Error cleaning cache file {cache_file}: {e}")

        logger.info(f"Cleaned {removed} expired cache entries")
        return removed

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = self.stats["hits"] / total_requests if total_requests > 0 else 0

        return {
            **self.stats,
            "memory_items": len(self.memory_cache),
            "hit_rate": f"{hit_rate:.2%}",
            "total_requests": total_requests,
            "disk_cache_size": sum(f.stat().st_size for f in self.cache_dir.glob("*.cache"))
        }

    async def clear(self, domain: str = None) -> None:
        """
        Clear cache.

        Args:
            domain: Clear specific domain or all if None
        """
        if domain:
            # Clear specific domain from memory
            keys_to_remove = [k for k, v in self.memory_cache.items()
                            if v.get("domain") == domain]
            for key in keys_to_remove:
                del self.memory_cache[key]

            # Clear specific domain from disk
            for cache_file in self.cache_dir.glob("*.cache"):
                try:
                    async with aiofiles.open(cache_file, 'rb') as f:
                        content = await f.read()
                        entry = pickle.loads(content)
                    if entry.get("domain") == domain:
                        cache_file.unlink()
                except:
                    pass
        else:
            # Clear all
            self.memory_cache.clear()
            for cache_file in self.cache_dir.glob("*.cache"):
                cache_file.unlink()

        logger.info(f"Cleared cache for domain: {domain or 'all'}")

    async def warm_cache(self, urls: List[str], domain: str = None) -> None:
        """
        Pre-warm cache with URLs (useful for batch operations).

        Args:
            urls: List of URLs to cache
            domain: Domain for the URLs
        """
        logger.info(f"Warming cache with {len(urls)} URLs for domain: {domain}")

        # This would typically fetch the URLs and cache them
        # Implementation depends on the collector being used
        pass


class SmartCacheStrategy:
    """
    Smart caching strategies based on content type and domain.
    """

    @staticmethod
    def should_cache(url: str, content: str, domain: str = None) -> bool:
        """
        Determine if content should be cached.

        Args:
            url: URL of the content
            content: The content itself
            domain: Domain context

        Returns:
            True if should be cached
        """
        # Don't cache very small content (likely errors)
        if len(content) < 100:
            return False

        # Don't cache error pages
        error_indicators = ["404", "not found", "error", "forbidden", "unauthorized"]
        content_lower = content[:500].lower()
        if any(indicator in content_lower for indicator in error_indicators):
            return False

        # Always cache API documentation
        if "api" in url.lower() or "/docs" in url.lower():
            return True

        # Domain-specific rules
        if domain == "drupal":
            # Cache Drupal module and hook documentation
            return any(term in url.lower() for term in ["module", "hook", "api", "function"])
        elif domain == "react":
            # Cache component and hook documentation
            return any(term in url.lower() for term in ["component", "hook", "api", "guide"])
        elif domain == "rust":
            # Cache trait and struct documentation
            return any(term in url.lower() for term in ["trait", "struct", "enum", "macro"])

        # Default: cache everything else
        return True

    @staticmethod
    def get_cache_priority(url: str, domain: str = None) -> int:
        """
        Get cache priority (higher = more important to keep).

        Args:
            url: URL to prioritize
            domain: Domain context

        Returns:
            Priority score (0-100)
        """
        priority = 50  # Default priority

        # API documentation is high priority
        if "api" in url.lower():
            priority += 20

        # Reference documentation
        if any(term in url.lower() for term in ["reference", "docs", "guide"]):
            priority += 15

        # Examples and tutorials
        if any(term in url.lower() for term in ["example", "tutorial", "sample"]):
            priority += 10

        # Version-specific content
        if any(f"v{i}" in url.lower() for i in range(1, 20)):
            priority -= 10  # Lower priority for old versions

        # Domain-specific adjustments
        if domain == "drupal":
            if "hook" in url.lower():
                priority += 15
            if "module" in url.lower():
                priority += 10
        elif domain == "react":
            if "hooks" in url.lower():
                priority += 15
            if "component" in url.lower():
                priority += 10
        elif domain == "rust":
            if "std" in url.lower():
                priority += 20  # Standard library is crucial

        return min(100, max(0, priority))


# Global cache instance
_cache_manager = None


def get_cache_manager(cache_dir: Path = None) -> CacheManager:
    """Get or create the global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(cache_dir)
    return _cache_manager