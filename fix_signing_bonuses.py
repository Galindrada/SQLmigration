#!/usr/bin/env python3
"""
Fix historical signing bonuses that were not properly deducted from user budgets.
This script recalculates all signing bonuses since 2025-11-18 18:37 and corrects
the balance_after values in user_movements and user_budgets tables.
"""

import sqlite3
from datetime import datetime

def fix_signing_bonuses(db_path='pes6_league_db.sqlite'):
    """Fix all signing bonuses since the specified date"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Date threshold: 2025-11-18 18:37
    threshold_date = '2025-11-18 18:37:00'
    
    print(f"🔍 Finding all signing bonus transactions since {threshold_date}...")
    
    # Get all signing bonus movements since the threshold date
    cursor.execute("""
        SELECT id, user_id, amount, balance_after, created_at, description
        FROM user_movements
        WHERE type = 'Signing Bonus'
        AND created_at >= ?
        ORDER BY user_id, created_at
    """, (threshold_date,))
    
    signing_bonuses = cursor.fetchall()
    
    if not signing_bonuses:
        print("✅ No signing bonuses found to fix.")
        conn.close()
        return
    
    print(f"📊 Found {len(signing_bonuses)} signing bonus transactions to fix")
    
    # Group by user to recalculate budgets sequentially
    user_bonuses = {}
    for bonus in signing_bonuses:
        user_id = bonus['user_id']
        if user_id not in user_bonuses:
            user_bonuses[user_id] = []
        user_bonuses[user_id].append(bonus)
    
    print(f"👥 Affected users: {len(user_bonuses)}")
    
    fixed_count = 0
    errors = []
    
    for user_id, bonuses in user_bonuses.items():
        try:
            # Special case for user 6: use hardcoded correct budget
            if user_id == 6:
                current_budget = 4754105
                # Find the EOS movement to get the reference date
                cursor.execute("""
                    SELECT created_at
                    FROM user_movements
                    WHERE user_id = ? 
                    AND type = 'End of Season Salary Bill'
                    AND created_at >= '2025-11-18 18:37:00'
                    AND created_at <= '2025-11-18 18:38:00'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_id,))
                eos_result = cursor.fetchone()
                if eos_result:
                    reference_date = eos_result['created_at']
                else:
                    reference_date = threshold_date
                print(f"  📅 User 6: Using hardcoded budget €{current_budget:,} before contract renewals")
            else:
                # First, try to find the End of Season Salary Bill around the threshold
                # This is the correct reference point after the end_of_season_process
                cursor.execute("""
                    SELECT balance_after, created_at
                    FROM user_movements
                    WHERE user_id = ? 
                    AND type = 'End of Season Salary Bill'
                    AND created_at >= '2025-11-18 18:37:00'
                    AND created_at <= '2025-11-18 18:38:00'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_id,))
                
                eos_movement = cursor.fetchone()
                reference_date = None
                
                if eos_movement:
                    # Use the End of Season Salary Bill as the correct reference point
                    current_budget = eos_movement['balance_after']
                    reference_date = eos_movement['created_at']
                    print(f"  📅 Using End of Season Salary Bill at {reference_date} as reference")
                else:
                    # Fallback: Use the last movement at or before the threshold
                    cursor.execute("""
                        SELECT balance_after 
                        FROM user_movements
                        WHERE user_id = ? AND created_at <= ?
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (user_id, threshold_date))
                    
                    last_movement = cursor.fetchone()
                    
                    if last_movement:
                        # Use the correct balance from the threshold as starting point
                        current_budget = last_movement['balance_after']
                        reference_date = threshold_date
                    else:
                        # No movements at all - use base budget
                        current_budget = 450000000
                        reference_date = threshold_date
            
            print(f"\n👤 User {user_id}: Starting budget = €{current_budget:,}")
            
            # Get ALL movements for this user AFTER the reference point (EOS or threshold)
            # We need to recalculate all of them in order to get correct balances
            
            cursor.execute("""
                SELECT id, amount, balance_after, created_at, type, description
                FROM user_movements
                WHERE user_id = ? AND created_at > ?
                ORDER BY created_at
            """, (user_id, reference_date))
            
            all_movements = cursor.fetchall()
            
            # Recalculate each movement in chronological order
            for movement in all_movements:
                movement_amount = movement['amount']
                expected_new_budget = current_budget + movement_amount
                
                # Only update if balance_after is incorrect
                if movement['balance_after'] != expected_new_budget:
                    # Update the balance_after in user_movements
                    cursor.execute("""
                        UPDATE user_movements
                        SET balance_after = ?
                        WHERE id = ?
                    """, (expected_new_budget, movement['id']))
                    
                    if movement['type'] == 'Signing Bonus':
                        fixed_count += 1
                        print(f"  ✅ Fixed {movement['type']} {movement['id']}: €{abs(movement_amount):,} -> Balance: €{expected_new_budget:,}")
                
                current_budget = expected_new_budget
            
            # Update user_budgets table with the final calculated budget
            cursor.execute("""
                INSERT OR REPLACE INTO user_budgets (user_id, budget, updated_at)
                VALUES (?, ?, datetime('now'))
            """, (user_id, current_budget))
            
            # Also update teams table for consistency
            cursor.execute("""
                UPDATE teams 
                SET budget = ?
                WHERE id = (
                    SELECT t.id FROM teams t
                    JOIN league_teams lt ON t.club_name = lt.team_name
                    WHERE lt.user_id = ?
                )
            """, (current_budget, user_id))
            
            print(f"  💰 Final budget for user {user_id}: €{current_budget:,}")
            
        except Exception as e:
            error_msg = f"Error fixing user {user_id}: {e}"
            errors.append(error_msg)
            print(f"  ❌ {error_msg}")
            conn.rollback()
            continue
    
    # Commit all changes
    if fixed_count > 0:
        conn.commit()
        print(f"\n✅ Successfully fixed {fixed_count} signing bonus transactions")
    else:
        print("\n⚠️  No transactions were fixed")
    
    if errors:
        print(f"\n❌ Errors encountered: {len(errors)}")
        for error in errors:
            print(f"   {error}")
    
    conn.close()

if __name__ == "__main__":
    print("🔧 Starting signing bonus fix script...")
    fix_signing_bonuses()
    print("\n✨ Script completed!")

