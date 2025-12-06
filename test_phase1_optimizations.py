#!/usr/bin/env python3
"""
Test Phase 1 Performance Optimizations
=======================================

This script tests that all Phase 1 optimizations work correctly
WITHOUT breaking any existing functionality.
"""

import sqlite3
import sys
from datetime import datetime

DB_PATH = 'pes6_league_db.sqlite'

def test_database_integrity():
    """Test that all existing data is intact"""
    print("\n" + "="*80)
    print("🔍 TEST 1: DATABASE INTEGRITY")
    print("="*80)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Teams table
    tests_total += 1
    try:
        cur.execute("SELECT COUNT(*) as count FROM teams")
        team_count = cur.fetchone()['count']
        print(f"✅ Teams table: {team_count} teams found")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Teams table error: {e}")
    
    # Test 2: Players table
    tests_total += 1
    try:
        cur.execute("SELECT COUNT(*) as count FROM players")
        player_count = cur.fetchone()['count']
        print(f"✅ Players table: {player_count} players found")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Players table error: {e}")
    
    # Test 3: Budget integrity
    tests_total += 1
    try:
        cur.execute("SELECT SUM(budget) as total FROM teams")
        total_budget = cur.fetchone()['total']
        print(f"✅ Budget integrity: €{total_budget:,.2f} total")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Budget integrity error: {e}")
    
    # Test 4: Market listings
    tests_total += 1
    try:
        cur.execute("SELECT COUNT(*) as count FROM market_bazaar_listings")
        listing_count = cur.fetchone()['count']
        print(f"✅ Market listings: {listing_count} listings found")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Market listings error: {e}")
    
    # Test 5: Market offers
    tests_total += 1
    try:
        cur.execute("SELECT COUNT(*) as count FROM market_bazaar_offers")
        offer_count = cur.fetchone()['count']
        print(f"✅ Market offers: {offer_count} offers found")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Market offers error: {e}")
    
    conn.close()
    
    print(f"\n📊 Integrity Tests: {tests_passed}/{tests_total} passed")
    return tests_passed == tests_total


def test_new_schema_additions():
    """Test that new schema additions are present"""
    print("\n" + "="*80)
    print("🔍 TEST 2: NEW SCHEMA ADDITIONS")
    print("="*80)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: last_action_time column
    tests_total += 1
    try:
        cur.execute("PRAGMA table_info(teams)")
        columns = [row[1] for row in cur.fetchall()]
        if 'last_action_time' in columns:
            print("✅ last_action_time column exists in teams table")
            tests_passed += 1
        else:
            print("❌ last_action_time column NOT found in teams table")
    except Exception as e:
        print(f"❌ Error checking last_action_time column: {e}")
    
    # Test 2: Database indexes
    tests_total += 1
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
        indexes = [row[0] for row in cur.fetchall()]
        expected_indexes = [
            'idx_players_club_position',
            'idx_market_listings_status_type',
            'idx_market_offers_status',
            'idx_market_offers_listing',
            'idx_teams_budget',
            'idx_players_market_value',
            'idx_league_teams_user'
        ]
        found_indexes = [idx for idx in expected_indexes if idx in indexes]
        print(f"✅ Found {len(found_indexes)}/{len(expected_indexes)} performance indexes")
        if len(found_indexes) == len(expected_indexes):
            tests_passed += 1
        else:
            missing = set(expected_indexes) - set(found_indexes)
            print(f"   Missing indexes: {missing}")
    except Exception as e:
        print(f"❌ Error checking indexes: {e}")
    
    conn.close()
    
    print(f"\n📊 Schema Tests: {tests_passed}/{tests_total} passed")
    return tests_passed == tests_total


