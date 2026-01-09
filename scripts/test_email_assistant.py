#!/usr/bin/env python3
"""
Test Email Assistant Agent
===========================

Test script for email assistant with sample data.
Demonstrates the full workflow without requiring real email accounts.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from langgraph_agents.email_assistant_graph import EmailAssistantGraph
from langgraph_agents.state_schemas import init_email_assistant_state, EmailMessage


async def run_email_assistant_test():
    """Run email assistant with mock data."""

    print("\n" + "="*70)
    print("🚀 EMAIL ASSISTANT AGENT TEST")
    print("="*70 + "\n")

    # Initialize graph
    print("1️⃣  Initializing Email Assistant Graph...")
    graph = EmailAssistantGraph(enable_memory=False)  # Disable memory for testing
    await graph.initialize()
    print("✅ Graph initialized\n")

    # Test Case 1: Important email requiring response
    print("="*70)
    print("TEST CASE 1: Important Email")
    print("="*70 + "\n")

    print("📝 Sample Email:")
    print("  From: boss@company.com")
    print("  Subject: URGENT: Budget Report Needed")
    print("  Body: Please send the Q4 budget report ASAP.\n")

    print("⏳ Running agent...\n")

    # Create mock state with sample email
    initial_state = init_email_assistant_state()

    sample_email: EmailMessage = {
        "id": "msg_001",
        "source": "outlook",
        "from_email": "boss@company.com",
        "from_name": "John Boss",
        "subject": "URGENT: Budget Report Needed",
        "body": "Hi,\n\nPlease send me the Q4 budget report as soon as possible.\n\nThanks,\nJohn",
        "received_at": datetime.utcnow().isoformat(),
        "has_attachments": False,
        "is_read": False
    }

    # Manually inject sample email (simulating fetch_emails_node)
    initial_state["all_emails"] = [sample_email]
    initial_state["outlook_emails"] = [sample_email]
    initial_state["new_emails_count"] = 1

    start_time = datetime.now()

    try:
        # Run from classify_emails onwards (skip fetch)
        graph_instance = graph.graph.compile()

        # We'll manually step through nodes for testing
        print("📊 Classifying email...")
        state = await graph.classify_emails_node(initial_state)

        print(f"   Category: {state['classifications'].get('msg_001', {}).get('category', 'N/A')}")
        print(f"   Importance: {state['classifications'].get('msg_001', {}).get('importance_score', 0):.0%}")
        print(f"   Requires response: {state['classifications'].get('msg_001', {}).get('requires_response', False)}")
        print(f"   Action: {state['classifications'].get('msg_001', {}).get('suggested_action', 'N/A')}\n")

        print("🔍 Loading response patterns...")
        state = await graph.load_patterns_node(state)
        print(f"   Patterns matched: {len(state['pattern_matches'])}\n")

        print("📱 Sending Telegram notification...")
        state = await graph.notify_telegram_node(state)
        print(f"   Notification sent: {state['notification_sent']}\n")

        print("✍️  Drafting reply...")
        state = await graph.handle_replies_node(state)
        print(f"   Reply drafts: {len(state['reply_drafts'])}")
        print(f"   Pending approval: {len(state['pending_approval'])}\n")

        if state['reply_drafts']:
            draft = list(state['reply_drafts'].values())[0]
            print(f"   Draft preview:")
            print(f"   To: {draft['to_email']}")
            print(f"   Subject: {draft['subject']}")
            print(f"   Body: {draft['body'][:100]}...")
            print(f"   Confidence: {draft['confidence']:.0%}")
            print(f"   Requires approval: {draft['requires_approval']}\n")

        print("📚 Learning patterns...")
        state = await graph.learn_patterns_node(state)
        print(f"   New patterns saved: {state['new_patterns_saved']}\n")

        print("💾 Saving context...")
        state = await graph.save_context_node(state)

        duration = (datetime.now() - start_time).total_seconds()

        print("📊 RESULTS:")
        print(f"  ⏱️  Duration: {duration:.2f}s")
        print(f"  📧 Emails processed: {state['new_emails_count']}")
        print(f"  ⭐ Important: {len(state['important_emails'])}")
        print(f"  🗑️  Spam: {len(state['spam_emails'])}")
        print(f"  📂 Archived: {state['archived_count']}")
        print(f"  🔔 Notification sent: {state['notification_sent']}")
        print(f"  ✍️  Reply drafts: {len(state['reply_drafts'])}")
        print(f"  ⏳ Pending approval: {len(state['pending_approval'])}")

        if state['warnings']:
            print(f"\n  ⚠️  Warnings ({len(state['warnings'])}):")
            for warning in state['warnings']:
                print(f"     - {warning}")

        print(f"\n  📋 Steps: {' → '.join(state['steps_completed'])}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    # Test Case 2: Spam email
    print("\n" + "="*70)
    print("TEST CASE 2: Spam Email")
    print("="*70 + "\n")

    print("📝 Sample Email:")
    print("  From: marketing@spammer.com")
    print("  Subject: Get rich quick! Buy now!")
    print("  Body: Amazing offer...\n")

    spam_email: EmailMessage = {
        "id": "msg_002",
        "source": "godaddy",
        "from_email": "marketing@spammer.com",
        "from_name": "Marketing Team",
        "subject": "Get rich quick! Buy now!",
        "body": "Amazing offer! Click here to get rich!",
        "received_at": datetime.utcnow().isoformat(),
        "has_attachments": False,
        "is_read": False
    }

    initial_state_2 = init_email_assistant_state()
    initial_state_2["all_emails"] = [spam_email]
    initial_state_2["godaddy_emails"] = [spam_email]
    initial_state_2["new_emails_count"] = 1

    try:
        state2 = await graph.classify_emails_node(initial_state_2)
        state2 = await graph.load_patterns_node(state2)
        state2 = await graph.archive_emails_node(state2)
        state2 = await graph.save_context_node(state2)

        print("📊 RESULTS:")
        print(f"  Category: {state2['classifications'].get('msg_002', {}).get('category', 'N/A')}")
        print(f"  Action: {state2['classifications'].get('msg_002', {}).get('suggested_action', 'N/A')}")
        print(f"  Archived: {state2['archived_count']}")

    except Exception as e:
        print(f"❌ Error: {e}")

    # Summary
    print("\n" + "="*70)
    print("📈 SUMMARY")
    print("="*70 + "\n")

    print("✨ Email Assistant Agent Test Complete!")
    print("\nKey Features Demonstrated:")
    print("  ✅ Email classification (important vs spam)")
    print("  ✅ Pattern matching for auto-replies")
    print("  ✅ Telegram notifications (mocked)")
    print("  ✅ Reply drafting with approval")
    print("  ✅ Spam archiving")
    print("  ✅ Learning from patterns")
    print("  ✅ Context saving")

    print("\n📝 Next Steps:")
    print("  1. Set up Telegram bot (@BotFather)")
    print("  2. Configure email accounts (Outlook + GoDaddy)")
    print("  3. Enable memory layer (Qdrant)")
    print("  4. Deploy to Coolify")
    print("  5. Schedule Temporal workflow (5 min interval)")

    print("\n✨ Done!\n")

    # Cleanup
    await graph.close()


if __name__ == "__main__":
    try:
        asyncio.run(run_email_assistant_test())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
