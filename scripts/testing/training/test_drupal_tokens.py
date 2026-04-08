#!/usr/bin/env python3
"""Test script to verify Drupal collection meets token requirements"""

import asyncio
import sys
sys.path.append('/app')

from brain.training.data_preparation.simple_drupal_collector import SimpleDrupalCollector

async def test_drupal_tokens():
    """Test that the SimpleDrupalCollector meets token requirements"""

    print("Testing Drupal Collection Token Requirements...")
    print("=" * 60)

    collector = SimpleDrupalCollector()

    try:
        # Collect Drupal data
        examples = await collector.collect_drupal_data(target_version="11")

        print(f"✅ Collection completed successfully!")
        print(f"📊 Total examples collected: {len(examples)}")

        # Calculate tokens (simple word-based approximation)
        # In reality, tokenizers split differently, but words is a reasonable approximation
        total_words = 0
        total_chars = 0
        for example in examples:
            content = example.get('content', '')
            words = content.split()
            total_words += len(words)
            total_chars += len(content)

        # Approximate tokens (usually 1 token ≈ 0.75 words for code)
        estimated_tokens = int(total_words * 1.3)  # Code tends to have more tokens than natural language

        print(f"\n📊 Token Statistics:")
        print(f"   - Total words: {total_words}")
        print(f"   - Total characters: {total_chars}")
        print(f"   - Estimated tokens: ~{estimated_tokens}")

        # Check requirements
        print(f"\n📋 Requirements Check:")
        print(f"   Examples: {len(examples)} {'✅ PASSED' if len(examples) >= 50 else '❌ FAILED'} (min: 50)")
        print(f"   Tokens: ~{estimated_tokens} {'✅ PASSED' if estimated_tokens >= 5000 else '❌ FAILED'} (min: 5000)")

        if len(examples) >= 50 and estimated_tokens >= 5000:
            print(f"\n✅ ALL REQUIREMENTS MET!")
            return True
        else:
            print(f"\n❌ REQUIREMENTS NOT MET")
            if len(examples) < 50:
                print(f"   Need {50 - len(examples)} more examples")
            if estimated_tokens < 5000:
                print(f"   Need ~{5000 - estimated_tokens} more tokens")
            return False

    except Exception as e:
        print(f"❌ Error during collection: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_drupal_tokens())
    sys.exit(0 if success else 1)