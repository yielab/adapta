#!/usr/bin/env python3
"""
Debug connection issues to Drupal.org
"""
import asyncio
import aiohttp
import ssl
import certifi

async def test_connection():
    """Test various connection methods"""

    test_urls = [
        "https://www.drupal.org/docs",
        "https://api.drupal.org/api/drupal",
        "https://www.drupal.org/",
        "https://httpbin.org/get",  # Control test
    ]

    # Try different SSL contexts
    ssl_configs = [
        ("Default SSL", None),
        ("Certifi SSL", ssl.create_default_context(cafile=certifi.where())),
        ("No SSL Verify", False),
    ]

    for ssl_name, ssl_context in ssl_configs:
        print(f"\n=== Testing with {ssl_name} ===")

        connector = aiohttp.TCPConnector(ssl=ssl_context) if ssl_context != False else aiohttp.TCPConnector(ssl=False)

        async with aiohttp.ClientSession(
            connector=connector,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        ) as session:

            for url in test_urls:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        content = await response.text()
                        print(f"  ✓ {url}: Status {response.status}, Length {len(content)}")
                except aiohttp.ClientSSLError as e:
                    print(f"  ✗ {url}: SSL Error - {e}")
                except aiohttp.ClientConnectorError as e:
                    print(f"  ✗ {url}: Connection Error - {e}")
                except asyncio.TimeoutError:
                    print(f"  ✗ {url}: Timeout")
                except Exception as e:
                    print(f"  ✗ {url}: {type(e).__name__} - {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())