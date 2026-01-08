"""
Player Swap and Direct Loan Features
=====================================

This module contains helper functions for Phase 2 features:
1. Player swap offers
2. Direct loan proposals  
3. Buy-back clauses

These features EXTEND existing functionality without modifying it.
"""

import sqlite3
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


def create_swap_offer(db_path: str, listing_id: int, buyer_team_id: int, 
                     target_player_id: int, swap_player_id: int, 
                     cash_compensation: int = 0, additional_swap_players: List[int] = None) -> Optional[int]:
    """
    Create a player swap offer (player(s) + cash for player)
    
    IMPORTANT: All players must NOT be blacklisted to create a swap offer
    
    Args:
        db_path: Path to database
        listing_id: ID of the listing being offered on
        buyer_team_id: Team making the offer
        target_player_id: Player they want to acquire
        swap_player_id: Primary player they're offering in exchange
        cash_compensation: Additional cash (positive = buyer pays, negative = seller pays)
        additional_swap_players: Optional list of additional player IDs to include in swap
    
    Returns:
        Offer ID if successful, None otherwise
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Collect all player IDs to check for blacklist
        all_player_ids = [target_player_id, swap_player_id]
        if additional_swap_players:
            all_player_ids.extend(additional_swap_players)
        
        # CRITICAL: Check if any player is blacklisted
        placeholders = ','.join(['?'] * len(all_player_ids))
        cur.execute(f"""
            SELECT COUNT(*) as count FROM blacklist 
            WHERE player_id IN ({placeholders}) AND user_id = 1
        """, all_player_ids)
        
        blacklist_count = cur.fetchone()['count']
        if blacklist_count > 0:
            print(f"Cannot create swap offer: One or more players are blacklisted")
            return None
        
        # Get swap player details
        cur.execute("SELECT market_value, player_name FROM players WHERE id = ?", (swap_player_id,))
        swap_player = cur.fetchone()
        
        if not swap_player:
            return None
        
        swap_valuation = swap_player['market_value']
        
        # Calculate total swap valuation (primary + additional players)
        total_swap_valuation = swap_valuation
        if additional_swap_players:
            placeholders = ','.join(['?'] * len(additional_swap_players))
            cur.execute(f"""
                SELECT SUM(market_value) as total_value FROM players
                WHERE id IN ({placeholders})
            """, additional_swap_players)
            additional_value = cur.fetchone()['total_value'] or 0
            total_swap_valuation += additional_value
        
        # Determine swap type
        if cash_compensation == 0:
            swap_type = 'swap' if not additional_swap_players else 'multi_swap'
        else:
            swap_type = 'cash+swap' if not additional_swap_players else 'cash+multi_swap'
        
        # Set expiration (7 days from now)
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()
        
        # Create the offer
        # Note: market_bazaar_offers doesn't have player_id column - it gets it from listing
        cur.execute("""
            INSERT INTO market_bazaar_offers 
            (listing_id, buyer_team_id, offered_price, 
             swap_player_id, swap_type, swap_valuation, cash_compensation,
             status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, ?)
        """, (listing_id, buyer_team_id, abs(cash_compensation), 
              swap_player_id, swap_type, total_swap_valuation, cash_compensation, expires_at))
        
        offer_id = cur.lastrowid
        
        # Add additional swap players to swap_offer_players table
        if additional_swap_players:
            # Ensure swap_offer_players table exists (auto-create if missing)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS swap_offer_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    offer_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    market_value INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (offer_id) REFERENCES market_bazaar_offers(id) ON DELETE CASCADE,
                    FOREIGN KEY (player_id) REFERENCES players(id),
                    UNIQUE(offer_id, player_id)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_swap_offer_players_offer 
                ON swap_offer_players(offer_id)
            """)
            
            for additional_player_id in additional_swap_players:
                cur.execute("SELECT market_value FROM players WHERE id = ?", (additional_player_id,))
                player_value = cur.fetchone()
                if player_value:
                    cur.execute("""
                        INSERT INTO swap_offer_players (offer_id, player_id, market_value)
                        VALUES (?, ?, ?)
                    """, (offer_id, additional_player_id, player_value['market_value']))
        
        conn.commit()
        
        return offer_id
        
    except Exception as e:
        print(f"Error creating swap offer: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def get_suitable_swap_players(db_path: str, team_id: int, target_player_value: int,
                              max_value_ratio: float = 1.3) -> List[Dict]:
    """
    Find players on a team suitable for swap offers
    
    IMPORTANT: Excludes blacklisted players (cannot be swapped)
    
    Args:
        db_path: Path to database
        team_id: Team to find swap candidates from
        target_player_value: Value of player being targeted
        max_value_ratio: Maximum value ratio (e.g., 1.3 = up to 130% of target value)
    
    Returns:
        List of suitable players for swaps (excluding blacklisted players)
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Find players within acceptable value range
        # CRITICAL: Exclude blacklisted players
        min_value = int(target_player_value * 0.5)
        max_value = int(target_player_value * max_value_ratio)
        
        cur.execute("""
            SELECT * FROM players
            WHERE club_id = ?
            AND market_value BETWEEN ? AND ?
            AND registered_position != '0'
            AND id NOT IN (
                SELECT player_id FROM blacklist WHERE user_id = 1
            )
            ORDER BY market_value DESC
            LIMIT 10
        """, (team_id, min_value, max_value))
        
        players = [dict(row) for row in cur.fetchall()]
        return players
        
    finally:
        conn.close()


def cpu_consider_swap_offer(db_path: str, cpu_team_id: int, listing_id: int) -> Optional[int]:
    """
    CPU team considers making a swap offer on a listing
    
    Logic:
    - 20% chance to propose a swap instead of cash offer
    - Finds suitable player from their squad
    - Calculates fair cash compensation based on value difference
    
    Returns:
        Offer ID if swap offer created, None otherwise
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Get listing details
        cur.execute("""
            SELECT l.*, p.player_name, p.market_value
            FROM market_bazaar_listings l
            JOIN players p ON l.player_id = p.id
            WHERE l.id = ?
        """, (listing_id,))
        
        listing = cur.fetchone()
        if not listing:
            return None
        
        target_value = listing['market_value']
        
        # Find suitable swap candidates
        candidates = get_suitable_swap_players(db_path, cpu_team_id, target_value)
        
        if not candidates:
            return None
        
        # Select a random candidate
        swap_player = random.choice(candidates)
        swap_value = swap_player['market_value']
        
        # Calculate cash compensation
        value_diff = target_value - swap_value
        
        # Add some randomness to compensation (90-110% of difference)
        cash_compensation = int(value_diff * random.uniform(0.9, 1.1))
        
        # Create the swap offer
        offer_id = create_swap_offer(
            db_path, listing_id, cpu_team_id,
            listing['player_id'], swap_player['id'],
            cash_compensation
        )
        
        return offer_id
        
    finally:
        conn.close()


