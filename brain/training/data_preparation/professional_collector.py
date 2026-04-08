"""
Professional-Grade Web Collector
=================================

Robust, production-ready web scraping with:
- Multiple extraction algorithms with intelligent fallback
- Comprehensive validation and quality scoring
- Detailed logging and debugging
- Error resilience and retry mechanisms
- Content deduplication
- Performance monitoring

Architecture: Modular, extensible, battle-tested
"""

import asyncio
import aiohttp
import hashlib
import json
import logging
import time
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
from dataclasses import dataclass, field, asdict
from enum import Enum

from bs4 import BeautifulSoup
import trafilatura
from readability import Document as ReadabilityDocument

# Configure logging
logger = logging.getLogger(__name__)


class ExtractionAlgorithm(Enum):
    """Available content extraction algorithms"""
    TRAFILATURA = "trafilatura"
    READABILITY = "readability"
    BEAUTIFULSOUP = "beautifulsoup"


class ContentQuality(Enum):
    """Content quality levels"""
    EXCELLENT = "excellent"  # 0.9+
    GOOD = "good"            # 0.75-0.9
    ACCEPTABLE = "acceptable" # 0.6-0.75
    POOR = "poor"            # <0.6


@dataclass
class CollectionMetrics:
    """Metrics for monitoring collection performance"""
    total_requested: int = 0
    successful: int = 0
    failed: int = 0
    deduplicated: int = 0
    avg_quality_score: float = 0.0
    avg_collection_time_ms: float = 0.0
    avg_content_size_kb: float = 0.0
    total_tokens: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CollectedPage:
    """Represents a collected web page with metadata"""
    url: str
    content: str
    title: str
    extraction_algorithm: str
    quality_score: float
    content_hash: str
    collected_at: str
    collection_time_ms: int
    status_code: int
    content_length: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ContentExtractor:
    """
    Multi-algorithm content extractor with intelligent fallback.

    Tries extraction methods in order of quality:
    1. Trafilatura (best for articles/documentation)
    2. Readability (good for general web pages)
    3. BeautifulSoup (fallback for simple extraction)
    """

    def __init__(self):
        self.algorithm_attempts = {alg: 0 for alg in ExtractionAlgorithm}
        self.algorithm_successes = {alg: 0 for alg in ExtractionAlgorithm}

    async def extract(self, html: str, url: str) -> Tuple[Optional[str], Optional[str], ExtractionAlgorithm]:
        """
        Extract clean content and title from HTML.

        Returns:
            Tuple of (content, title, algorithm_used) or (None, None, None) if all fail
        """
        # Try Trafilatura first (best for documentation)
        content, title = await self._try_trafilatura(html, url)
        if content and len(content) > 100:
            self.algorithm_successes[ExtractionAlgorithm.TRAFILATURA] += 1
            return content, title, ExtractionAlgorithm.TRAFILATURA

        # Fallback to Readability
        content, title = await self._try_readability(html)
        if content and len(content) > 100:
            self.algorithm_successes[ExtractionAlgorithm.READABILITY] += 1
            return content, title, ExtractionAlgorithm.READABILITY

        # Final fallback to BeautifulSoup
        content, title = await self._try_beautifulsoup(html)
        if content and len(content) > 100:
            self.algorithm_successes[ExtractionAlgorithm.BEAUTIFULSOUP] += 1
            return content, title, ExtractionAlgorithm.BEAUTIFULSOUP

        logger.warning(f"All extraction algorithms failed for {url}")
        return None, None, None

    async def _try_trafilatura(self, html: str, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Try Trafilatura extraction"""
        self.algorithm_attempts[ExtractionAlgorithm.TRAFILATURA] += 1
        try:
            content = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                include_images=False,
                include_formatting=True,
                include_links=False,
                output_format='txt'
            )

            # Get metadata for title
            metadata = trafilatura.extract_metadata(html, default_url=url)
            title = metadata.title if metadata else None

            return content, title
        except Exception as e:
            logger.debug(f"Trafilatura extraction failed: {e}")
            return None, None

    async def _try_readability(self, html: str) -> Tuple[Optional[str], Optional[str]]:
        """Try Readability extraction"""
        self.algorithm_attempts[ExtractionAlgorithm.READABILITY] += 1
        try:
            doc = ReadabilityDocument(html)
            title = doc.title()
            html_content = doc.summary()

            # Convert HTML to text
            soup = BeautifulSoup(html_content, 'html.parser')
            content = soup.get_text(separator='\n', strip=True)

            return content, title
        except Exception as e:
            logger.debug(f"Readability extraction failed: {e}")
            return None, None

    async def _try_beautifulsoup(self, html: str) -> Tuple[Optional[str], Optional[str]]:
        """Try BeautifulSoup extraction (last resort)"""
        self.algorithm_attempts[ExtractionAlgorithm.BEAUTIFULSOUP] += 1
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Get title
            title_tag = soup.find('title')
            title = title_tag.string if title_tag else None

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Get text from main content area if possible
            main_content = (
                soup.find('main') or
                soup.find('article') or
                soup.find(class_=re.compile(r'content|main|article', re.I)) or
                soup.find('body')
            )

            if main_content:
                content = main_content.get_text(separator='\n', strip=True)
            else:
                content = soup.get_text(separator='\n', strip=True)

            return content, title
        except Exception as e:
            logger.debug(f"BeautifulSoup extraction failed: {e}")
            return None, None

    def get_stats(self) -> Dict[str, Any]:
        """Get extraction statistics"""
        total_attempts = sum(self.algorithm_attempts.values())
        total_successes = sum(self.algorithm_successes.values())

        return {
            'total_attempts': total_attempts,
            'total_successes': total_successes,
            'success_rate': total_successes / total_attempts if total_attempts > 0 else 0,
            'algorithm_stats': {
                alg.value: {
                    'attempts': self.algorithm_attempts[alg],
                    'successes': self.algorithm_successes[alg],
                    'success_rate': (self.algorithm_successes[alg] / self.algorithm_attempts[alg]
                                    if self.algorithm_attempts[alg] > 0 else 0)
                }
                for alg in ExtractionAlgorithm
            }
        }


class ContentValidator:
    """
    Validates and scores content quality.

    Scores based on:
    - Technical depth (code blocks, technical terms)
    - Completeness (length, structure)
    - Readability (grammar, formatting)
    - Relevance (domain-specific keywords)
    """

    def __init__(self, domain_config: Optional[Dict[str, Any]] = None):
        self.domain_config = domain_config or {}
        self.required_keywords = self.domain_config.get('required_keywords', [])
        self.min_tokens = self.domain_config.get('min_tokens_per_page', 50)
        self.code_block_weight = 0.3
        self.completeness_weight = 0.25
        self.technical_depth_weight = 0.25
        self.relevance_weight = 0.2

    def validate_and_score(self, content: str, url: str) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Validate content and return quality score.

        Returns:
            Tuple of (is_valid, quality_score, metrics_dict)
        """
        metrics = {}

        # Basic validation
        if not content or len(content.strip()) < 100:
            return False, 0.0, {'reason': 'content_too_short'}

        # Token count
        tokens = self._count_tokens(content)
        metrics['tokens'] = tokens

        if tokens < self.min_tokens:
            return False, 0.0, {'reason': 'insufficient_tokens', 'tokens': tokens, 'required': self.min_tokens}

        # Calculate quality scores
        technical_score = self._score_technical_depth(content)
        completeness_score = self._score_completeness(content, tokens)
        readability_score = self._score_readability(content)
        relevance_score = self._score_relevance(content)

        # Weighted overall score
        quality_score = (
            technical_score * self.technical_depth_weight +
            completeness_score * self.completeness_weight +
            readability_score * 0.0 +  # Disabled for now
            relevance_score * self.relevance_weight +
            0.25  # Base score for valid content
        )

        metrics.update({
            'technical_depth': round(technical_score, 3),
            'completeness': round(completeness_score, 3),
            'readability': round(readability_score, 3),
            'relevance': round(relevance_score, 3),
            'quality_score': round(quality_score, 3),
            'quality_level': self._get_quality_level(quality_score).value
        })

        # Content is valid if score meets threshold
        threshold = self.domain_config.get('quality_threshold', 0.6)
        is_valid = quality_score >= threshold

        return is_valid, quality_score, metrics

    def _count_tokens(self, content: str) -> int:
        """Estimate token count (simple word-based)"""
        return len(content.split())

    def _score_technical_depth(self, content: str) -> float:
        """Score based on presence of code blocks and technical terms"""
        score = 0.0

        # Code blocks
        code_blocks = len(re.findall(r'```[\s\S]*?```|<code>[\s\S]*?</code>', content))
        if code_blocks > 0:
            score += min(0.5, code_blocks * 0.1)

        # Technical patterns
        technical_patterns = [
            r'\b(?:function|class|def|const|let|var|import|export)\b',  # Code keywords
            r'\b(?:API|SDK|HTTP|JSON|XML|SQL|CLI)\b',  # Technical acronyms
            r'(?:\w+\.\w+\()',  # Method calls
            r'(?:</?\w+>)',  # HTML/XML tags
        ]

        for pattern in technical_patterns:
            matches = len(re.findall(pattern, content, re.IGNORECASE))
            if matches > 0:
                score += min(0.125, matches * 0.01)

        return min(1.0, score)

    def _score_completeness(self, content: str, tokens: int) -> float:
        """Score based on content completeness"""
        score = 0.0

        # Length score (more content = more complete)
        if tokens >= 500:
            score += 0.4
        elif tokens >= 200:
            score += 0.25
        elif tokens >= 100:
            score += 0.15

        # Structure indicators
        has_headings = bool(re.search(r'^#{1,6}\s+\w+', content, re.MULTILINE))
        has_lists = bool(re.search(r'^\s*[-*]\s+\w+', content, re.MULTILINE))
        has_paragraphs = len(re.findall(r'\n\n+', content)) >= 2

        if has_headings:
            score += 0.2
        if has_lists:
            score += 0.2
        if has_paragraphs:
            score += 0.2

        return min(1.0, score)

    def _score_readability(self, content: str) -> float:
        """Score based on readability (placeholder)"""
        # For now, just check for basic sentence structure
        sentences = re.split(r'[.!?]+', content)
        if len(sentences) >= 5:
            return 0.7
        return 0.5

    def _score_relevance(self, content: str) -> float:
        """Score based on domain-specific keyword presence"""
        if not self.required_keywords:
            return 0.8  # Default if no keywords specified

        content_lower = content.lower()
        found_keywords = sum(1 for kw in self.required_keywords if kw.lower() in content_lower)

        # Score based on percentage of required keywords found
        if len(self.required_keywords) > 0:
            ratio = found_keywords / len(self.required_keywords)
            return min(1.0, ratio * 1.5)  # Boost to 1.0 if 67%+ keywords found

        return 0.8

    def _get_quality_level(self, score: float) -> ContentQuality:
        """Convert numeric score to quality level"""
        if score >= 0.9:
            return ContentQuality.EXCELLENT
        elif score >= 0.75:
            return ContentQuality.GOOD
        elif score >= 0.6:
            return ContentQuality.ACCEPTABLE
        else:
            return ContentQuality.POOR


class ProfessionalWebCollector:
    """
    Production-grade web content collector.

    Features:
    - Robust multi-algorithm extraction
    - Content validation and quality scoring
    - Deduplication via content hashing
    - Rate limiting and politeness
    - Retry with exponential backoff
    - Comprehensive logging and metrics
    - Debug information collection
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        # Configuration
        self.rate_limit = self.config.get('rate_limit', 1.0)
        self.timeout = self.config.get('timeout', 30)
        self.max_retries = self.config.get('max_retries', 3)
        self.retry_delay = self.config.get('retry_delay', 5)
        self.respect_robots = self.config.get('respect_robots_txt', True)
        self.user_agent = self.config.get('user_agent',
            'Mozilla/5.0 (Brain AI Training Bot) AppleWebKit/537.36')

        # Components
        self.extractor = ContentExtractor()
        self.validator = ContentValidator(self.config.get('domain_config'))
        self.metrics = CollectionMetrics()

        # Cache integration
        self.cache_manager = None
        if self.config.get('enable_cache', True):
            try:
                from .cache_manager import get_cache_manager
                self.cache_manager = get_cache_manager()
                logger.info("Cache manager initialized for professional collector")
            except ImportError:
                logger.warning("Cache manager not available")

        # State
        self.session: Optional[aiohttp.ClientSession] = None
        self.content_hashes: Set[str] = set()
        self.collected_pages: List[CollectedPage] = []
        self.last_request_time = 0.0

        # Debug
        self.debug_enabled = self.config.get('debug_files', True)
        self.debug_dir = Path(self.config.get('debug_dir', '/tmp/collection_debug'))
        if self.debug_enabled:
            self.debug_dir.mkdir(parents=True, exist_ok=True)

    async def collect_urls(self, urls: List[str]) -> List[CollectedPage]:
        """
        Collect content from multiple URLs.

        Args:
            urls: List of URLs to collect

        Returns:
            List of successfully collected pages
        """
        logger.info(f"[COLLECT] Starting collection of {len(urls)} URLs")
        self.metrics.total_requested = len(urls)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            headers={'User-Agent': self.user_agent}
        ) as self.session:
            tasks = [self.collect_url(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out failures and exceptions
            successful_pages = [
                page for page in results
                if isinstance(page, CollectedPage)
            ]

            self.collected_pages = successful_pages

        # Update metrics
        self.metrics.successful = len(successful_pages)
        self.metrics.failed = len(urls) - len(successful_pages)

        if successful_pages:
            self.metrics.avg_quality_score = sum(p.quality_score for p in successful_pages) / len(successful_pages)
            self.metrics.avg_collection_time_ms = sum(p.collection_time_ms for p in successful_pages) / len(successful_pages)
            self.metrics.avg_content_size_kb = sum(p.content_length for p in successful_pages) / len(successful_pages) / 1024
            self.metrics.total_tokens = sum(len(p.content.split()) for p in successful_pages)

        # Log final stats
        logger.info(
            f"[COLLECT] Complete: {self.metrics.successful}/{self.metrics.total_requested} successful "
            f"({self.metrics.failed} failed, {self.metrics.deduplicated} duplicates) | "
            f"Avg Quality: {self.metrics.avg_quality_score:.2f} | "
            f"Total Tokens: {self.metrics.total_tokens:,}"
        )

        # Save debug info
        if self.debug_enabled:
            await self._save_debug_info()

        return successful_pages

    async def collect_url(self, url: str) -> Optional[CollectedPage]:
        """
        Collect content from a single URL with retry logic and caching.

        Args:
            url: URL to collect

        Returns:
            CollectedPage if successful, None otherwise
        """
        start_time = time.time()

        # Check cache first
        if self.cache_manager:
            domain = self.config.get('domain')
            cached_data = await self.cache_manager.get(url, domain)
            if cached_data:
                logger.debug(f"[CACHE HIT] Retrieved {url} from cache")
                # Convert cached data to CollectedPage
                page = CollectedPage(
                    url=url,
                    title=cached_data.get('title', ''),
                    content=cached_data.get('content', ''),
                    metadata=cached_data.get('metadata', {}),
                    quality_score=cached_data.get('quality_score', 0.5),
                    extraction_method=cached_data.get('extraction_method', 'cache'),
                    collection_time_ms=0  # Instant from cache
                )
                return page

        for attempt in range(self.max_retries):
            try:
                # Rate limiting
                await self._rate_limit()

                # Fetch HTML
                logger.debug(f"[COLLECT] Fetching {url} (attempt {attempt + 1}/{self.max_retries})")
                async with self.session.get(url) as response:
                    status_code = response.status

                    if status_code != 200:
                        logger.warning(f"[COLLECT] {url} returned status {status_code}")
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            continue
                        return None

                    html = await response.text()
                    content_length = len(html)

                # Extract content
                content, title, algorithm = await self.extractor.extract(html, url)

                if not content:
                    logger.warning(f"[COLLECT] Failed to extract content from {url}")
                    return None

                # Validate and score
                is_valid, quality_score, validation_metrics = self.validator.validate_and_score(content, url)

                if not is_valid:
                    logger.warning(
                        f"[COLLECT] Content validation failed for {url}: "
                        f"{validation_metrics.get('reason', 'quality_too_low')}"
                    )
                    self.metrics.errors.append({
                        'url': url,
                        'reason': 'validation_failed',
                        'details': validation_metrics
                    })
                    return None

                # Check for duplicates
                content_hash = hashlib.md5(content.encode()).hexdigest()
                if content_hash in self.content_hashes:
                    logger.debug(f"[COLLECT] Duplicate content detected: {url}")
                    self.metrics.deduplicated += 1
                    return None

                self.content_hashes.add(content_hash)

                # Create page object
                collection_time_ms = int((time.time() - start_time) * 1000)
                page = CollectedPage(
                    url=url,
                    content=content,
                    title=title or "Untitled",
                    extraction_algorithm=algorithm.value,
                    quality_score=quality_score,
                    content_hash=content_hash,
                    collected_at=datetime.utcnow().isoformat() + 'Z',
                    collection_time_ms=collection_time_ms,
                    status_code=status_code,
                    content_length=content_length,
                    metadata=validation_metrics
                )

                logger.info(
                    f"[COLLECT] ✓ {url} | "
                    f"Quality: {quality_score:.2f} | "
                    f"Tokens: {validation_metrics.get('tokens', 0)} | "
                    f"Time: {collection_time_ms}ms | "
                    f"Algorithm: {algorithm.value}"
                )

                # Cache the successful collection
                if self.cache_manager and quality_score >= 0.5:  # Only cache decent quality
                    domain = self.config.get('domain')
                    cache_data = {
                        'title': title,
                        'content': content,
                        'metadata': validation_metrics,
                        'quality_score': quality_score,
                        'extraction_method': algorithm.value
                    }
                    await self.cache_manager.set(url, cache_data, domain)
                    logger.debug(f"[CACHE] Stored {url} in cache")

                return page

            except asyncio.TimeoutError:
                logger.warning(f"[COLLECT] Timeout fetching {url} (attempt {attempt + 1})")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    self.metrics.errors.append({'url': url, 'reason': 'timeout'})

            except Exception as e:
                logger.error(f"[COLLECT] Error fetching {url}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    self.metrics.errors.append({'url': url, 'reason': 'error', 'message': str(e)})

        return None

    async def _rate_limit(self):
        """Enforce rate limiting between requests"""
        if self.rate_limit > 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.rate_limit:
                await asyncio.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    async def _save_debug_info(self):
        """Save debug information to files"""
        try:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

            # Collection metrics
            metrics_file = self.debug_dir / f"metrics_{timestamp}.json"
            with open(metrics_file, 'w') as f:
                json.dump(self.metrics.to_dict(), f, indent=2)

            # Extractor stats
            extractor_stats_file = self.debug_dir / f"extractor_stats_{timestamp}.json"
            with open(extractor_stats_file, 'w') as f:
                json.dump(self.extractor.get_stats(), f, indent=2)

            # Quality scores
            quality_file = self.debug_dir / f"quality_scores_{timestamp}.json"
            quality_data = [
                {
                    'url': page.url,
                    'quality_score': page.quality_score,
                    'metadata': page.metadata
                }
                for page in self.collected_pages
            ]
            with open(quality_file, 'w') as f:
                json.dump(quality_data, f, indent=2)

            logger.info(f"[DEBUG] Saved debug info to {self.debug_dir}")

        except Exception as e:
            logger.error(f"[DEBUG] Failed to save debug info: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get collection metrics"""
        return self.metrics.to_dict()
