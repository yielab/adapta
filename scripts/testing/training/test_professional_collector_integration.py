#!/usr/bin/env python3
"""
Test script for Professional Collector Integration
Tests the complete flow from API → Pipeline → Collector → Professional Collector
"""

import asyncio
import json
import sys
from pathlib import Path

# Add brain to path
sys.path.insert(0, str(Path(__file__).parent))

from brain.training.data_preparation.pipeline import DataPreparationPipeline
from brain.training.data_preparation.base import DataSource
from brain.training.data_preparation.domain_configs import (
    create_collector_config,
    validate_data_for_domain,
    get_domain_config
)


async def test_professional_collector_basic():
    """Test basic professional collector functionality"""
    print("\n" + "="*80)
    print("TEST 1: Basic Professional Collector Integration")
    print("="*80)

    try:
        # Create a simple test source
        sources = [
            DataSource(
                type='url',
                location='https://www.drupal.org/docs',
                metadata={'category': 'test'},
                version='11'
            )
        ]

        # Create pipeline with professional collector enabled
        config = {
            'use_professional': True,
            'debug_files': True,
            'debug_dir': '/tmp/test_collection_debug',
            'max_pages': 5,  # Small test
            'rate_limit': 0.5,
            'output_dir': '/tmp/test_training_data'
        }

        pipeline = DataPreparationPipeline(config)
        pipeline.configure(
            collector_type='web',
            preprocessor_type='markdown',
            formatter_type='jsonl'
        )

        print(f"✓ Pipeline configured")
        print(f"  Collector: {pipeline.collector.__class__.__name__}")
        print(f"  Professional enabled: {getattr(pipeline.collector, 'use_professional', False)}")

        # Test collection (just the collection phase, not full pipeline)
        print("\nStarting collection...")
        from brain.training.data_preparation.collectors import WebScraper

        collector = WebScraper(config)
        print(f"  Collector type: {collector.__class__.__name__}")
        print(f"  Professional collector available: {hasattr(collector, 'professional_collector')}")
        print(f"  Using professional: {getattr(collector, 'use_professional', False)}")

        # Collect from single source
        data = await collector.collect(sources[0])

        print(f"\n✓ Collection complete!")
        print(f"  Pages collected: {len(data)}")

        if data:
            first_page = data[0]
            print(f"\n  First page details:")
            print(f"    URL: {first_page.get('url', 'N/A')}")
            print(f"    Content length: {len(first_page.get('content', ''))} chars")
            print(f"    Type: {first_page.get('type', 'N/A')}")

            # Check for professional collector metadata
            metadata = first_page.get('metadata', {})
            if 'quality_score' in metadata:
                print(f"\n  ✓ Professional collector metadata found!")
                print(f"    Quality score: {metadata.get('quality_score', 'N/A')}")
                print(f"    Extraction algorithm: {metadata.get('extraction_algorithm', 'N/A')}")
                print(f"    Collection time: {metadata.get('collection_time_ms', 'N/A')}ms")

        # Check for collection metrics
        metrics = collector.get_collection_metrics()
        if metrics:
            print(f"\n  ✓ Collection metrics available!")
            print(f"    Total requested: {metrics.get('total_requested', 0)}")
            print(f"    Successful: {metrics.get('successful', 0)}")
            print(f"    Failed: {metrics.get('failed', 0)}")
            print(f"    Avg quality score: {metrics.get('avg_quality_score', 0):.3f}")
            print(f"    Avg collection time: {metrics.get('avg_collection_time_ms', 0):.0f}ms")
            print(f"    Total tokens: {metrics.get('total_tokens', 0)}")

        return True

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_domain_configs():
    """Test domain configuration system"""
    print("\n" + "="*80)
    print("TEST 2: Domain Configuration System")
    print("="*80)

    try:
        # Test Drupal config
        drupal_config = get_domain_config('drupal')
        print(f"\n✓ Drupal Config:")
        print(f"  Min examples: {drupal_config.min_examples}")
        print(f"  Min tokens: {drupal_config.min_tokens}")
        print(f"  Quality threshold: {drupal_config.quality_threshold}")
        print(f"  Required keywords: {drupal_config.required_keywords[:5]}...")
        print(f"  Max pages: {drupal_config.max_pages}")

        # Test React config
        react_config = get_domain_config('react')
        print(f"\n✓ React Config:")
        print(f"  Min examples: {react_config.min_examples}")
        print(f"  Min tokens: {react_config.min_tokens}")
        print(f"  Quality threshold: {react_config.quality_threshold}")

        # Test Rust config
        rust_config = get_domain_config('rust')
        print(f"\n✓ Rust Config:")
        print(f"  Min examples: {rust_config.min_examples}")
        print(f"  Min tokens: {rust_config.min_tokens}")
        print(f"  Quality threshold: {rust_config.quality_threshold}")

        # Test validation
        print(f"\n✓ Testing validation:")

        # Should pass
        is_valid, msg = validate_data_for_domain('drupal', 60, 6000)
        print(f"  Drupal (60 examples, 6000 tokens): {'PASS' if is_valid else 'FAIL'}")

        # Should fail
        is_valid, msg = validate_data_for_domain('drupal', 10, 1000)
        print(f"  Drupal (10 examples, 1000 tokens): {'PASS' if is_valid else 'FAIL'}")
        if not is_valid:
            print(f"    Error: {msg}")

        # Test config creation
        collector_config = create_collector_config('drupal', max_pages=500)
        print(f"\n✓ Created collector config:")
        print(f"  Max pages: {collector_config.get('max_pages')}")
        print(f"  Quality threshold: {collector_config.get('quality_threshold')}")

        return True

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_imports():
    """Test that all necessary modules can be imported"""
    print("\n" + "="*80)
    print("TEST 3: Import Validation")
    print("="*80)

    try:
        print("\n✓ Checking imports...")

        # Test professional collector import
        from brain.training.data_preparation.professional_collector import (
            ProfessionalWebCollector,
            ContentExtractor,
            ContentValidator,
            CollectedPage,
            CollectionMetrics
        )
        print("  ✓ ProfessionalWebCollector imported")

        # Test domain configs import
        from brain.training.data_preparation.domain_configs import (
            DOMAIN_CONFIGS,
            get_domain_config,
            create_collector_config,
            validate_data_for_domain
        )
        print("  ✓ Domain configs imported")

        # Test collectors import
        from brain.training.data_preparation.collectors import (
            WebScraper,
            DocumentationCrawler,
            PROFESSIONAL_COLLECTOR_AVAILABLE
        )
        print("  ✓ Collectors imported")
        print(f"  ✓ Professional collector available: {PROFESSIONAL_COLLECTOR_AVAILABLE}")

        return True

    except Exception as e:
        print(f"\n✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_integration():
    """Test that API endpoints are properly configured"""
    print("\n" + "="*80)
    print("TEST 4: API Integration Check")
    print("="*80)

    try:
        import httpx

        # Check API health
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health")
            print(f"\n✓ API Health: {response.json()}")

            # Check if data preparation endpoints are available
            # Note: This will fail without auth, but we can check the error
            try:
                response = await client.get("http://localhost:8000/api/docs")
                print(f"  ✓ API docs accessible")
            except:
                pass

        return True

    except Exception as e:
        print(f"\n✗ API test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("PROFESSIONAL COLLECTOR INTEGRATION TEST SUITE")
    print("="*80)

    results = {
        'imports': await test_imports(),
        'domain_configs': await test_domain_configs(),
        'api_integration': await test_api_integration(),
        'professional_collector': await test_professional_collector_basic(),
    }

    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {test_name}: {status}")

    all_passed = all(results.values())

    if all_passed:
        print("\n✓ All tests passed! Integration is working correctly.")
        return 0
    else:
        print("\n✗ Some tests failed. Check output above for details.")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