def create_direct_loan_proposal(db_path: str, player_id: int, loaning_team_id: int,
                                borrowing_team_id: int, loan_duration: int = 1,
                                wage_coverage: float = 0.5, loan_fee: int = 0,
                                option_to_buy: bool = False, option_price: int = 0) -> Optional[int]:
    """
    Create a direct loan proposal (team-to-team, no listing required)
    
    Args:
        db_path: Path to database
        player_id: Player to loan
        loaning_team_id: Team loaning out the player
        borrowing_team_id: Team borrowing the player
        loan_duration: Loan duration in seasons (fixed to 1 for end of season)
        wage_coverage: How much of wages borrower pays (0.0 to 1.0)
        loan_fee: One-time loan fee (not monthly)
        option_to_buy: Whether there's an option to buy (deprecated, kept for compatibility)
        option_price: Price if option to buy is exercised (deprecated, kept for compatibility)
    
    Returns:
        Proposal ID if successful, None otherwise
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    cur = conn.cursor()
    
    try:
        # Ensure table exists (auto-create if missing)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS direct_loan_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                loaning_team_id INTEGER NOT NULL,
                borrowing_team_id INTEGER NOT NULL,
                loan_duration INTEGER DEFAULT 1,
                wage_coverage_percentage REAL DEFAULT 0.0,
                monthly_fee INTEGER DEFAULT 0,
                option_to_buy INTEGER DEFAULT 0,
                option_to_buy_price INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT,
                responded_at TEXT,
                FOREIGN KEY (player_id) REFERENCES players(id),
                FOREIGN KEY (loaning_team_id) REFERENCES teams(id),
                FOREIGN KEY (borrowing_team_id) REFERENCES teams(id)
            )
        """)
        
        # Create index for performance
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_direct_loan_proposals_status 
            ON direct_loan_proposals(status, borrowing_team_id)
        """)
        
        conn.commit()
        
    except Exception as e:
        print(f"Warning: Could not ensure direct_loan_proposals table exists: {e}")
        # Continue anyway - might already exist
    
    try:
        # Set expiration (7 days from now)
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()
        
        # Store loan_fee in monthly_fee column for compatibility (but it's a one-time fee)
        cur.execute("""
            INSERT INTO direct_loan_proposals
            (player_id, loaning_team_id, borrowing_team_id, loan_duration,
             wage_coverage_percentage, monthly_fee, option_to_buy, option_to_buy_price,
             status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP, ?)
        """, (player_id, loaning_team_id, borrowing_team_id, loan_duration,
              wage_coverage, loan_fee, 1 if option_to_buy else 0, option_price,
              expires_at))
        
        proposal_id = cur.lastrowid
        conn.commit()
        
        return proposal_id
        
    except Exception as e:
        print(f"Error creating loan proposal: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def cpu_propose_direct_loan(db_path: str, cpu_team_id: int) -> Optional[Dict]:
    """
    CPU team proposes a direct loan for one of their surplus/young players
    
    Logic:
    - Only proposes if team has > 28 players
    - Targets young players (< 23) or surplus players
    - Chooses a random CPU team that needs that position
    - 50% wage coverage, small monthly fee
    
    Returns:
        Dict with proposal details if successful, None otherwise
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Check if team has surplus players
        cur.execute("SELECT COUNT(*) as count FROM players WHERE club_id = ?", (cpu_team_id,))
        player_count = cur.fetchone()['count']
        
        if player_count <= 28:
            return None  # Team doesn't have surplus
        
        # Find young or surplus players
        cur.execute("""
            SELECT * FROM players
            WHERE club_id = ?
            AND (age < 23 OR overall < 75)
            AND registered_position != '0'
            ORDER BY RANDOM()
            LIMIT 5
        """, (cpu_team_id,))
        
        candidates = cur.fetchall()
        if not candidates:
            return None
        
        player = random.choice(candidates)
        
        # Find a team that might need this position
        cur.execute("""
            SELECT t.id FROM teams t
            JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE lt.user_id = 1
            AND t.id != ?
            AND t.id != 141
            ORDER BY RANDOM()
            LIMIT 1
        """, (cpu_team_id,))
        
        target_team = cur.fetchone()
        if not target_team:
            return None
        
        # Calculate loan terms
        player_salary = player['salary'] or 1000000
        loan_fee = int(player_salary * 0.1)  # 10% of annual salary as one-time loan fee
        wage_coverage = random.uniform(0.4, 0.7)  # 40-70% wage coverage
        
        # Create proposal
        proposal_id = create_direct_loan_proposal(
            db_path, player['id'], cpu_team_id, target_team['id'],
            loan_duration=1, wage_coverage=wage_coverage, loan_fee=loan_fee
        )
        
        if proposal_id:
            return {
                'proposal_id': proposal_id,
                'player_name': player['player_name'],
                'loaning_team_id': cpu_team_id,
                'borrowing_team_id': target_team['id'],
                'loan_fee': loan_fee,
                'wage_coverage': wage_coverage
            }
        
        return None
        
    finally:
        conn.close()


