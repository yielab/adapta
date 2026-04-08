#!/usr/bin/env python3
"""Test script to verify SimpleDrupalCollector returns 50+ examples"""

import asyncio
import sys
sys.path.append('/app')

from brain.training.data_preparation.simple_drupal_collector import SimpleDrupalCollector

async def test_drupal_collection():
    """Test that the SimpleDrupalCollector returns at least 50 examples"""

    print("Testing SimpleDrupalCollector...")
    print("-" * 50)

    collector = SimpleDrupalCollector()

    try:
        # Collect Drupal data
        examples = await collector.collect_drupal_data(target_version="11")

        print(f"✅ Collection completed successfully!")
        print(f"📊 Total examples collected: {len(examples)}")

        # Validate minimum requirement
        if len(examples) >= 50:
            print(f"✅ PASSED: Got {len(examples)} examples (minimum: 50)")
        else:
            print(f"❌ FAILED: Got {len(examples)} examples (minimum: 50)")
            return False

        # Show statistics
        total_tokens = sum(len(ex.get('content', '').split()) for ex in examples)
        api_examples = len([ex for ex in examples if ex.get('source') == 'api.drupal.org'])
        static_examples = len([ex for ex in examples if ex.get('source') == 'static'])

        print(f"\n📊 Statistics:")
        print(f"   - Total tokens: ~{total_tokens}")
        print(f"   - API examples: {api_examples}")
        print(f"   - Static examples: {static_examples}")

        # Show first few examples
        print(f"\n📝 First 3 examples:")
        for i, example in enumerate(examples[:3], 1):
            print(f"\n   Example {i}:")
            print(f"   - URL: {example.get('url', 'N/A')}")
            print(f"   - Title: {example.get('title', 'N/A')}")
            print(f"   - Source: {example.get('source', 'N/A')}")
            print(f"   - Content length: {len(example.get('content', ''))} chars")

        return True

    except Exception as e:
        print(f"❌ Error during collection: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_drupal_collection())
    sys.exit(0 if success else 1)