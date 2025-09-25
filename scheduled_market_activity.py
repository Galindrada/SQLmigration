#!/usr/bin/env python3
"""
Scheduled Market Activity Script
This script can be run via cron to trigger market activity at regular intervals.
"""

import sys
import os
import sqlite3
from datetime import datetime

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def trigger_scheduled_market_activity():
    """Trigger scheduled market activity"""
    try:
        # Import required modules
        from cpu_ai import cpu_ai
        from app import check_expired_offers, post_transfer_news
        
        print(f"🔄 Starting scheduled market activity at {datetime.now()}")
        
        # Trigger CPU AI activity
        cpu_result = cpu_ai.process_cpu_ai_actions()
        print(f"🤖 CPU AI activity: {cpu_result.get('actions_taken', 0)} actions taken")
        
        # Process expired offers
        check_expired_offers()
        print("⏰ Expired offers processed")
        
        # Create a blog post about the market activity
        blog_title = f"🔄 Scheduled Market Activity Complete"
        
        blog_content = f"""
        <p><strong>📊 Automated Market Activity</strong></p>
        <p>The league has completed scheduled market activity processing.</p>
        <ul>
        <li><strong>🤖 CPU AI Activity:</strong> {cpu_result.get('actions_taken', 0)} actions taken</li>
        <li><strong>⏰ Expired Offers:</strong> Processed and cleaned up</li>
        <li><strong>🔄 Market Updates:</strong> All pending transactions processed</li>
        </ul>
        <p><strong>✅ Market activity processing completed successfully!</strong></p>
        """
        
        post_transfer_news(blog_title, blog_content, user_id=1)
        print("📝 Blog post created")
        
        print(f"✅ Scheduled market activity completed successfully at {datetime.now()}")
        return True
        
    except Exception as e:
        print(f"❌ Error during scheduled market activity: {e}")
        return False

if __name__ == "__main__":
    success = trigger_scheduled_market_activity()
    sys.exit(0 if success else 1)
