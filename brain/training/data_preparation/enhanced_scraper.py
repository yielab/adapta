"""
Enhanced Professional Web Scraper with Advanced Features
"""

import asyncio
import aiohttp
import hashlib
import json
import logging
import random
import re
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from urllib.parse import urlparse, urljoin, urlunparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import trafilatura
from readability import Readability

logger = logging.getLogger(__name__)


class ProxyManager:
    """Manages proxy rotation for anonymous scraping"""

    def __init__(self, proxy_list: Optional[List[str]] = None):
        self.proxies = proxy_list or []
        self.current_index = 0
        self.failed_proxies = set()
        self.proxy_stats = {}

    def get_proxy(self) -> Optional[str]:
        """Get next working proxy"""
        if not self.proxies:
            return None

        attempts = 0
        while attempts < len(self.proxies):
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)

            if proxy not in self.failed_proxies:
                return proxy
            attempts += 1

        return None

    def mark_failed(self, proxy: str):
        """Mark proxy as failed"""
        self.failed_proxies.add(proxy)
        if proxy in self.proxy_stats:
            self.proxy_stats[proxy]['failures'] += 1

    def mark_success(self, proxy: str, response_time: float):
        """Track successful proxy usage"""
        if proxy not in self.proxy_stats:
            self.proxy_stats[proxy] = {'successes': 0, 'failures': 0, 'avg_time': 0}

        stats = self.proxy_stats[proxy]
        stats['successes'] += 1
        stats['avg_time'] = (stats['avg_time'] * (stats['successes'] - 1) + response_time) / stats['successes']


