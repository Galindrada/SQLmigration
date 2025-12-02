#!/usr/bin/env python3
"""
Test MVP image fetching for international games
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db_helper

def test_mvp_images():
    """Test MVP image fetching for international games"""
    with app.app_context():
        cur = db_helper.get_cursor()
        
        # Get recent international games with MVP
        cur.execute("""
            SELECT ig.id, ig.home_team_name, ig.away_team_name, 
                   ig.home_score, ig.away_score, ig.mvp_player_id,
                   p.player_name, p.profile_image
            FROM international_games ig
            LEFT JOIN players p ON ig.mvp_player_id = p.id
            WHERE ig.is_played = 1 AND ig.mvp_player_id IS NOT NULL
            ORDER BY ig.id DESC
            LIMIT 10
        """)
        games = cur.fetchall()
        
        print("="*80)
        print("MVP IMAGE VERIFICATION FOR INTERNATIONAL GAMES")
        print("="*80)
        print(f"Found {len(games)} games with MVP\n")
        
        for game in games:
            game_id = game['id']
            mvp_id = game['mvp_player_id']
            mvp_name = game['player_name']
            profile_image = game['profile_image']
            
            print(f"Game {game_id}: {game['home_team_name']} {game['home_score']}-{game['away_score']} {game['away_team_name']}")
            print(f"  MVP Player ID: {mvp_id}")
            print(f"  MVP Player Name: {mvp_name}")
            print(f"  Profile Image (from DB): {profile_image}")
            
            # Check if player exists
            cur.execute("SELECT id, player_name, profile_image FROM players WHERE id = ?", (mvp_id,))
            player = cur.fetchone()
            
            if player:
                print(f"  ✅ Player found in database")
                print(f"  Player Name (from DB): {player['player_name']}")
                print(f"  Profile Image (from DB): {player['profile_image']}")
                
                # Check if image file exists
                if player['profile_image']:
                    image_path = os.path.join(app.root_path, 'static', 'player_images', player['profile_image'])
                    exists = os.path.exists(image_path)
                    print(f"  Image file exists: {exists}")
                    if not exists:
                        print(f"  ⚠️  Image file NOT FOUND at: {image_path}")
                else:
                    print(f"  ⚠️  No profile_image in database")
            else:
                print(f"  ❌ Player NOT FOUND in database!")
            
            # Check if MVP was actually in this game
            cur.execute("""
                SELECT COUNT(*) as count
                FROM international_player_game_stats
                WHERE game_id = ? AND player_id = ?
            """, (game_id, mvp_id))
            in_game = cur.fetchone()['count'] > 0
            print(f"  MVP in game stats: {in_game}")
            
            if not in_game:
                print(f"  ⚠️  WARNING: MVP player {mvp_id} ({mvp_name}) is NOT in game stats!")
                # Show who actually played
                cur.execute("""
                    SELECT player_id, player_name, goals, assists
                    FROM international_player_game_stats
                    WHERE game_id = ?
                    ORDER BY goals DESC, assists DESC
                    LIMIT 5
                """, (game_id,))
                actual_players = cur.fetchall()
                print(f"  Top players in game:")
                for p in actual_players:
                    print(f"    - {p['player_name']} (ID: {p['player_id']}) - {p['goals']}G {p['assists']}A")
            
            print()

if __name__ == '__main__':
    test_mvp_images()

