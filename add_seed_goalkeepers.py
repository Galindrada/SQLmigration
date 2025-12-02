#!/usr/bin/env python3
"""
Add Seed Goalkeepers Script

This script assigns seed_player values to goalkeepers in the database
from elite goalkeepers in original.sqlite.

Only assigns seeds to:
- Goalkeepers with registered_position = 0
- That don't already have a seed_player value

Seeds come from original.sqlite goalkeepers with:
- registered_position = 0
- goal_keeping > 82
"""

import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from team_management import TeamManager, add_seed_goalkeepers

def main():
    """Main function to run the seed goalkeeper assignment"""
    print("="*80)
    print("🧤 ADD SEED GOALKEEPERS FROM ORIGINAL.SQLITE")
    print("="*80)
    print()
    print("This script will assign seed_player values to goalkeepers without seeds.")
    print("Seeds are selected from elite goalkeepers (goal_keeping > 82) in original.sqlite")
    print()
    
    manager = TeamManager()
    
    if not manager.connect():
        print("❌ Failed to connect to database")
        return 1
    
    try:
        add_seed_goalkeepers(manager)
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        manager.disconnect()

if __name__ == "__main__":
    sys.exit(main())