class ContentExtractor:
    """Advanced content extraction with multiple algorithms"""

    @staticmethod
    def extract_with_trafilatura(html: str, url: str) -> Dict[str, Any]:
        """Extract content using Trafilatura"""
        try:
            result = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                include_links=True,
                output_format='json',
                with_metadata=True
            )
            if result:
                return json.loads(result)
        except Exception as e:
            logger.debug(f"Trafilatura extraction failed: {e}")
        return {}

    @staticmethod
    def extract_with_readability(html: str, url: str) -> Dict[str, Any]:
        """Extract content using Readability"""
        try:
            doc = Readability(html, url)
            summary = doc.summary()
            return {
                'title': doc.title(),
                'content': BeautifulSoup(summary, 'html.parser').get_text(),
                'excerpt': doc.excerpt() if hasattr(doc, 'excerpt') else None
            }
        except Exception as e:
            logger.debug(f"Readability extraction failed: {e}")
        return {}

    @staticmethod
    def extract_structured_data(soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract structured data (JSON-LD, microdata, etc.)"""
        structured = {}

        # JSON-LD
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                structured['json_ld'] = structured.get('json_ld', [])
                structured['json_ld'].append(data)
            except:
                pass

        # OpenGraph
        og_data = {}
        for meta in soup.find_all('meta', property=re.compile(r'^og:')):
            og_data[meta.get('property', '').replace('og:', '')] = meta.get('content')
        if og_data:
            structured['opengraph'] = og_data

        # Twitter Cards
        twitter_data = {}
        for meta in soup.find_all('meta', {'name': re.compile(r'^twitter:')}):
            twitter_data[meta.get('name', '').replace('twitter:', '')] = meta.get('content')
        if twitter_data:
            structured['twitter'] = twitter_data

        return structured

    @staticmethod
    def clean_text(text: str) -> str:
        """Advanced text cleaning"""
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove special characters but keep punctuation
        text = re.sub(r'[^\w\s\.\,\!\?\-\:\;\(\)\"\']+', ' ', text)

        # Fix common encoding issues
        replacements = {
            'â€™': "'",
            'â€œ': '"',
            'â€': '"',
            'â€"': '-',
            'â€¦': '...',
            'Ã©': 'é',
            'Ã¨': 'è',
            'Ã ': 'à'
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

        return text.strip()


class RobotChecker:
    """Checks robots.txt compliance"""

    def __init__(self):
        self.robot_cache = {}
        self.cache_duration = timedelta(hours=24)

    async def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        """Check if URL can be fetched according to robots.txt"""
        parsed = urlparse(url)
        robot_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        # Check cache
        if robot_url in self.robot_cache:
            cached_time, robot_parser = self.robot_cache[robot_url]
            if datetime.now() - cached_time < self.cache_duration:
                return robot_parser.can_fetch(user_agent, url)

        # Fetch and parse robots.txt
        try:
            robot_parser = RobotFileParser()
            robot_parser.set_url(robot_url)
            robot_parser.read()

            self.robot_cache[robot_url] = (datetime.now(), robot_parser)
            return robot_parser.can_fetch(user_agent, url)
        except:
            # If robots.txt is not accessible, assume we can fetch
            return True


class DuplicateDetector:
    """Detects and filters duplicate content"""

    def __init__(self, similarity_threshold: float = 0.85):
        self.content_hashes = set()
        self.url_patterns = set()
        self.similarity_threshold = similarity_threshold
        self.shingle_size = 5

    def is_duplicate(self, content: str, url: str) -> bool:
        """Check if content is duplicate"""
        # Quick hash check
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        if content_hash in self.content_hashes:
            return True

        # URL pattern check (e.g., /page/1, /page/2)
        url_pattern = re.sub(r'\d+', 'N', url)
        if url_pattern in self.url_patterns:
            return True

        # Add to seen
        self.content_hashes.add(content_hash)
        self.url_patterns.add(url_pattern)

        return False

    def get_shingles(self, text: str) -> Set[str]:
        """Generate shingles for similarity comparison"""
        words = text.lower().split()
        shingles = set()
        for i in range(len(words) - self.shingle_size + 1):
            shingle = ' '.join(words[i:i + self.shingle_size])
            shingles.add(hashlib.md5(shingle.encode()).hexdigest())
        return shingles

    def jaccard_similarity(self, shingles1: Set[str], shingles2: Set[str]) -> float:
        """Calculate Jaccard similarity between shingle sets"""
        if not shingles1 or not shingles2:
            return 0.0
        intersection = len(shingles1 & shingles2)
        union = len(shingles1 | shingles2)
        return intersection / union if union > 0 else 0.0


class JavaScriptRenderer:
    """Handles JavaScript-heavy websites"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None

    def setup_driver(self):
        """Setup Selenium WebDriver"""
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')

        # Stealth mode
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--disable-blink-features=AutomationControlled")

        self.driver = webdriver.Chrome(options=options)

        # Execute stealth scripts
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            '''
        })

    async def render_page(self, url: str, wait_for: Optional[str] = None, wait_time: int = 10) -> str:
        """Render JavaScript page and return HTML"""
        if not self.driver:
            self.setup_driver()

        try:
            self.driver.get(url)

            if wait_for:
                wait = WebDriverWait(self.driver, wait_time)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_for)))
            else:
                await asyncio.sleep(2)  # Default wait

            # Scroll to load lazy content
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(1)

            return self.driver.page_source
        except Exception as e:
            logger.error(f"JavaScript rendering failed: {e}")
            return ""

    def cleanup(self):
        """Cleanup WebDriver"""
        if self.driver:
            self.driver.quit()


class EnhancedWebScraper:
    """Professional-grade web scraper with all advanced features"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        # Components
        self.proxy_manager = ProxyManager(self.config.get('proxies', []))
        self.content_extractor = ContentExtractor()
        self.robot_checker = RobotChecker()
        self.duplicate_detector = DuplicateDetector()
        self.js_renderer = None

        # User agents
        self.ua = UserAgent()
        self.custom_headers = self.config.get('headers', {})

        # Rate limiting
        self.rate_limit = self.config.get('rate_limit', 1.0)
        self.last_request_time = {}

        # Session management
        self.session = None
        self.cookies = {}

        # Cache
        self.cache_dir = Path(self.config.get('cache_dir', '/tmp/scraper_cache'))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_duration = timedelta(hours=self.config.get('cache_hours', 24))

        # Statistics
        self.stats = {
            'total_requests': 0,
            'successful': 0,
            'failed': 0,
            'cached': 0,
            'duplicates': 0,
            'robots_blocked': 0
        }

    async def setup(self):
        """Setup async session"""
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=10)
        self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
        if self.js_renderer:
            self.js_renderer.cleanup()

    def get_headers(self) -> Dict[str, str]:
        """Get randomized headers"""
        headers = {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }

        # Add custom headers
        headers.update(self.custom_headers)

        # Randomize order
        headers_list = list(headers.items())
        random.shuffle(headers_list)

        return dict(headers_list)

    async def apply_rate_limit(self, domain: str):
        """Apply rate limiting per domain"""
        if domain in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain]
            if elapsed < self.rate_limit:
                await asyncio.sleep(self.rate_limit - elapsed)

        self.last_request_time[domain] = time.time()

    def get_cache_path(self, url: str) -> Path:
        """Get cache file path for URL"""
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.json"

    def load_from_cache(self, url: str) -> Optional[Dict[str, Any]]:
        """Load cached content if available and fresh"""
        cache_path = self.get_cache_path(url)

        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    cached = json.load(f)

                cached_time = datetime.fromisoformat(cached['timestamp'])
                if datetime.now() - cached_time < self.cache_duration:
                    self.stats['cached'] += 1
                    logger.debug(f"Loaded from cache: {url}")
                    return cached['data']
            except Exception as e:
                logger.debug(f"Cache load failed: {e}")

        return None

    def save_to_cache(self, url: str, data: Dict[str, Any]):
        """Save content to cache"""
        cache_path = self.get_cache_path(url)

        try:
            with open(cache_path, 'w') as f:
                json.dump({
                    'url': url,
                    'timestamp': datetime.now().isoformat(),
                    'data': data
                }, f, indent=2)
        except Exception as e:
            logger.debug(f"Cache save failed: {e}")

    async def fetch_with_retry(
        self,
        url: str,
        max_retries: int = 3,
        use_js: bool = False
    ) -> Optional[str]:
        """Fetch URL with retry logic and proxy rotation"""

        for attempt in range(max_retries):
            try:
                # Use JavaScript renderer if needed
                if use_js:
                    if not self.js_renderer:
                        self.js_renderer = JavaScriptRenderer()
                    html = await self.js_renderer.render_page(url)
                    if html:
                        return html

                # Regular HTTP fetch
                proxy = self.proxy_manager.get_proxy()
                headers = self.get_headers()

                start_time = time.time()

                async with self.session.get(
                    url,
                    headers=headers,
                    proxy=proxy,
                    ssl=False,
                    allow_redirects=True
                ) as response:
                    if response.status == 200:
                        html = await response.text()

                        # Track success
                        if proxy:
                            self.proxy_manager.mark_success(proxy, time.time() - start_time)

                        return html

                    elif response.status == 403 or response.status == 429:
                        # Rate limited or blocked
                        if proxy:
                            self.proxy_manager.mark_failed(proxy)

                        # Exponential backoff
                        await asyncio.sleep(2 ** attempt)

                    else:
                        logger.warning(f"HTTP {response.status} for {url}")

            except Exception as e:
                logger.debug(f"Fetch attempt {attempt + 1} failed: {e}")

                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        return None

    async def scrape_url(self, url: str, use_js: bool = False) -> Optional[Dict[str, Any]]:
        """Scrape a single URL with all enhancements"""

        # Check cache
        cached = self.load_from_cache(url)
        if cached:
            return cached

        # Check robots.txt
        can_fetch = await self.robot_checker.can_fetch(url)
        if not can_fetch:
            logger.info(f"Blocked by robots.txt: {url}")
            self.stats['robots_blocked'] += 1
            return None

        # Apply rate limiting
        domain = urlparse(url).netloc
        await self.apply_rate_limit(domain)

        # Fetch content
        self.stats['total_requests'] += 1
        html = await self.fetch_with_retry(url, use_js=use_js)

        if not html:
            self.stats['failed'] += 1
            return None

        self.stats['successful'] += 1

        # Parse with BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # Extract content using multiple methods
        data = {
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'title': soup.title.string if soup.title else None
        }

        # Try Trafilatura
        traf_data = self.content_extractor.extract_with_trafilatura(html, url)
        if traf_data:
            data['trafilatura'] = traf_data

        # Try Readability
        read_data = self.content_extractor.extract_with_readability(html, url)
        if read_data:
            data['readability'] = read_data

        # Extract structured data
        structured = self.content_extractor.extract_structured_data(soup)
        if structured:
            data['structured'] = structured

        # Extract main content (fallback)
        if not traf_data and not read_data:
            # Remove script and style elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                element.decompose()

            text = soup.get_text()
            data['content'] = self.content_extractor.clean_text(text)

        # Check for duplicates
        main_content = (
            traf_data.get('text', '') if traf_data else
            read_data.get('content', '') if read_data else
            data.get('content', '')
        )

        if self.duplicate_detector.is_duplicate(main_content, url):
            logger.info(f"Duplicate content detected: {url}")
            self.stats['duplicates'] += 1
            return None

        # Extract links for crawling
        data['links'] = []
        for link in soup.find_all('a', href=True):
            absolute_url = urljoin(url, link['href'])
            if absolute_url.startswith('http'):
                data['links'].append(absolute_url)

        # Extract images
        data['images'] = []
        for img in soup.find_all('img', src=True):
            absolute_url = urljoin(url, img['src'])
            data['images'].append({
                'src': absolute_url,
                'alt': img.get('alt', ''),
                'title': img.get('title', '')
            })

        # Save to cache
        self.save_to_cache(url, data)

        return data

    async def crawl(
        self,
        start_urls: List[str],
        max_depth: int = 2,
        max_pages: int = 100,
        follow_external: bool = False,
        use_js: bool = False
    ) -> List[Dict[str, Any]]:
        """Crawl websites starting from given URLs"""

        if not self.session:
            await self.setup()

        results = []
        visited = set()
        queue = deque([(url, 0) for url in start_urls])

        # Get allowed domains
        allowed_domains = set()
        if not follow_external:
            for url in start_urls:
                domain = urlparse(url).netloc
                allowed_domains.add(domain)

        while queue and len(results) < max_pages:
            url, depth = queue.popleft()

            if url in visited or depth > max_depth:
                continue

            visited.add(url)

            # Scrape page
            logger.info(f"Scraping: {url} (depth: {depth})")
            data = await self.scrape_url(url, use_js=use_js)

            if data:
                results.append(data)

                # Add links to queue
                if depth < max_depth:
                    for link in data.get('links', []):
                        link_domain = urlparse(link).netloc

                        if follow_external or link_domain in allowed_domains:
                            if link not in visited:
                                queue.append((link, depth + 1))

        # Log statistics
        logger.info(f"""
        Scraping complete:
        - Total requests: {self.stats['total_requests']}
        - Successful: {self.stats['successful']}
        - Failed: {self.stats['failed']}
        - Cached: {self.stats['cached']}
        - Duplicates: {self.stats['duplicates']}
        - Robots blocked: {self.stats['robots_blocked']}
        - Pages scraped: {len(results)}
        """)

        return results

    async def scrape_sitemap(self, sitemap_url: str) -> List[str]:
        """Extract URLs from sitemap"""
        html = await self.fetch_with_retry(sitemap_url)
        if not html:
            return []

        urls = []
        soup = BeautifulSoup(html, 'xml')

        for loc in soup.find_all('loc'):
            urls.append(loc.text)

        # Check for nested sitemaps
        for sitemap in soup.find_all('sitemap'):
            nested_loc = sitemap.find('loc')
            if nested_loc:
                nested_urls = await self.scrape_sitemap(nested_loc.text)
                urls.extend(nested_urls)

        return urls


# Integration with existing pipeline
class ProfessionalWebCollector:
    """Wrapper to integrate with existing pipeline"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.scraper = EnhancedWebScraper(config)

    async def collect(self, source) -> List[Dict[str, Any]]:
        """Collect data from source"""
        await self.scraper.setup()

        try:
            if source.type == 'url':
                # Single URL
                data = await self.scraper.scrape_url(
                    source.location,
                    use_js=self.config.get('use_js', False)
                )
                return [data] if data else []

            elif source.type == 'sitemap':
                # Sitemap crawl
                urls = await self.scraper.scrape_sitemap(source.location)
                results = []

                for url in urls[:self.config.get('max_pages', 100)]:
                    data = await self.scraper.scrape_url(url)
                    if data:
                        results.append(data)

                return results

            elif source.type == 'crawl':
                # Deep crawl
                return await self.scraper.crawl(
                    [source.location],
                    max_depth=self.config.get('max_depth', 2),
                    max_pages=self.config.get('max_pages', 100),
                    follow_external=self.config.get('follow_external', False),
                    use_js=self.config.get('use_js', False)
                )

            else:
                # Default crawl
                return await self.scraper.crawl(
                    [source.location],
                    max_depth=2,
                    max_pages=100
                )

        finally:
            await self.scraper.cleanup()