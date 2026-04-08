#!/usr/bin/env python3
"""
Direct test of Drupal collection - bypassing all the complex abstractions
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
from pathlib import Path

async def fetch_page(session, url):
    """Simple page fetcher"""
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                text = await response.text()
                soup = BeautifulSoup(text, 'html.parser')

                # Remove scripts and styles
                for script in soup(["script", "style"]):
                    script.decompose()

                # Get text
                content = soup.get_text(separator='\n', strip=True)

                # Get title
                title = soup.find('title')
                title_text = title.string if title else url

                return {
                    'url': url,
                    'title': title_text,
                    'content': content[:5000],  # First 5000 chars
                    'length': len(content)
                }
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
    return None

async def test_drupal_collection():
    """Test collecting Drupal documentation"""

    # Key Drupal documentation URLs that should work
    urls = [
        "https://www.drupal.org/docs",
        "https://www.drupal.org/docs/getting-started",
        "https://www.drupal.org/docs/user_guide/en/index.html",
        "https://www.drupal.org/docs/develop",
        "https://www.drupal.org/docs/theming-drupal",
        "https://www.drupal.org/docs/creating-modules",
        "https://www.drupal.org/docs/drupal-apis",
        "https://www.drupal.org/docs/configuration-management",
        "https://api.drupal.org/api/drupal",
        "https://www.drupal.org/docs/understanding-drupal"
    ]

    print("Testing Drupal documentation collection...")
    print(f"Will try to collect {len(urls)} pages\n")

    collected_pages = []

    async with aiohttp.ClientSession(
        headers={'User-Agent': 'Mozilla/5.0 (Training Bot) Chrome/91.0'}
    ) as session:
        for url in urls:
            print(f"Fetching: {url}")
            page = await fetch_page(session, url)
            if page:
                print(f"  ✓ Got {page['length']} chars from: {page['title']}")
                collected_pages.append(page)
            else:
                print(f"  ✗ Failed to fetch")

            await asyncio.sleep(1)  # Rate limiting

    print(f"\n=== RESULTS ===")
    print(f"Successfully collected: {len(collected_pages)}/{len(urls)} pages")
    print(f"Total content: {sum(p['length'] for p in collected_pages)} characters")

    if collected_pages:
        # Save a sample
        output_file = Path("/tmp/drupal_test_collection.json")
        with open(output_file, 'w') as f:
            json.dump(collected_pages, f, indent=2)
        print(f"Saved to: {output_file}")

        # Show sample content
        print("\nSample content from first page:")
        print("-" * 50)
        print(collected_pages[0]['content'][:500])
        print("-" * 50)

    return collected_pages

if __name__ == "__main__":
    result = asyncio.run(test_drupal_collection())
    print(f"\nFinal result: {len(result)} pages collected")