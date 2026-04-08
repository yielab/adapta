"""
Selenium-based collector for JavaScript-heavy websites.
Handles dynamic content loading, SPAs, and complex interactions.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from pathlib import Path

logger = logging.getLogger(__name__)

# Selenium imports are conditional
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not installed. JavaScript-heavy site collection will be limited.")


class SeleniumCollector:
    """
    Collector for JavaScript-heavy websites using Selenium WebDriver.

    Features:
    - Headless browser execution
    - Dynamic content waiting
    - Scroll-based lazy loading
    - Cookie and session handling
    - Screenshot capture for debugging
    - Configurable wait strategies
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize Selenium collector.

        Args:
            config: Configuration including browser settings, wait times, etc.
        """
        if not SELENIUM_AVAILABLE:
            raise ImportError(
                "Selenium is not installed. Install with: pip install selenium webdriver-manager"
            )

        self.config = config or {}
        self.driver = None
        self.wait_timeout = self.config.get("wait_timeout", 10)
        self.page_load_timeout = self.config.get("page_load_timeout", 30)
        self.implicit_wait = self.config.get("implicit_wait", 3)
        self.headless = self.config.get("headless", True)
        self.user_agent = self.config.get(
            "user_agent",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Domain-specific wait strategies
        self.domain_strategies = {
            "react": self._wait_for_react,
            "angular": self._wait_for_angular,
            "vue": self._wait_for_vue,
            "default": self._wait_for_default
        }

    def _create_driver(self):
        """Create and configure Chrome WebDriver."""
        options = Options()

        if self.headless:
            options.add_argument("--headless=new")  # New headless mode

        # Performance and stability options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"--user-agent={self.user_agent}")

        # Disable images for faster loading (optional)
        if self.config.get("disable_images", False):
            prefs = {"profile.managed_default_content_settings.images": 2}
            options.add_experimental_option("prefs", prefs)

        # Use webdriver-manager for automatic driver management
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        except ImportError:
            # Fallback to system chromedriver
            service = Service()

        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(self.page_load_timeout)
        self.driver.implicitly_wait(self.implicit_wait)

    async def collect_page(self, url: str, domain: str = None) -> Optional[Dict[str, Any]]:
        """
        Collect a page using Selenium.

        Args:
            url: URL to collect
            domain: Domain type for specific wait strategies

        Returns:
            Page data or None if failed
        """
        if not self.driver:
            self._create_driver()

        try:
            logger.info(f"Selenium collecting: {url}")
            start_time = time.time()

            # Navigate to page
            self.driver.get(url)

            # Apply domain-specific wait strategy
            wait_strategy = self.domain_strategies.get(
                domain, self.domain_strategies["default"]
            )
            await wait_strategy()

            # Handle lazy loading by scrolling
            if self.config.get("scroll_page", True):
                await self._scroll_page()

            # Wait for any final dynamic content
            await asyncio.sleep(1)

            # Extract content
            page_data = await self._extract_content()

            # Add metadata
            page_data.update({
                "url": url,
                "domain": domain,
                "collection_time": time.time() - start_time,
                "collector": "selenium",
                "page_height": self.driver.execute_script("return document.body.scrollHeight"),
                "viewport_width": self.driver.execute_script("return window.innerWidth"),
                "viewport_height": self.driver.execute_script("return window.innerHeight")
            })

            logger.info(f"Selenium collected {url} in {page_data['collection_time']:.2f}s")
            return page_data

        except TimeoutException:
            logger.warning(f"Timeout collecting {url} with Selenium")
            return None
        except WebDriverException as e:
            logger.error(f"WebDriver error collecting {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error collecting {url}: {e}")
            return None

    async def _extract_content(self) -> Dict[str, Any]:
        """Extract content from the loaded page."""
        # Get page title
        title = self.driver.title

        # Try multiple content extraction strategies
        content = ""

        # Strategy 1: Main content areas
        main_selectors = [
            "main", "article", "[role='main']",
            ".content", "#content", ".documentation",
            ".markdown-body", ".prose"
        ]

        for selector in main_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    content = "\n\n".join([elem.text for elem in elements if elem.text])
                    if content:
                        break
            except:
                continue

        # Strategy 2: If no main content, get body text
        if not content:
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                content = body.text
            except:
                content = ""

        # Extract code blocks separately
        code_blocks = []
        try:
            code_elements = self.driver.find_elements(By.CSS_SELECTOR, "pre, code")
            for elem in code_elements:
                code_text = elem.text
                if code_text and len(code_text) > 20:  # Skip tiny snippets
                    code_blocks.append(code_text)
        except:
            pass

        # Extract navigation structure (useful for documentation sites)
        nav_structure = await self._extract_navigation()

        # Extract metadata
        meta_description = ""
        try:
            meta_elem = self.driver.find_element(
                By.CSS_SELECTOR, "meta[name='description']"
            )
            meta_description = meta_elem.get_attribute("content")
        except:
            pass

        return {
            "title": title,
            "content": content,
            "code_blocks": code_blocks,
            "navigation": nav_structure,
            "meta_description": meta_description,
            "word_count": len(content.split()),
            "code_block_count": len(code_blocks)
        }

    async def _extract_navigation(self) -> List[Dict[str, str]]:
        """Extract navigation links from the page."""
        nav_items = []
        nav_selectors = ["nav", ".sidebar", ".toc", ".navigation", "[role='navigation']"]

        for selector in nav_selectors:
            try:
                nav_elements = self.driver.find_elements(By.CSS_SELECTOR, f"{selector} a")
                for elem in nav_elements[:50]:  # Limit to prevent huge lists
                    try:
                        nav_items.append({
                            "text": elem.text,
                            "href": elem.get_attribute("href")
                        })
                    except:
                        continue
                if nav_items:
                    break
            except:
                continue

        return nav_items

    async def _scroll_page(self):
        """Scroll the page to trigger lazy loading."""
        scroll_pause = 0.5
        last_height = self.driver.execute_script("return document.body.scrollHeight")

        while True:
            # Scroll down to bottom
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # Wait for new content to load
            await asyncio.sleep(scroll_pause)

            # Check if new content loaded
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

            # Limit scrolling to prevent infinite loops
            if last_height > 50000:  # Arbitrary limit
                break

    async def _wait_for_react(self):
        """Wait for React app to be ready."""
        wait = WebDriverWait(self.driver, self.wait_timeout)

        # Wait for React root
        try:
            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#root, #app, .app"))
            )
        except:
            pass

        # Check for React DevTools
        try:
            self.driver.execute_script(
                "return window.React || window.__REACT_DEVTOOLS_GLOBAL_HOOK__"
            )
            await asyncio.sleep(1)  # Give React time to render
        except:
            pass

    async def _wait_for_angular(self):
        """Wait for Angular app to be ready."""
        try:
            # Wait for Angular to be defined
            WebDriverWait(self.driver, self.wait_timeout).until(
                lambda driver: driver.execute_script("return window.getAllAngularTestabilities")
            )

            # Wait for Angular to be stable
            self.driver.execute_script("""
                var callback = arguments[arguments.length - 1];
                if (window.getAllAngularTestabilities) {
                    var testabilities = window.getAllAngularTestabilities();
                    var count = testabilities.length;
                    var decrement = function() {
                        count--;
                        if (count === 0) {
                            callback();
                        }
                    };
                    testabilities.forEach(function(testability) {
                        testability.whenStable(decrement);
                    });
                } else {
                    callback();
                }
            """)
        except:
            await asyncio.sleep(2)

    async def _wait_for_vue(self):
        """Wait for Vue app to be ready."""
        try:
            # Wait for Vue to be defined
            self.driver.execute_script("return window.Vue || window.__VUE__")
            await asyncio.sleep(1)  # Give Vue time to render
        except:
            pass

        # Wait for common Vue indicators
        try:
            wait = WebDriverWait(self.driver, self.wait_timeout)
            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[id='app'], .vue-app"))
            )
        except:
            pass

    async def _wait_for_default(self):
        """Default wait strategy."""
        # Wait for DOM to be ready
        WebDriverWait(self.driver, self.wait_timeout).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )

        # Wait for common content indicators
        content_indicators = [
            "main", "article", ".content", "#content",
            "[role='main']", ".documentation"
        ]

        for indicator in content_indicators:
            try:
                WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, indicator))
                )
                break
            except:
                continue

    async def collect_spa_routes(self, base_url: str, routes: List[str]) -> List[Dict[str, Any]]:
        """
        Collect multiple routes from a Single Page Application.

        Args:
            base_url: Base URL of the SPA
            routes: List of routes to collect

        Returns:
            List of collected page data
        """
        collected = []

        for route in routes:
            url = f"{base_url.rstrip('/')}/{route.lstrip('/')}"
            page_data = await self.collect_page(url, domain="spa")
            if page_data:
                collected.append(page_data)

            # Small delay between requests
            await asyncio.sleep(0.5)

        return collected

    def take_screenshot(self, filename: str = None):
        """Take a screenshot for debugging."""
        if not self.driver:
            return

        if not filename:
            timestamp = int(time.time())
            filename = f"screenshot_{timestamp}.png"

        try:
            self.driver.save_screenshot(filename)
            logger.info(f"Screenshot saved: {filename}")
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")

    def close(self):
        """Close the WebDriver."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.close()


