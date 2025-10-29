#!/usr/bin/env python3
"""
Simulate CPU AI market activity to balance teams and fill critical positions
"""

import sqlite3
from cpu_ai import CPUAI
from app import check_expired_offers
from collections import defaultdict

def get_team_composition_stats():
    """Get current team composition statistics"""
    conn = sqlite3.connect('pes6_league_db.sqlite')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get all CPU teams
    cur.execute("""
        SELECT t.id, t.club_name
        FROM teams t
        WHERE t.id != 141
        AND t.id IN (
            SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = 1
        )
    """)
    
    cpu_teams = cur.fetchall()
    stats = {
        'teams_without_gk': [],
        'teams_missing_positions': [],
        'teams_over_capacity': [],
        'total_teams': len(cpu_teams),
        'position_gaps': defaultdict(int)
    }
    
    cpu_ai = CPUAI()
    
    # Ideal composition thresholds
    IDEAL_GK = 2
    IDEAL_DEF = 4  # Positions 2, 3
    IDEAL_FB = 4   # Positions 4, 6
    IDEAL_MID = 6  # Positions 5, 7, 9
    IDEAL_WING = 4 # Positions 8, 10
    IDEAL_FWD = 4  # Positions 11, 12
    
    for team in cpu_teams:
        team_id = team['id']
        team_name = team['club_name']
        
        # Get actual position counts directly from database
        cur.execute("""
            SELECT registered_position, COUNT(*) as count
            FROM players
            WHERE club_id = ?
            GROUP BY registered_position
        """, (team_id,))
        
        position_counts = {row['registered_position']: row['count'] for row in cur.fetchall()}
        total_players = sum(position_counts.values())
        
        # Check for over-capacity
        if total_players > 32:
            stats['teams_over_capacity'].append({
                'team_id': team_id,
                'team_name': team_name,
                'total_players': total_players
            })
        
        # Count by position groups
        gk_count = position_counts.get('0', 0)
        def_count = position_counts.get('2', 0) + position_counts.get('3', 0)
        fb_count = position_counts.get('4', 0) + position_counts.get('6', 0)
        mid_count = position_counts.get('5', 0) + position_counts.get('7', 0) + position_counts.get('9', 0)
        wing_count = position_counts.get('8', 0) + position_counts.get('10', 0)
        fwd_count = position_counts.get('11', 0) + position_counts.get('12', 0)
        
        missing_positions = []
        
        # Check goalkeepers
        if gk_count == 0:
            stats['teams_without_gk'].append((team_id, team_name))
            stats['position_gaps']['GK'] += 1
            missing_positions.append('GK')
        
        # Check other positions
        if def_count < IDEAL_DEF:
            missing_positions.append('DEF')
            stats['position_gaps']['DEF'] += 1
        if fb_count < IDEAL_FB:
            missing_positions.append('FB')
            stats['position_gaps']['FB'] += 1
        if mid_count < IDEAL_MID:
            missing_positions.append('MID')
            stats['position_gaps']['MID'] += 1
        if wing_count < IDEAL_WING:
            missing_positions.append('WING')
            stats['position_gaps']['WING'] += 1
        if fwd_count < IDEAL_FWD:
            missing_positions.append('FWD')
            stats['position_gaps']['FWD'] += 1
        
        if missing_positions:
            stats['teams_missing_positions'].append({
                'team_id': team_id,
                'team_name': team_name,
                'missing': missing_positions,
                'total_players': total_players
            })
    
    conn.close()
    return stats

def print_stats(stats, iteration=None):
    """Print team composition statistics"""
    if iteration is not None:
        print(f"\n{'='*60}")
        print(f"ITERATION {iteration}")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")
        print("FINAL STATISTICS")
        print(f"{'='*60}")
    
    print(f"\n📊 Total CPU Teams: {stats['total_teams']}")
    print(f"🚫 Teams without Goalkeepers: {len(stats['teams_without_gk'])}")
    
    if stats['teams_without_gk']:
        print("\n   Teams missing GK:")
        for team_id, team_name in stats['teams_without_gk'][:10]:  # Show first 10
            print(f"   - {team_name} (ID: {team_id})")
        if len(stats['teams_without_gk']) > 10:
            print(f"   ... and {len(stats['teams_without_gk']) - 10} more")
    
    print(f"\n🔍 Position Gaps Detected:")
    for pos, count in sorted(stats['position_gaps'].items(), key=lambda x: -x[1]):
        print(f"   {pos}: {count} teams")
    
    print(f"\n📋 Teams with Missing Positions: {len(stats['teams_missing_positions'])}")
    if stats['teams_missing_positions']:
        print("\n   Top 10 teams with most gaps:")
        sorted_teams = sorted(stats['teams_missing_positions'], 
                            key=lambda x: len(x['missing']), reverse=True)
        for team_info in sorted_teams[:10]:
            print(f"   - {team_info['team_name']}: Missing {', '.join(team_info['missing'])} "
                  f"({team_info['total_players']} players)")
    
    print(f"\n⚠️  Teams Over Capacity (>32 players): {len(stats['teams_over_capacity'])}")
    if stats['teams_over_capacity']:
        print("\n   Teams exceeding 32 players:")
        sorted_over = sorted(stats['teams_over_capacity'], 
                           key=lambda x: x['total_players'], reverse=True)
        for team_info in sorted_over[:10]:
            print(f"   - {team_info['team_name']}: {team_info['total_players']} players")
        if len(stats['teams_over_capacity']) > 10:
            print(f"   ... and {len(stats['teams_over_capacity']) - 10} more")

