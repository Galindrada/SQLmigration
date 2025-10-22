#!/usr/bin/env python3
"""
Display a comprehensive summary of position averages
"""

import game_mechanics
import pandas as pd

def show_position_averages_summary():
    """Display detailed summary of position averages"""
    
    print("📊 POSITION AVERAGES SUMMARY")
    print("=" * 80)
    
    # Get cached position averages
    pos_avg_df = game_mechanics.get_cached_position_averages('pes6_league_db.sqlite')
    
    # Basic info
    print(f"📋 Dataset Info:")
    print(f"  Positions: {len(pos_avg_df)}")
    print(f"  Skills: {len(pos_avg_df.columns)}")
    print(f"  Total data points: {len(pos_avg_df) * len(pos_avg_df.columns)}")
    print()
    
    # Position names mapping
    position_names = {
        '0': 'Goalkeeper (GK)',
        '2': 'Sweeper (SW)',
        '3': 'Centre-Back (CB)',
        '4': 'Side-Back (SB)',
        '5': 'Defensive Midfielder (DMF)',
        '6': 'Wing-Back (WB)',
        '7': 'Center-Midfielder (CMF)',
        '8': 'Side-Midfielder (SMF)',
        '9': 'Attacking Midfielder (AMF)',
        '10': 'Winger (WG)',
        '11': 'Shadow Striker (SS)',
        '12': 'Striker (CF)'
    }
    
    # Show each position with key stats
    print("🎯 POSITION-BY-POSITION BREAKDOWN:")
    print("-" * 80)
    
    for position in pos_avg_df.index:
        pos_name = position_names.get(position, f"Position {position}")
        pos_data = pos_avg_df.loc[position]
        
        print(f"\n{pos_name} (Position {position}):")
        print(f"  📈 Key Skills:")
        
        # Show top 5 skills for this position
        top_skills = pos_data.sort_values(ascending=False).head(5)
        for skill, value in top_skills.items():
            print(f"    {skill}: {value:.1f}")
        
        # Show bottom 5 skills
        bottom_skills = pos_data.sort_values(ascending=True).head(5)
        print(f"  📉 Lowest Skills:")
        for skill, value in bottom_skills.items():
            print(f"    {skill}: {value:.1f}")
        
        # Show overall stats
        print(f"  📊 Stats:")
        print(f"    Average: {pos_data.mean():.1f}")
        print(f"    Range: {pos_data.min():.1f} - {pos_data.max():.1f}")
        print(f"    Std Dev: {pos_data.std():.1f}")
    
    # Show skill-by-skill breakdown
    print(f"\n🔍 SKILL-BY-SKILL BREAKDOWN:")
    print("-" * 80)
    
    # Get top 10 most variable skills (highest standard deviation)
    skill_variability = pos_avg_df.std().sort_values(ascending=False)
    print(f"\n📊 Most Variable Skills (highest position differences):")
    for skill, std_dev in skill_variability.head(10).items():
        min_val = pos_avg_df[skill].min()
        max_val = pos_avg_df[skill].max()
        print(f"  {skill}: {min_val:.1f} - {max_val:.1f} (std: {std_dev:.1f})")
    
    # Get least variable skills
    print(f"\n📊 Least Variable Skills (most similar across positions):")
    for skill, std_dev in skill_variability.tail(10).items():
        min_val = pos_avg_df[skill].min()
        max_val = pos_avg_df[skill].max()
        print(f"  {skill}: {min_val:.1f} - {max_val:.1f} (std: {std_dev:.1f})")
    
    # Show overall dataset statistics
    print(f"\n📈 OVERALL DATASET STATISTICS:")
    print("-" * 80)
    print(f"  Global Average: {pos_avg_df.values.mean():.1f}")
    print(f"  Global Range: {pos_avg_df.values.min():.1f} - {pos_avg_df.values.max():.1f}")
    print(f"  Global Std Dev: {pos_avg_df.values.std():.1f}")
    
    # Show position rankings for key skills
    key_skills = ['attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration', 
                  'shot_accuracy', 'goal_keeping', 'technique', 'mentality']
    
    print(f"\n🏆 POSITION RANKINGS FOR KEY SKILLS:")
    print("-" * 80)
    
    for skill in key_skills:
        if skill in pos_avg_df.columns:
            skill_rankings = pos_avg_df[skill].sort_values(ascending=False)
            print(f"\n{skill.upper()}:")
            for i, (position, value) in enumerate(skill_rankings.items(), 1):
                pos_name = position_names.get(position, f"Pos {position}")
                print(f"  {i}. {pos_name}: {value:.1f}")
    
    # Show correlation matrix for key skills
    print(f"\n🔗 SKILL CORRELATIONS (Key Skills):")
    print("-" * 80)
    
    key_skills_subset = [skill for skill in key_skills if skill in pos_avg_df.columns]
    if len(key_skills_subset) > 1:
        corr_matrix = pos_avg_df[key_skills_subset].T.corr()
        print("Correlation matrix (showing only key skills):")
        print(corr_matrix.round(2))

if __name__ == "__main__":
    show_position_averages_summary() 