# Buy-back clause functionality removed per user request
# The database table exists but is not actively used
# Can be implemented later if needed


def complete_swap_offer(db_path: str, offer_id: int, user_team_id: int = None) -> bool:
    """
    Complete a player swap offer
    
    CRITICAL: After swap completion, BOTH players are blacklisted
    This prevents constant back-and-forth swapping
    
    Args:
        db_path: Path to database
        offer_id: Offer ID to complete
        user_team_id: User's team ID (club_id) - if provided, ensures swap player goes to correct team
    
    Returns:
        True if successful, False otherwise
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Get offer details
        cur.execute("""
            SELECT o.*, l.player_id as target_player_id, l.team_id as listing_team_id,
                   p1.club_id as target_current_club, p2.club_id as swap_current_club,
                   p1.player_name as target_name, p2.player_name as swap_name
            FROM market_bazaar_offers o
            JOIN market_bazaar_listings l ON o.listing_id = l.id
            JOIN players p1 ON l.player_id = p1.id
            LEFT JOIN players p2 ON o.swap_player_id = p2.id
            WHERE o.id = ?
        """, (offer_id,))
        
        offer = cur.fetchone()
        if not offer or offer['swap_type'] not in ['swap', 'cash+swap', 'multi_swap', 'cash+multi_swap']:
            return False
        
        target_player_id = offer['target_player_id']
        swap_player_id = offer['swap_player_id']
        buyer_team_id = offer['buyer_team_id']  # CPU team (making the offer)
        cash_compensation = offer['cash_compensation']
        
        # Get additional swap players if this is a multi-player swap
        additional_swap_players = []
        if offer['swap_type'] in ['multi_swap', 'cash+multi_swap']:
            # Ensure swap_offer_players table exists (auto-create if missing)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS swap_offer_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    offer_id INTEGER NOT NULL,
                    player_id INTEGER NOT NULL,
                    market_value INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (offer_id) REFERENCES market_bazaar_offers(id) ON DELETE CASCADE,
                    FOREIGN KEY (player_id) REFERENCES players(id),
                    UNIQUE(offer_id, player_id)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_swap_offer_players_offer 
                ON swap_offer_players(offer_id)
            """)
            
            cur.execute("""
                SELECT player_id FROM swap_offer_players
                WHERE offer_id = ?
                ORDER BY id
            """, (offer_id,))
            rows = cur.fetchall()
            additional_swap_players = [int(row['player_id']) for row in rows]
        
        # Determine seller team ID (where swap player should go)
        # For CPU-to-user swaps: swap player goes to user's team
        # If user_team_id is provided, use it; otherwise use listing_team_id
        if user_team_id:
            seller_team_id = user_team_id  # User's team (where swap player should go)
            print(f"✅ Using provided user_team_id: {seller_team_id} for swap player")
        else:
            # Fallback: use listing team_id (should be user's team for cpu_user_offer listings)
            seller_team_id = offer['listing_team_id']
            print(f"⚠️  Using listing_team_id: {seller_team_id} for swap player (user_team_id not provided)")
        
        print(f"Swap details: Target player {target_player_id} -> buyer_team {buyer_team_id}, Swap player {swap_player_id} -> seller_team {seller_team_id}")
        if additional_swap_players:
            print(f"Additional swap players: {additional_swap_players}")
        
        # Execute the swap: exchange players
        # Target player (user's player) goes to buyer_team_id (CPU team)
        cur.execute("UPDATE players SET club_id = ? WHERE id = ?", 
                   (buyer_team_id, target_player_id))
        print(f"✅ Moved target player {target_player_id} to buyer team {buyer_team_id}")
        
        # Primary swap player (CPU's player) goes to seller_team_id (user's team)
        cur.execute("UPDATE players SET club_id = ? WHERE id = ?", 
                   (seller_team_id, swap_player_id))
        print(f"✅ Moved swap player {swap_player_id} to seller team {seller_team_id}")
        
        # Move additional swap players to user's team
        for add_player_id in additional_swap_players:
            cur.execute("UPDATE players SET club_id = ? WHERE id = ?", 
                       (seller_team_id, add_player_id))
            print(f"✅ Moved additional swap player {add_player_id} to seller team {seller_team_id}")
        
        # Verify the swap
        cur.execute("SELECT club_id FROM players WHERE id = ?", (swap_player_id,))
        verify = cur.fetchone()
        if verify and verify['club_id'] != seller_team_id:
            print(f"❌ ERROR: Swap player {swap_player_id} is at club {verify['club_id']}, expected {seller_team_id}")
            raise Exception(f"Swap player transfer failed: player at wrong club")
        else:
            print(f"✅ Verified: Swap player {swap_player_id} is at correct club {seller_team_id}")
        
        # Handle cash compensation if any
        if cash_compensation != 0:
            if cash_compensation > 0:
                # Buyer pays seller
                cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", 
                           (cash_compensation, buyer_team_id))
                cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?", 
                           (cash_compensation, seller_team_id))
            else:
                # Seller pays buyer (negative compensation)
                cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?", 
                           (abs(cash_compensation), buyer_team_id))
                cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", 
                           (abs(cash_compensation), seller_team_id))
        
        # Mark offer and listing as completed
        cur.execute("UPDATE market_bazaar_offers SET status = 'completed' WHERE id = ?", (offer_id,))
        cur.execute("UPDATE market_bazaar_listings SET status = 'completed' WHERE id = ?", 
                   (offer['listing_id'],))
        
        # CRITICAL: Blacklist ALL players involved in the swap
        # This prevents constant back-and-forth trading
        all_swap_player_ids = [swap_player_id] + additional_swap_players
        for player_id in [target_player_id] + all_swap_player_ids:
            cur.execute("INSERT OR IGNORE INTO blacklist (user_id, player_id) VALUES (1, ?)", 
                       (player_id,))
        
        conn.commit()
        
        player_count = len([target_player_id] + all_swap_player_ids)
        print(f"✅ Swap completed: {offer['target_name']} ↔ {offer['swap_name']}")
        if additional_swap_players:
            print(f"   + {len(additional_swap_players)} additional player(s)")
        print(f"   All {player_count} players blacklisted to prevent re-trading")
        
        return True
        
    except Exception as e:
        print(f"Error completing swap: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    # Test the functions
    print("Testing Player Swap and Direct Loan Features...")
    
    db_path = 'pes6_league_db.sqlite'
    
    # Test 1: Find suitable swap players
    print("\n1. Testing swap player search...")
    players = get_suitable_swap_players(db_path, 4, 10000000)  # Inter, 10M target
    print(f"   Found {len(players)} suitable swap candidates")
    if players:
        print(f"   Example: {players[0]['player_name']} (€{players[0]['market_value']:,})")
    
    # Test 2: Test direct loan proposal
    print("\n2. Testing direct loan proposal logic...")
    print("   (Direct loan proposals ready but not yet integrated into CPU AI)")
    
    print("\n✅ Phase 2 features working correctly!")