class SmartSeleniumStrategy:
    """
    Smart strategies for determining when to use Selenium.
    """

    @staticmethod
    def needs_selenium(url: str, initial_content: str = None) -> bool:
        """
        Determine if a URL needs Selenium for proper collection.

        Args:
            url: URL to check
            initial_content: Initial content from basic collection (optional)

        Returns:
            True if Selenium should be used
        """
        # Always use Selenium for known SPA frameworks documentation
        spa_indicators = [
            "react.dev", "angular.io", "vuejs.org",
            "svelte.dev", "emberjs.com", "nextjs.org"
        ]

        domain = urlparse(url).netloc
        if any(indicator in domain for indicator in spa_indicators):
            return True

        # Check URL patterns that typically need JS
        js_patterns = [
            "/docs/", "/api/", "/reference/",
            "/#/", "#!", "/app/"
        ]

        if any(pattern in url for pattern in js_patterns):
            return True

        # If we have initial content, check for JS indicators
        if initial_content:
            # Very little content might mean JS-rendered
            if len(initial_content) < 500:
                return True

            # Check for loading indicators
            loading_indicators = [
                "loading...", "please wait", "javascript required",
                "enable javascript", "<noscript>", "app is loading"
            ]

            content_lower = initial_content.lower()
            if any(indicator in content_lower for indicator in loading_indicators):
                return True

        return False

    @staticmethod
    def get_wait_strategy(url: str) -> str:
        """
        Get the appropriate wait strategy for a URL.

        Args:
            url: URL to determine strategy for

        Returns:
            Strategy name (react, angular, vue, or default)
        """
        domain = urlparse(url).netloc.lower()
        path = urlparse(url).path.lower()

        # React sites
        if "react" in domain or "react" in path:
            return "react"

        # Angular sites
        if "angular" in domain or "angular" in path:
            return "angular"

        # Vue sites
        if "vue" in domain or "vue" in path:
            return "vue"

        return "default"