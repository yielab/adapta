"""
Data collection implementations for various sources
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin, quote
import re
import logging
from pathlib import Path
import json
import time
from .base import DataCollector, DataSource

logger = logging.getLogger(__name__)

# Import professional collector if available
try:
    from .professional_collector import ProfessionalWebCollector
    PROFESSIONAL_COLLECTOR_AVAILABLE = True
except ImportError:
    PROFESSIONAL_COLLECTOR_AVAILABLE = False
    logger.info("Professional collector not available, using basic implementation")


class WebScraper(DataCollector):
    """
    Professional web scraper with enhanced capabilities.
    Falls back to basic implementation if enhanced scraper is not available.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        # Use professional collector if available
        if PROFESSIONAL_COLLECTOR_AVAILABLE and self.config.get('use_professional', True):
            self.professional_collector = ProfessionalWebCollector(config)
            self.use_professional = True
            logger.info("Using professional web collector with advanced features")
        else:
            self.professional_collector = None
            self.use_professional = False

        # Basic scraper properties (for fallback)
        self.session = None
        self.rate_limit = self.config.get('rate_limit', 1.0)  # seconds between requests
        self.max_depth = self.config.get('max_depth', 3)
        self.allowed_domains = self.config.get('allowed_domains', [])
        self.blocked_domains = self.config.get('blocked_domains', [])
        self.user_agent = self.config.get('user_agent',
            'Mozilla/5.0 (Brain LLM Training Bot) AppleWebKit/537.36')

        # Store collection metrics for reporting
        self.collection_metrics = None

    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={'User-Agent': self.user_agent}
            )
        return self.session

    async def collect(self, source: DataSource) -> List[Dict[str, Any]]:
        """Collect data from a web source using professional or basic scraper"""

        # Use professional collector if available
        if self.use_professional:
            try:
                return await self._collect_with_professional(source)
            except Exception as e:
                logger.warning(f"Professional collector failed, falling back to basic: {e}")
                self.use_professional = False  # Disable for future calls

        # Basic implementation (fallback)
        if source.type != 'url':
            # Convert to url type for basic scraper
            source = DataSource(
                type='url',
                location=source.location,
                metadata=source.metadata,
                version=source.version
            )

        # Check cache first
        cached = self.get_cached_data(source, max_age_hours=self.config.get('cache_hours', 24))
        if cached:
            logger.info(f"Using cached data for {source.location}")
            return cached

        collected_data = []
        try:
            session = await self._get_session()

            # Fetch the main page
            content = await self._fetch_url(session, source.location)
            if content:
                data = {
                    'url': source.location,
                    'content': content,
                    'type': 'webpage',
                    'metadata': source.metadata
                }
                collected_data.append(data)

                # Find and follow links if configured
                if self.config.get('follow_links', False):
                    links = self._extract_links(content, source.location)
                    for link in links[:self.config.get('max_links', 10)]:
                        await asyncio.sleep(self.rate_limit)
                        link_content = await self._fetch_url(session, link)
                        if link_content:
                            collected_data.append({
                                'url': link,
                                'content': link_content,
                                'type': 'webpage',
                                'metadata': {'parent': source.location}
                            })

            # Cache the results
            self.cache_data(source, collected_data)

        finally:
            if self.session and self.config.get('close_session', True):
                await self.session.close()
                self.session = None

        return collected_data

    async def _collect_with_professional(self, source: DataSource) -> List[Dict[str, Any]]:
        """
        Collect data using the professional collector.
        Converts DataSource to URL list and transforms results back.
        """
        # For single URL sources, collect directly
        if source.type == 'url':
            urls = [source.location]
        else:
            # For other types, try to extract URLs from location
            urls = [source.location]

        # Collect pages using professional collector
        collected_pages = await self.professional_collector.collect_urls(urls)

        # Store metrics for later retrieval
        self.collection_metrics = self.professional_collector.get_metrics()

        # Convert CollectedPage objects to Dict format expected by pipeline
        collected_data = []
        for page in collected_pages:
            data = {
                'url': page.url,
                'content': page.content,
                'type': 'webpage',
                'metadata': {
                    **source.metadata,
                    'title': page.title,
                    'extraction_algorithm': page.extraction_algorithm,
                    'quality_score': page.quality_score,
                    'content_hash': page.content_hash,
                    'collected_at': page.collected_at,
                    'collection_time_ms': page.collection_time_ms,
                    'status_code': page.status_code,
                    'content_length': page.content_length,
                    **page.metadata
                }
            }
            collected_data.append(data)

        return collected_data

    def get_collection_metrics(self) -> Optional[Dict[str, Any]]:
        """Get metrics from the last collection run"""
        return self.collection_metrics

    async def _fetch_url(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Fetch and convert URL content to markdown"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    html = await response.text()
                    return self._html_to_markdown(html, url)
                else:
                    logger.warning(f"Failed to fetch {url}: HTTP {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def _html_to_markdown(self, html: str, base_url: str) -> str:
        """Convert HTML to clean markdown format"""
        soup = BeautifulSoup(html, 'html.parser')

        # Remove script and style elements
        for script in soup(['script', 'style', 'nav', 'header', 'footer']):
            script.decompose()

        # Focus on main content areas
        main_content = None
        for selector in ['main', 'article', '#content', '.content', '#main', '.documentation']:
            main_content = soup.select_one(selector)
            if main_content:
                break

        if not main_content:
            main_content = soup.body if soup.body else soup

        # Convert to markdown-like format
        markdown = []
        for element in main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'code', 'ul', 'ol', 'li']):
            if element.name.startswith('h'):
                level = int(element.name[1])
                markdown.append(f"\n{'#' * level} {element.get_text().strip()}\n")
            elif element.name == 'p':
                text = element.get_text().strip()
                if text:
                    markdown.append(f"\n{text}\n")
            elif element.name == 'pre' or element.name == 'code':
                code = element.get_text().strip()
                if code:
                    markdown.append(f"\n```\n{code}\n```\n")
            elif element.name == 'li':
                markdown.append(f"- {element.get_text().strip()}")

        return '\n'.join(markdown)

    def _extract_links(self, content: str, base_url: str) -> List[str]:
        """Extract relevant links from content"""
        links = []
        # Simple regex for markdown links
        pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
        for match in re.finditer(pattern, content):
            link = match.group(2)
            if not link.startswith('http'):
                link = urljoin(base_url, link)

            # Filter based on allowed/blocked domains
            domain = urlparse(link).netloc
            if self.allowed_domains and domain not in self.allowed_domains:
                continue
            if domain in self.blocked_domains:
                continue

            links.append(link)

        return links