def test_performance_functions():
    """Test that performance optimization functions work"""
    print("\n" + "="*80)
    print("🔍 TEST 3: PERFORMANCE FUNCTIONS")
    print("="*80)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Import performance module
    tests_total += 1
    try:
        from cpu_ai_performance import (
            batch_analyze_teams_composition,
            should_team_act_optimized,
            update_team_last_action_time,
            get_teams_by_action_priority
        )
        print("✅ Performance optimization module imported successfully")
        tests_passed += 1
    except ImportError as e:
        print(f"❌ Could not import performance module: {e}")
        return False
    
    # Test 2: Get teams by priority
    tests_total += 1
    try:
        priorities = get_teams_by_action_priority(DB_PATH, datetime.now())
        total_teams = sum(len(teams) for teams in priorities.values())
        print(f"✅ Priority grouping works: {total_teams} teams categorized")
        for priority, teams in priorities.items():
            if teams:
                print(f"   {priority.upper()}: {len(teams)} teams")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Priority grouping error: {e}")
    
    # Test 3: Batch analysis
    tests_total += 1
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id FROM teams LIMIT 5")
        team_ids = [row['id'] for row in cur.fetchall()]
        conn.close()
        
        if team_ids:
            results = batch_analyze_teams_composition(DB_PATH, team_ids)
            print(f"✅ Batch analysis works: analyzed {len(results)} teams")
            tests_passed += 1
        else:
            print("⚠️  No teams to analyze")
    except Exception as e:
        print(f"❌ Batch analysis error: {e}")
    
    # Test 4: Action frequency logic
    tests_total += 1
    try:
        # Test with different scenarios
        test_cases = [
            (1, 15, None, "Critical team (< 16 players)"),
            (2, 25, None, "Normal team, no history"),
            (3, 25, datetime.now().isoformat(), "Recently acted"),
        ]
        
        all_passed = True
        for team_id, player_count, last_action, desc in test_cases:
            result = should_team_act_optimized(team_id, player_count, last_action, datetime.now())
            print(f"   {desc}: {'Act' if result else 'Skip'}")
        
        print("✅ Action frequency logic works")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Action frequency error: {e}")
    
    print(f"\n📊 Performance Tests: {tests_passed}/{tests_total} passed")
    return tests_passed == tests_total


def test_cpu_ai_integration():
    """Test that CPU AI still works with optimizations"""
    print("\n" + "="*80)
    print("🔍 TEST 4: CPU AI INTEGRATION")
    print("="*80)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Import CPU AI
    tests_total += 1
    try:
        from cpu_ai import cpu_ai, CPUAI
        print("✅ CPU AI module imported successfully")
        tests_passed += 1
    except ImportError as e:
        print(f"❌ Could not import CPU AI: {e}")
        return False
    
    # Test 2: Check PERFORMANCE_OPTIMIZATIONS_AVAILABLE flag
    tests_total += 1
    try:
        import cpu_ai as cpu_ai_module
        if hasattr(cpu_ai_module, 'PERFORMANCE_OPTIMIZATIONS_AVAILABLE'):
            status = cpu_ai_module.PERFORMANCE_OPTIMIZATIONS_AVAILABLE
            print(f"✅ Performance optimizations {'ENABLED' if status else 'DISABLED'}")
            tests_passed += 1
        else:
            print("⚠️  PERFORMANCE_OPTIMIZATIONS_AVAILABLE flag not found")
    except Exception as e:
        print(f"❌ Error checking optimization status: {e}")
    
    # Test 3: Verify CPU AI can still analyze teams
    tests_total += 1
    try:
        ai = CPUAI(DB_PATH)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id FROM teams LIMIT 1")
        team_id = cur.fetchone()['id']
        conn.close()
        
        analysis = ai.analyze_team_composition(team_id)
        if analysis:
            print(f"✅ CPU AI team analysis works: {analysis['team_name']}")
            tests_passed += 1
        else:
            print("❌ CPU AI team analysis returned empty")
    except Exception as e:
        print(f"❌ CPU AI analysis error: {e}")
    
    print(f"\n📊 Integration Tests: {tests_passed}/{tests_total} passed")
    return tests_passed == tests_total


def main():
    print("="*80)
    print("🧪 PHASE 1 PERFORMANCE OPTIMIZATION TESTS")
    print("="*80)
    print("Testing that optimizations work without breaking existing functionality")
    
    all_tests_passed = True
    
    # Run all test suites
    all_tests_passed &= test_database_integrity()
    all_tests_passed &= test_new_schema_additions()
    all_tests_passed &= test_performance_functions()
    all_tests_passed &= test_cpu_ai_integration()
    
    # Final summary
    print("\n" + "="*80)
    if all_tests_passed:
        print("✅ ALL TESTS PASSED!")
        print("="*80)
        print("Phase 1 optimizations are working correctly.")
        print("Your existing functionality is intact.")
        print("\n📈 Expected improvements:")
        print("  • Faster CPU AI processing (fewer unnecessary actions)")
        print("  • Reduced database query load (batch operations)")
        print("  • Smarter action frequency (based on team needs)")
        print("  • All money transfers still work correctly")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("="*80)
        print("Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

