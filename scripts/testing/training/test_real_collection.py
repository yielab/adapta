#!/usr/bin/env python3
"""
Test real-world collection with a permissive site
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from brain.training.data_preparation.collectors import WebScraper
from brain.training.data_preparation.base import DataSource
from brain.training.data_preparation.domain_configs import create_collector_config


async def test_real_collection():
    """Test with a real, permissive URL"""
    print("\n" + "="*80)
    print("REAL-WORLD COLLECTION TEST")
    print("="*80)

    # Use example.com (always allows bots)
    test_urls = [
        'https://example.com',
    ]

    # Create collector with Drupal domain config
    config = create_collector_config('drupal')
    config.update({
        'use_professional': True,
        'debug_files': True,
        'debug_dir': '/tmp/test_collection',
        'rate_limit': 1.0,
        'timeout': 30,
        'max_retries': 2
    })

    collector = WebScraper(config)

    print(f"\n✓ Collector configured")
    print(f"  Using professional: {collector.use_professional}")
    print(f"  Quality threshold: {config.get('quality_threshold')}")
    print(f"  Domain: drupal")

    # Test with each URL
    for url in test_urls:
        print(f"\n{'='*80}")
        print(f"Testing: {url}")
        print(f"{'='*80}")

        source = DataSource(
            type='url',
            location=url,
            metadata={'test': True}
        )

        try:
            data = await collector.collect(source)

            print(f"\n✓ Collection successful!")
            print(f"  Pages collected: {len(data)}")

            if data:
                page = data[0]
                print(f"\n  Page details:")
                print(f"    URL: {page.get('url')}")
                print(f"    Content length: {len(page.get('content', ''))} chars")
                print(f"    Content preview: {page.get('content', '')[:200]}...")

                metadata = page.get('metadata', {})
                if 'quality_score' in metadata:
                    print(f"\n  ✓ Professional collector used!")
                    print(f"    Quality score: {metadata.get('quality_score'):.3f}")
                    print(f"    Extraction algorithm: {metadata.get('extraction_algorithm')}")
                    print(f"    Collection time: {metadata.get('collection_time_ms')}ms")
                    print(f"    Content hash: {metadata.get('content_hash', '')[:16]}...")

            # Get collection metrics
            metrics = collector.get_collection_metrics()
            if metrics:
                print(f"\n  Collection Metrics:")
                print(f"    Total requested: {metrics.get('total_requested')}")
                print(f"    Successful: {metrics.get('successful')}")
                print(f"    Failed: {metrics.get('failed')}")
                print(f"    Success rate: {metrics.get('successful', 0) / max(metrics.get('total_requested', 1), 1) * 100:.1f}%")
                print(f"    Avg quality: {metrics.get('avg_quality_score', 0):.3f}")
                print(f"    Total tokens: {metrics.get('total_tokens')}")

        except Exception as e:
            print(f"\n✗ Collection failed: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*80}")
    print("TEST COMPLETE")
    print(f"{'='*80}")


if __name__ == '__main__':
    asyncio.run(test_real_collection())
