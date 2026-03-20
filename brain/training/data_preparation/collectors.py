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


class WebScraper(DataCollector):
    """
    Web scraper for collecting content from websites.
    Supports HTML to markdown conversion and intelligent content extraction.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.session = None
        self.rate_limit = self.config.get('rate_limit', 1.0)  # seconds between requests
        self.max_depth = self.config.get('max_depth', 3)
        self.allowed_domains = self.config.get('allowed_domains', [])
        self.blocked_domains = self.config.get('blocked_domains', [])
        self.user_agent = self.config.get('user_agent',
            'Mozilla/5.0 (Brain LLM Training Bot) AppleWebKit/537.36')

    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={'User-Agent': self.user_agent}
            )
        return self.session

    async def collect(self, source: DataSource) -> List[Dict[str, Any]]:
        """Collect data from a web source"""
        if source.type != 'url':
            raise ValueError(f"WebScraper expects 'url' source, got {source.type}")

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
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.scraper = WebScraper(config)
        self.sitemap_patterns = self.config.get('sitemap_patterns',
            ['sitemap.xml', 'sitemap_index.xml', 'llms.txt'])

    async def collect(self, source: DataSource) -> List[Dict[str, Any]]:
        """Collect documentation from a site"""
        if source.type == 'sitemap':
            return await self._collect_from_sitemap(source.location)
        elif source.type == 'documentation':
            return await self._collect_documentation_tree(source.location)
        else:
            # Fall back to regular scraping
            return await self.scraper.collect(source)

    async def _collect_from_sitemap(self, sitemap_url: str) -> List[Dict[str, Any]]:
        """Parse and collect from XML sitemap"""
        collected_data = []

        try:
            session = await self.scraper._get_session()
            async with session.get(sitemap_url) as response:
                if response.status == 200:
                    sitemap_xml = await response.text()
                    urls = self._parse_sitemap(sitemap_xml)

                    logger.info(f"Found {len(urls)} URLs in sitemap")

                    # Collect from each URL
                    for url_info in urls[:self.config.get('max_pages', 100)]:
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
        """Collect documentation following navigation hierarchy"""
        collected_data = []
        visited = set()
        queue = [(base_url, 0, None)]  # (url, depth, parent)

        while queue:
            url, depth, parent = queue.pop(0)

            if url in visited or depth > self.scraper.max_depth:
                continue

            visited.add(url)

            # Fetch page
            source = DataSource(type='url', location=url)
            page_data = await self.scraper.collect(source)

            if page_data:
                # Add hierarchy metadata
                for item in page_data:
                    item['metadata'] = item.get('metadata', {})
                    item['metadata'].update({
                        'depth': depth,
                        'parent': parent,
                        'hierarchy_level': depth
                    })
                    collected_data.append(item)

                # Extract child links
                if depth < self.scraper.max_depth:
                    links = self.scraper._extract_links(page_data[0]['content'], url)
                    for link in links:
                        if link not in visited:
                            queue.append((link, depth + 1, url))

            await asyncio.sleep(self.scraper.rate_limit)

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