class DocumentationCrawler(DataCollector):
    """
    Specialized crawler for documentation sites.
    Handles sitemaps, navigation trees, and preserves document hierarchy.
    Uses professional collector for efficient batch collection.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.scraper = WebScraper(config)
        self.sitemap_patterns = self.config.get('sitemap_patterns',
            ['sitemap.xml', 'sitemap_index.xml', 'llms.txt'])
        self.collection_metrics = None

    async def collect(self, source: DataSource) -> List[Dict[str, Any]]:
        """Collect documentation from a site"""
        if source.type == 'sitemap':
            return await self._collect_from_sitemap(source.location)
        elif source.type == 'documentation':
            return await self._collect_documentation_tree(source.location)
        else:
            # Fall back to regular scraping
            return await self.scraper.collect(source)

    def get_collection_metrics(self) -> Optional[Dict[str, Any]]:
        """Get metrics from the last collection run"""
        return self.collection_metrics or self.scraper.get_collection_metrics()

    async def _collect_from_sitemap(self, sitemap_url: str) -> List[Dict[str, Any]]:
        """Parse and collect from XML sitemap using professional collector if available"""
        collected_data = []

        try:
            session = await self.scraper._get_session()
            async with session.get(sitemap_url) as response:
                if response.status == 200:
                    sitemap_xml = await response.text()
                    urls_info = self._parse_sitemap(sitemap_xml)

                    logger.info(f"Found {len(urls_info)} URLs in sitemap")

                    # Limit to max_pages
                    max_pages = self.config.get('max_pages', 100)
                    urls_info = urls_info[:max_pages]

                    # If professional collector is available, use batch collection
                    if (self.scraper.use_professional and
                        hasattr(self.scraper, 'professional_collector')):

                        # Extract just the URLs for batch collection
                        urls = [url_info['url'] for url_info in urls_info]

                        logger.info(f"Using professional collector for batch collection of {len(urls)} URLs")
                        collected_pages = await self.scraper.professional_collector.collect_urls(urls)

                        # Store metrics
                        self.collection_metrics = self.scraper.professional_collector.get_metrics()

                        # Convert to expected format and add sitemap metadata
                        for page in collected_pages:
                            # Find matching url_info for metadata
                            url_info = next((u for u in urls_info if u['url'] == page.url), {})

                            collected_data.append({
                                'url': page.url,
                                'content': page.content,
                                'type': 'documentation',
                                'metadata': {
                                    'title': page.title,
                                    'extraction_algorithm': page.extraction_algorithm,
                                    'quality_score': page.quality_score,
                                    'lastmod': url_info.get('lastmod'),
                                    'priority': url_info.get('priority'),
                                    'source': 'sitemap',
                                    **page.metadata
                                }
                            })
                    else:
                        # Fallback: collect one by one with basic scraper
                        for url_info in urls_info:
                            await asyncio.sleep(self.scraper.rate_limit)
                            content = await self.scraper._fetch_url(session, url_info['url'])
                            if content:
                                collected_data.append({
                                    'url': url_info['url'],
                                    'content': content,
                                    'type': 'documentation',
                                    'metadata': {
                                        'lastmod': url_info.get('lastmod'),
                                        'priority': url_info.get('priority'),
                                        'source': 'sitemap'
                                    }
                                })

        except Exception as e:
            logger.error(f"Error collecting from sitemap: {e}")

        finally:
            if session and self.config.get('close_session', True):
                await session.close()

        return collected_data

    def _parse_sitemap(self, xml_content: str) -> List[Dict[str, str]]:
        """Parse sitemap XML and extract URLs"""
        urls = []
        try:
            root = ET.fromstring(xml_content)

            # Handle different sitemap namespaces
            namespaces = {
                '': 'http://www.sitemaps.org/schemas/sitemap/0.9',
                'xhtml': 'http://www.w3.org/1999/xhtml'
            }

            # Find all URL entries
            for url in root.findall('.//url', namespaces):
                loc = url.find('loc', namespaces)
                if loc is not None and loc.text:
                    url_info = {'url': loc.text}

                    # Add optional metadata
                    lastmod = url.find('lastmod', namespaces)
                    if lastmod is not None:
                        url_info['lastmod'] = lastmod.text

                    priority = url.find('priority', namespaces)
                    if priority is not None:
                        url_info['priority'] = priority.text

                    urls.append(url_info)

        except Exception as e:
            logger.error(f"Error parsing sitemap: {e}")

        return urls

    async def _collect_documentation_tree(self, base_url: str) -> List[Dict[str, Any]]:
        """
        Simplified documentation collection - just use professional collector directly
        for the base URL and let it handle the crawling.
        """
        max_pages = self.config.get('max_pages', 300)

        logger.info(f"Starting documentation collection from {base_url}")
        logger.info(f"Max pages: {max_pages}")

        # For Drupal.org, we know the structure - just collect key sections directly
        urls_to_collect = []

        # Base URL first
        urls_to_collect.append(base_url)

        # If it's a Drupal docs site, add known important sections
        if 'drupal.org/docs' in base_url:
            # Add main documentation sections
            base_sections = [
                '/introduction',
                '/requirements',
                '/installation',
                '/configuration',
                '/administration',
                '/development',
                '/theming',
                '/security',
                '/api',
                '/modules',
                '/themes',
                '/distributions'
            ]

            for section in base_sections:
                # Try both with and without trailing parts
                if base_url.endswith('/en'):
                    urls_to_collect.append(base_url + section)
                else:
                    urls_to_collect.append(base_url + section)

        # Limit to max_pages
        urls_to_collect = urls_to_collect[:max_pages]

        logger.info(f"Prepared {len(urls_to_collect)} URLs to collect")

        collected_data = []

        # Use professional collector if available
        if (self.scraper.use_professional and
            hasattr(self.scraper, 'professional_collector') and
            len(urls_to_collect) > 0):

            logger.info(f"Using professional collector for {len(urls_to_collect)} URLs")

            try:
                # Collect URLs using professional collector
                from .professional_collector import CollectedPage
                collected_pages = await self.scraper.professional_collector.collect_urls(urls_to_collect)

                logger.info(f"Professional collector returned {len(collected_pages)} pages")

                # Convert CollectedPage objects to dict format
                for page in collected_pages:
                    if isinstance(page, CollectedPage):
                        data = {
                            'url': page.url,
                            'content': page.content,
                            'type': 'documentation',
                            'metadata': {
                                'title': page.title,
                                'quality_score': page.quality_score,
                                'extraction_algorithm': page.extraction_algorithm,
                                'content_hash': page.content_hash,
                                'collected_at': page.collected_at,
                                'collection_time_ms': page.collection_time_ms
                            }
                        }
                    else:
                        # Already in dict format
                        data = page

                    collected_data.append(data)

                # Capture metrics from professional collector
                if hasattr(self.scraper.professional_collector, 'get_metrics'):
                    self.collection_metrics = self.scraper.professional_collector.get_metrics()

                logger.info(f"Processed {len(collected_data)} items for pipeline")

            except Exception as e:
                logger.error(f"Professional collector batch failed: {e}")
                import traceback
                traceback.print_exc()
                # Fallback to basic collection
                logger.info("Falling back to basic collection")
                for url in urls_to_collect[:10]:  # Just collect first 10 as fallback
                    try:
                        source = DataSource(type='url', location=url)
                        page_data = await self.scraper.collect(source)
                        if page_data:
                            collected_data.extend(page_data)
                        await asyncio.sleep(self.scraper.rate_limit)
                    except Exception as e2:
                        logger.warning(f"Failed to collect {url}: {e2}")

        else:
            # No professional collector - collect individually
            logger.info(f"No professional collector, collecting {len(urls_to_collect)} pages individually")
            for url in urls_to_collect[:10]:  # Just first 10 for testing
                try:
                    source = DataSource(type='url', location=url)
                    page_data = await self.scraper.collect(source)
                    if page_data:
                        collected_data.extend(page_data)
                    await asyncio.sleep(self.scraper.rate_limit)
                except Exception as e:
                    logger.warning(f"Failed to collect {url}: {e}")

        logger.info(f"Documentation tree collection complete: {len(collected_data)} items collected")
        return collected_data


class APIDocScraper(DataCollector):
    """
    Specialized scraper for API documentation.
    Handles API references, code examples, and change logs.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_patterns = self.config.get('api_patterns', {
            'functions': r'function\s+(\w+)',
            'classes': r'class\s+(\w+)',
            'methods': r'\.(\w+)\s*\(',
            'endpoints': r'(GET|POST|PUT|DELETE|PATCH)\s+([/\w\{\}]+)'
        })

    async def collect(self, source: DataSource) -> List[Dict[str, Any]]:
        """Collect API documentation"""
        if source.type != 'api_doc':
            source.type = 'url'  # Treat as regular URL

        # Use web scraper for initial collection
        scraper = WebScraper(self.config)
        raw_data = await scraper.collect(source)

        # Enhance with API-specific extraction
        enhanced_data = []
        for item in raw_data:
            enhanced = self._extract_api_elements(item)
            enhanced_data.append(enhanced)

        return enhanced_data

    def _extract_api_elements(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract API-specific elements from content"""
        content = data.get('content', '')

        api_elements = {
            'functions': [],
            'classes': [],
            'methods': [],
            'endpoints': [],
            'code_examples': []
        }

        # Extract functions
        for match in re.finditer(self.api_patterns['functions'], content):
            api_elements['functions'].append(match.group(1))

        # Extract classes
        for match in re.finditer(self.api_patterns['classes'], content):
            api_elements['classes'].append(match.group(1))

        # Extract API endpoints
        for match in re.finditer(self.api_patterns['endpoints'], content):
            api_elements['endpoints'].append({
                'method': match.group(1),
                'path': match.group(2)
            })

        # Extract code blocks
        code_pattern = r'```(\w*)\n(.*?)```'
        for match in re.finditer(code_pattern, content, re.DOTALL):
            api_elements['code_examples'].append({
                'language': match.group(1) or 'unknown',
                'code': match.group(2)
            })

        # Add API elements to metadata
        data['metadata'] = data.get('metadata', {})
        data['metadata']['api_elements'] = api_elements
        data['type'] = 'api_documentation'

        return data


class ChangeRecordCollector(DataCollector):
    """
    Specialized collector for version changes and migration guides.
    Critical for delta training strategies.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.version_patterns = self.config.get('version_patterns', {
            'semantic': r'(\d+)\.(\d+)\.(\d+)',
            'drupal': r'Drupal\s+(\d+)',
            'deprecated': r'deprecated|removed|obsolete',
            'new': r'new|added|introduced'
        })

    async def collect(self, source: DataSource) -> List[Dict[str, Any]]:
        """Collect change records and version-specific information"""
        scraper = WebScraper(self.config)
        raw_data = await scraper.collect(source)

        # Process for version information
        versioned_data = []
        for item in raw_data:
            versioned = self._extract_version_info(item)
            versioned_data.append(versioned)

        return versioned_data

    def _extract_version_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract version and change information"""
        content = data.get('content', '')

        version_info = {
            'versions_mentioned': [],
            'deprecated_items': [],
            'new_features': [],
            'migration_notes': []
        }

        # Find version numbers
        for match in re.finditer(self.version_patterns['semantic'], content):
            version = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
            version_info['versions_mentioned'].append(version)

        # Find deprecated items
        if re.search(self.version_patterns['deprecated'], content, re.IGNORECASE):
            # Extract the context around deprecated mentions
            for match in re.finditer(r'([^.]*' + self.version_patterns['deprecated'] + r'[^.]*\.)', content, re.IGNORECASE):
                version_info['deprecated_items'].append(match.group(1).strip())

        # Find new features
        if re.search(self.version_patterns['new'], content, re.IGNORECASE):
            for match in re.finditer(r'([^.]*' + self.version_patterns['new'] + r'[^.]*\.)', content, re.IGNORECASE):
                version_info['new_features'].append(match.group(1).strip())

        # Add version info to metadata
        data['metadata'] = data.get('metadata', {})
        data['metadata']['version_info'] = version_info
        data['type'] = 'change_record'

        # Mark high priority for training
        data['training_weight'] = 1.5  # Higher weight for change records

        return data