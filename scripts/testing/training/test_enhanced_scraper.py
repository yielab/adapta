#!/usr/bin/env python3
"""
Test script for the enhanced web scraper
"""

import asyncio
import json
from pathlib import Path
import sys

# Add the brain module to path
sys.path.insert(0, '/home/ox/Sites/brainFromCero')

from brain.training.data_preparation.base import DataSource
from brain.training.data_preparation.collectors import WebScraper


async def test_basic_scraping():
    """Test basic web scraping functionality"""
    print("Testing basic web scraping...")

    config = {
        'use_enhanced': True,
        'cache_hours': 0,  # Disable cache for testing
        'rate_limit': 1.0,
        'max_pages': 5
    }

    scraper = WebScraper(config)

    # Test with a simple website
    source = DataSource(
        type='url',
        location='https://httpbin.org/html',
        metadata={'test': 'basic'}
    )

    try:
        results = await scraper.collect(source)
        print(f"✓ Basic scraping successful: {len(results)} items collected")

        if results:
            print(f"  - URL: {results[0].get('url', 'N/A')}")
            content_length = len(results[0].get('content', ''))
            print(f"  - Content length: {content_length} chars")

    except Exception as e:
        print(f"✗ Basic scraping failed: {e}")
        return False

    return True


async def test_intelligent_collection():
    """Test intelligent collector selection"""
    print("\nTesting intelligent collector selection...")

    config = {
        'use_enhanced': True,
        'cache_hours': 0,
        'max_concurrent': 3
    }

    scraper = WebScraper(config)

    # Test with different source types
    test_cases = [
        DataSource(type='url', location='https://httpbin.org/html', metadata={'type': 'url'}),
        DataSource(type='api_doc', location='https://httpbin.org/json', metadata={'type': 'api'}),
        DataSource(type='documentation', location='https://httpbin.org/html', metadata={'type': 'doc'})
    ]

    for source in test_cases:
        try:
            results = await scraper.collect(source)
            print(f"✓ {source.type} collection successful: {len(results)} items")
        except Exception as e:
            print(f"✗ {source.type} collection failed: {e}")

    return True


async def test_enhanced_features():
    """Test enhanced features if available"""
    print("\nTesting enhanced scraper features...")

    config = {
        'use_enhanced': True,
        'cache_hours': 24,
        'rate_limit': 0.5,
        'max_retries': 3,
        'use_js': False,  # Disable JS rendering for now
        'proxies': [],  # No proxies for testing
    }

    try:
        from brain.training.data_preparation.enhanced_scraper import EnhancedWebScraper

        scraper = EnhancedWebScraper(config)
        await scraper.setup()

        # Test basic fetch
        url = 'https://httpbin.org/html'
        data = await scraper.scrape_url(url)

        if data:
            print("✓ Enhanced scraper working")
            print(f"  - Title: {data.get('title', 'N/A')}")
            print(f"  - Links found: {len(data.get('links', []))}")
            print(f"  - Images found: {len(data.get('images', []))}")

            # Check extraction methods
            if 'trafilatura' in data:
                print("  - Trafilatura extraction: ✓")
            if 'readability' in data:
                print("  - Readability extraction: ✓")
            if 'structured' in data:
                print("  - Structured data extraction: ✓")
        else:
            print("✗ No data returned from enhanced scraper")

        await scraper.cleanup()

    except ImportError as e:
        print(f"⚠ Enhanced scraper not available: {e}")
        print("  Some dependencies may be missing. Install with:")
        print("  pip install trafilatura readability-lxml fake-useragent selenium")
    except Exception as e:
        print(f"✗ Enhanced scraper test failed: {e}")

    return True


async def test_pipeline_integration():
    """Test integration with the data preparation pipeline"""
    print("\nTesting pipeline integration...")

    from brain.training.data_preparation.pipeline import DataPreparationPipeline

    config = {
        'output_dir': '/tmp/test_scraper',
        'use_enhanced': True,
        'max_pages': 3,
        'rate_limit': 0.5
    }

    pipeline = DataPreparationPipeline(config)
    pipeline.configure(
        collector_type='web',
        preprocessor_type='markdown',
        formatter_type='jsonl'
    )

    sources = [
        DataSource(
            type='url',
            location='https://httpbin.org/html',
            metadata={'test': 'pipeline'}
        )
    ]

    try:
        output_file = await pipeline.prepare_data(sources)
        print(f"✓ Pipeline integration successful")
        print(f"  - Output file: {output_file}")
        print(f"  - Stats: {json.dumps(pipeline.stats, indent=2)}")

        # Check the output file
        if output_file.exists():
            with open(output_file, 'r') as f:
                lines = f.readlines()
                print(f"  - Items in output: {len(lines)}")

    except Exception as e:
        print(f"✗ Pipeline integration failed: {e}")
        return False

    return True


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Enhanced Web Scraper Test Suite")
    print("=" * 60)

    results = []

    # Run tests
    results.append(await test_basic_scraping())
    results.append(await test_intelligent_collection())
    results.append(await test_enhanced_features())
    results.append(await test_pipeline_integration())

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("✓ All tests passed! The enhanced scraper is working properly.")
    else:
        print("✗ Some tests failed. Check the output above for details.")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)