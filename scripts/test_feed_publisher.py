#!/usr/bin/env python3
"""
Test Feed Publisher Agent
=========================

Runs the feed publisher agent with sample data to demonstrate functionality.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from langgraph_agents import FeedPublisherGraph


async def run_feed_publisher_test():
    """Run feed publisher with test data."""

    print("\n" + "="*70)
    print("🚀 FEED PUBLISHER AGENT TEST")
    print("="*70 + "\n")

    # Initialize graph
    print("1️⃣  Initializing Feed Publisher Graph...")
    graph = FeedPublisherGraph()
    await graph.initialize()
    print("✅ Graph initialized\n")

    # Test Case 1: Dutch caption for Pomandi (Instagram)
    print("="*70)
    print("TEST CASE 1: Pomandi Instagram Post")
    print("="*70 + "\n")

    print("📝 Input:")
    print(f"  Brand: pomandi")
    print(f"  Platform: instagram")
    print(f"  Photo: products/pomandi/blazer-navy-001.jpg\n")

    print("⏳ Running agent...\n")

    start_time = datetime.now()
    result1 = await graph.publish(
        brand="pomandi",
        platform="instagram",
        photo_s3_key="products/pomandi/blazer-navy-001.jpg"
    )
    duration1 = (datetime.now() - start_time).total_seconds()

    print("📊 RESULTS:")
    print(f"  ⏱️  Duration: {duration1:.2f}s")
    print(f"  📝 Caption: {result1['caption']}")
    print(f"  ⭐ Quality Score: {result1['quality_score']:.1%}")
    print(f"  ✅ Published: {'Yes' if result1['published'] else 'No'}")
    print(f"  👤 Requires Approval: {'Yes' if result1['requires_approval'] else 'No'}")
    print(f"  🔄 Duplicate Detected: {'Yes' if result1['duplicate_detected'] else 'No'}")

    if result1['warnings']:
        print(f"\n  ⚠️  Warnings ({len(result1['warnings'])}):")
        for warning in result1['warnings']:
            print(f"     - {warning}")

    print(f"\n  📋 Steps Completed: {', '.join(result1['steps_completed'])}")

    # Test Case 2: French caption for Costume (Facebook)
    print("\n" + "="*70)
    print("TEST CASE 2: Costume Facebook Post")
    print("="*70 + "\n")

    print("📝 Input:")
    print(f"  Brand: costume")
    print(f"  Platform: facebook")
    print(f"  Photo: products/costume/suit-charcoal-001.jpg\n")

    print("⏳ Running agent...\n")

    start_time = datetime.now()
    result2 = await graph.publish(
        brand="costume",
        platform="facebook",
        photo_s3_key="products/costume/suit-charcoal-001.jpg"
    )
    duration2 = (datetime.now() - start_time).total_seconds()

    print("📊 RESULTS:")
    print(f"  ⏱️  Duration: {duration2:.2f}s")
    print(f"  📝 Caption: {result2['caption']}")
    print(f"  ⭐ Quality Score: {result2['quality_score']:.1%}")
    print(f"  ✅ Published: {'Yes' if result2['published'] else 'No'}")
    print(f"  👤 Requires Approval: {'Yes' if result2['requires_approval'] else 'No'}")
    print(f"  🔄 Duplicate Detected: {'Yes' if result2['duplicate_detected'] else 'No'}")

    if result2['warnings']:
        print(f"\n  ⚠️  Warnings ({len(result2['warnings'])}):")
        for warning in result2['warnings']:
            print(f"     - {warning}")

    print(f"\n  📋 Steps Completed: {', '.join(result2['steps_completed'])}")

    # Summary
    print("\n" + "="*70)
    print("📈 SUMMARY")
    print("="*70 + "\n")

    print("Test Results:")
    print(f"  ✅ Test Case 1 (Pomandi): {result1['quality_score']:.1%} quality")
    print(f"  ✅ Test Case 2 (Costume): {result2['quality_score']:.1%} quality")
    print(f"\nAverage Quality: {(result1['quality_score'] + result2['quality_score']) / 2:.1%}")
    print(f"Average Duration: {(duration1 + duration2) / 2:.2f}s")

    print("\n✨ Feed Publisher Agent Test Complete!\n")

    # Cleanup
    await graph.close()


if __name__ == "__main__":
    try:
        asyncio.run(run_feed_publisher_test())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