def simulate_cpu_market(iterations=100):
    """Simulate CPU AI market activity"""
    print("\n" + "="*60)
    print("CPU MARKET SIMULATION")
    print("="*60)
    print(f"Simulating {iterations} iterations of CPU AI activity...")
    print("This will process:")
    print("  - CPU AI actions (buy, loan, free agency, offers)")
    print("  - Expired offers (assigning players to teams)")
    print("="*60)
    
    # Get initial stats
    print("\n📊 INITIAL STATE:")
    initial_stats = get_team_composition_stats()
    print_stats(initial_stats)
    
    # Initialize CPU AI
    cpu_ai = CPUAI()
    
    # Track action counts
    total_actions = 0
    action_types = defaultdict(int)
    
    # Run simulations
    print(f"\n🔄 Running {iterations} iterations...")
    print("(This may take a few minutes)\n")
    
    for i in range(1, iterations + 1):
        # Process CPU AI actions
        result = cpu_ai.process_cpu_ai_actions()
        
        if result.get('success'):
            actions_count = result.get('actions_count', 0)
            total_actions += actions_count
            
            # Count action types
            for action in result.get('actions_taken', []):
                action_type = action.get('action', 'unknown')
                action_types[action_type] += 1
        
        # Process expired offers (this assigns players to teams)
        try:
            check_expired_offers()
        except Exception as e:
            print(f"   ⚠️  Warning: Error processing expired offers in iteration {i}: {e}")
        
        # Print progress every 5 iterations (more frequent for 25 iterations)
        if i % 5 == 0:
            print(f"   ✓ Completed {i}/{iterations} iterations ({total_actions} total actions)")
    
    # Get final stats
    print("\n📊 FINAL STATE:")
    final_stats = get_team_composition_stats()
    print_stats(final_stats)
    
    # Show improvements
    print(f"\n{'='*60}")
    print("IMPROVEMENT SUMMARY")
    print(f"{'='*60}")
    
    initial_gk_gap = len(initial_stats['teams_without_gk'])
    final_gk_gap = len(final_stats['teams_without_gk'])
    gk_improvement = initial_gk_gap - final_gk_gap
    
    print(f"\n⚽ Goalkeeper Situation:")
    print(f"   Before: {initial_gk_gap} teams without GK")
    print(f"   After:  {final_gk_gap} teams without GK")
    print(f"   Improvement: {gk_improvement} teams filled GK position")
    
    print(f"\n📈 Position Gap Changes:")
    for pos in set(list(initial_stats['position_gaps'].keys()) + 
                   list(final_stats['position_gaps'].keys())):
        initial_count = initial_stats['position_gaps'].get(pos, 0)
        final_count = final_stats['position_gaps'].get(pos, 0)
        change = initial_count - final_count
        if change != 0:
            print(f"   {pos}: {initial_count} → {final_count} ({change:+d})")
    
    # Check for over-capacity issues
    initial_over = len(initial_stats['teams_over_capacity'])
    final_over = len(final_stats['teams_over_capacity'])
    if initial_over > 0 or final_over > 0:
        print(f"\n⚠️  Over-Capacity Teams:")
        print(f"   Before: {initial_over} teams over 32 players")
        print(f"   After:  {final_over} teams over 32 players")
        if final_over > initial_over:
            print(f"   ⚠️  WARNING: More teams exceeded capacity after simulation!")
    
    print(f"\n🎯 Actions Taken:")
    print(f"   Total actions: {total_actions}")
    for action_type, count in sorted(action_types.items(), key=lambda x: -x[1]):
        print(f"   {action_type}: {count}")
    
    print(f"\n{'='*60}")
    print("Simulation Complete!")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    simulate_cpu_market(iterations=25)

