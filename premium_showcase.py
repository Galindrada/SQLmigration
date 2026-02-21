"""
Premium Showcase - Independent market bazaar feature.
3 CPU top players from low-budget non-Powerdog teams + 6 user slots.
Undisclosed bid timer. Powerdog bid at end.
"""

import sqlite3

# --- Config: imported from app.py (change at top of app.py) ---
try:
    from app import PREMIUM_SHOWCASE_TIMER_MINUTES, PREMIUM_SHOWCASE_USER_SLOTS
except ImportError:
    PREMIUM_SHOWCASE_TIMER_MINUTES = 1
    PREMIUM_SHOWCASE_USER_SLOTS = 6
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import db_helper

# Skills for "top 3 skills" - numeric skill columns
SKILL_COLS = [
    'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
    'response', 'agility', 'dribble_accuracy', 'dribble_speed',
    'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
    'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
    'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
    'team_work', 'consistency', 'condition_fitness'
]
SKILL_LABELS = {
    'attack': 'Attack', 'defense': 'Defense', 'balance': 'Balance', 'stamina': 'Stamina',
    'top_speed': 'Top Speed', 'acceleration': 'Acceleration', 'response': 'Response',
    'agility': 'Agility', 'dribble_accuracy': 'Dribble Accuracy', 'dribble_speed': 'Dribble Speed',
    'short_pass_accuracy': 'Short Pass', 'short_pass_speed': 'Short Pass Speed',
    'long_pass_accuracy': 'Long Pass', 'long_pass_speed': 'Long Pass Speed',
    'shot_accuracy': 'Shot Accuracy', 'shot_power': 'Shot Power', 'shot_technique': 'Shot Technique',
    'free_kick_accuracy': 'Free Kick', 'swerve': 'Swerve', 'heading': 'Heading', 'jump': 'Jump',
    'technique': 'Technique', 'aggression': 'Aggression', 'mentality': 'Mentality',
    'goal_keeping': 'Goalkeeping', 'team_work': 'Team Work', 'consistency': 'Consistency',
    'condition_fitness': 'Condition'
}


def get_db_path():
    from config import Config
    return getattr(Config, 'SQLITE_DB_PATH', 'pes6_league_db.sqlite')


def _blacklist_player(conn: sqlite3.Connection, player_id: int) -> bool:
    """Add player to general blacklist (user_id=1). Idempotent."""
    cur = conn.cursor()
    try:
        cur.execute("INSERT OR IGNORE INTO blacklist (user_id, player_id) VALUES (1, ?)", (player_id,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        cur.close()


def ensure_tables(conn: sqlite3.Connection):
    """Create premium showcase tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS premium_showcase_rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT DEFAULT 'active',
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS premium_showcase_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            slot_index INTEGER NOT NULL,
            player_id INTEGER,
            team_id INTEGER,
            source TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (round_id) REFERENCES premium_showcase_rounds(id),
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS premium_showcase_bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL,
            bidder_user_id INTEGER,
            bidder_team_id INTEGER,
            bid_amount INTEGER NOT NULL,
            is_user_bid INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (slot_id) REFERENCES premium_showcase_slots(id),
            FOREIGN KEY (bidder_user_id) REFERENCES users(id),
            FOREIGN KEY (bidder_team_id) REFERENCES teams(id)
        )
    """)
    conn.commit()


def get_bundled_skills(player_row: dict) -> Dict[str, int]:
    """Compute bundled skill ratings (same logic as player profile)."""
    d = player_row
    return {
        'Attack': d.get('attack_rating') if d.get('attack_rating') else ((d.get('attack') or 0) + (d.get('shot_technique') or 0) + (d.get('shot_accuracy') or 0) + (d.get('aggression') or 0)) // 4,
        'Defense': d.get('defense_rating') if d.get('defense_rating') else ((d.get('defense') or 0) + (d.get('heading') or 0) + (d.get('jump') or 0) + (d.get('balance') or 0)) // 4,
        'Physical': d.get('physical_rating') if d.get('physical_rating') else ((d.get('stamina') or 0) + (d.get('top_speed') or 0) + (d.get('acceleration') or 0) + (d.get('response') or 0) + (d.get('agility') or 0) + (d.get('jump') or 0)) // 6,
        'Power': d.get('power_rating') if d.get('power_rating') else ((d.get('shot_power') or 0) + (d.get('balance') or 0) + (d.get('mentality') or 0)) // 3,
        'Technique': d.get('technique_rating') if d.get('technique_rating') else ((d.get('technique') or 0) + (d.get('swerve') or 0) + (d.get('free_kick_accuracy') or 0) + (d.get('dribble_accuracy') or 0) + (d.get('dribble_speed') or 0) + (d.get('short_pass_accuracy') or 0) + (d.get('short_pass_speed') or 0) + (d.get('long_pass_accuracy') or 0) + (d.get('long_pass_speed') or 0)) // 9,
        'Goalkeeping': d.get('goalkeeping_rating') if d.get('goalkeeping_rating') else ((d.get('defense') or 0) + (d.get('goal_keeping') or 0) + (d.get('response') or 0) + (d.get('agility') or 0)) // 4,
    }


def get_top_3_skills(player_row: dict) -> List[Tuple[str, int]]:
    """Return top 3 numeric skills for a player."""
    skills = []
    for col in SKILL_COLS:
        val = player_row.get(col)
        if val is not None and isinstance(val, (int, float)):
            skills.append((SKILL_LABELS.get(col, col), int(val)))
    skills.sort(key=lambda x: x[1], reverse=True)
    return skills[:3]


def get_active_round(conn: sqlite3.Connection) -> Optional[dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT id, status, expires_at, created_at
        FROM premium_showcase_rounds
        WHERE status = 'active' AND expires_at > ?
        ORDER BY id DESC LIMIT 1
    """, (datetime.now().isoformat(),))
    row = cur.fetchone()
    return dict(row) if row else None


def cancel_showcase(conn: sqlite3.Connection) -> Dict:
    """Cancel the current active showcase round without processing bids or transfers."""
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id FROM premium_showcase_rounds
            WHERE status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return {'success': False, 'error': 'No active showcase to cancel'}
        round_id = row['id']
        cur.execute("""
            UPDATE premium_showcase_rounds
            SET status = 'cancelled'
            WHERE id = ?
        """, (round_id,))
        conn.commit()
        return {'success': True, 'round_id': round_id}
    finally:
        cur.close()


def populate_showcase(conn: sqlite3.Connection) -> Dict:
    """
    Populate new showcase round: 3 CPU players from non-Powerdog low-budget teams,
    2 empty user slots. 3-hour timer.
    """
    ensure_tables(conn)
    cur = conn.cursor()

    # Get non-Powerdog CPU teams with lowest budget (top 10)
    cur.execute("""
        SELECT t.id, t.club_name, t.budget, t.stance
        FROM teams t
        JOIN league_teams lt ON t.id = lt.id
        WHERE lt.user_id = 1
        AND (t.stance IS NULL OR t.stance != 'Powerdog')
        AND t.id != 141
        ORDER BY COALESCE(t.budget, 0) ASC
        LIMIT 10
    """)
    low_budget_teams = cur.fetchall()
    if not low_budget_teams:
        return {'success': False, 'error': 'No non-Powerdog CPU teams found'}

    # Pick top player from each of 3 lowest-budget teams (one per team)
    selected_players = []
    used_teams = set()
    for team in low_budget_teams:
        if len(selected_players) >= 3:
            break
        team_id = team['id']
        if team_id in used_teams:
            continue
        cur.execute("""
            SELECT p.*, t.club_name
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE p.club_id = ? AND p.loaned_by IS NULL
            AND p.id NOT IN (SELECT player_id FROM blacklist WHERE user_id = 1)
            ORDER BY p.overall DESC, p.market_value DESC
            LIMIT 1
        """, (team_id,))
        p = cur.fetchone()
        if p:
            selected_players.append(dict(p))
            used_teams.add(team_id)

    if len(selected_players) < 3:
        # Fallback: get top 3 from all non-Powerdog teams by overall
        cur.execute("""
            SELECT p.*, t.club_name, t.id as team_id
            FROM players p
            JOIN teams t ON p.club_id = t.id
            JOIN league_teams lt ON t.id = lt.id
            WHERE lt.user_id = 1
            AND (t.stance IS NULL OR t.stance != 'Powerdog')
            AND p.loaned_by IS NULL
            AND p.id NOT IN (SELECT player_id FROM blacklist WHERE user_id = 1)
            ORDER BY COALESCE(t.budget, 0) ASC, p.overall DESC
            LIMIT 3
        """)
        selected_players = [dict(r) for r in cur.fetchall()]

    if not selected_players:
        return {'success': False, 'error': 'No CPU players available'}

    # Create round
    expires_at = (datetime.now() + timedelta(minutes=PREMIUM_SHOWCASE_TIMER_MINUTES)).isoformat()
    cur.execute(
        "INSERT INTO premium_showcase_rounds (status, expires_at) VALUES ('active', ?)",
        (expires_at,)
    )
    round_id = cur.lastrowid

    # Insert slots
    for i, player in enumerate(selected_players[:3]):
        cur.execute("""
            INSERT INTO premium_showcase_slots (round_id, slot_index, player_id, team_id, source)
            VALUES (?, ?, ?, ?, 'cpu')
        """, (round_id, i, player['id'], player.get('club_id') or player.get('team_id')))

    # Empty user slots (count from config)
    user_slot_values = ', '.join([f'(?, {i + 3}, NULL, NULL, \'user\')' for i in range(PREMIUM_SHOWCASE_USER_SLOTS)])
    cur.execute(f"""
        INSERT INTO premium_showcase_slots (round_id, slot_index, player_id, team_id, source)
        VALUES {user_slot_values}
    """, (round_id,) * PREMIUM_SHOWCASE_USER_SLOTS)
    conn.commit()
    # Blacklist CPU players immediately when they join the auction
    cpu_player_ids = [p['id'] for p in selected_players[:3]]
    for pid in cpu_player_ids:
        _blacklist_player(conn, pid)
    return {'success': True, 'round_id': round_id, 'expires_at': expires_at, 'player_ids': cpu_player_ids}


def get_showcase_data(conn: sqlite3.Connection) -> Dict:
    """Get active showcase round with slots and player details."""
    ensure_tables(conn)
    round_row = get_active_round(conn)
    if not round_row:
        return {'active': False, 'round': None, 'slots': [], 'expires_at': None}

    cur = conn.cursor()
    cur.execute("""
        SELECT ps.*, p.player_name, p.overall, p.age, p.registered_position, p.market_value,
               p.salary, p.profile_image,
               t.club_name, t.id as team_id,
               p.attack, p.defense, p.balance, p.stamina, p.top_speed, p.acceleration,
               p.response, p.agility, p.dribble_accuracy, p.dribble_speed,
               p.short_pass_accuracy, p.short_pass_speed, p.long_pass_accuracy, p.long_pass_speed,
               p.shot_accuracy, p.shot_power, p.shot_technique, p.free_kick_accuracy, p.swerve,
               p.heading, p.jump, p.technique, p.aggression, p.mentality, p.goal_keeping,
               p.team_work, p.consistency, p.condition_fitness,
               p.attack_rating, p.defense_rating, p.physical_rating, p.power_rating,
               p.technique_rating, p.goalkeeping_rating
        FROM premium_showcase_slots ps
        LEFT JOIN players p ON ps.player_id = p.id
        LEFT JOIN teams t ON p.club_id = t.id
        WHERE ps.round_id = ?
        ORDER BY ps.slot_index
    """, (round_row['id'],))
    slots_raw = cur.fetchall()
    slots = []
    for row in slots_raw:
        s = dict(row)
        if s.get('player_id'):
            s['top_3_skills'] = get_top_3_skills(s)
            s['bundled_skills'] = get_bundled_skills(s)
        else:
            s['top_3_skills'] = []
            s['bundled_skills'] = {}
        slots.append(s)
    return {
        'active': True,
        'round': round_row,
        'slots': slots,
        'expires_at': round_row['expires_at']
    }


def submit_user_slot(conn: sqlite3.Connection, slot_id: int, player_id: int, user_id: int) -> Dict:
    """User fills an empty user slot with their player (overall > 83)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT ps.*, pr.status, pr.expires_at
        FROM premium_showcase_slots ps
        JOIN premium_showcase_rounds pr ON ps.round_id = pr.id
        WHERE ps.id = ? AND ps.source = 'user'
    """, (slot_id,))
    slot = cur.fetchone()
    if not slot:
        return {'success': False, 'error': 'Slot not found'}
    if slot['player_id']:
        return {'success': False, 'error': 'Slot already filled'}
    if slot['status'] != 'active' or datetime.fromisoformat(slot['expires_at']) <= datetime.now():
        return {'success': False, 'error': 'Showcase expired or closed'}

    # Verify player belongs to user and overall > 83
    cur.execute("""
        SELECT p.id, p.player_name, p.overall, p.loaned_by, p.club_id
        FROM players p
        JOIN teams t ON p.club_id = t.id
        JOIN league_teams lt ON t.id = lt.id
        WHERE p.id = ? AND lt.user_id = ?
    """, (player_id, user_id))
    player = cur.fetchone()
    if not player:
        return {'success': False, 'error': 'Player not found'}
    if player['overall'] is None or int(player['overall']) <= 83:
        return {'success': False, 'error': 'Player must have overall greater than 83'}
    if player['loaned_by']:
        return {'success': False, 'error': 'Cannot list loaned players'}

    cur.execute(
        "UPDATE premium_showcase_slots SET player_id = ?, team_id = ? WHERE id = ?",
        (player_id, player['club_id'], slot_id)
    )
    conn.commit()
    # Blacklist player immediately when they join the auction
    _blacklist_player(conn, player_id)
    return {'success': True}


def submit_bid(conn: sqlite3.Connection, slot_id: int, bid_amount: int, user_id: int) -> Dict:
    """User submits undisclosed bid. Each user can only have one bid per slot (latest overwrites)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT ps.*, pr.status, pr.expires_at
        FROM premium_showcase_slots ps
        JOIN premium_showcase_rounds pr ON ps.round_id = pr.id
        WHERE ps.id = ?
    """, (slot_id,))
    slot = cur.fetchone()
    if not slot:
        return {'success': False, 'error': 'Slot not found'}
    # User slots can be bid on only when filled
    if slot['source'] == 'user' and not slot['player_id']:
        return {'success': False, 'error': 'Slot not yet filled'}
    if slot['status'] != 'active' or datetime.fromisoformat(slot['expires_at']) <= datetime.now():
        return {'success': False, 'error': 'Bidding closed'}

    if bid_amount <= 0:
        return {'success': False, 'error': 'Bid must be positive'}

    # Get user's team
    cur.execute("SELECT id FROM league_teams WHERE user_id = ? LIMIT 1", (user_id,))
    lt = cur.fetchone()
    if not lt:
        return {'success': False, 'error': 'No team found'}

    # Delete previous bid from this user for this slot
    cur.execute("""
        DELETE FROM premium_showcase_bids
        WHERE slot_id = ? AND bidder_user_id = ?
    """, (slot_id, user_id))
    cur.execute("""
        INSERT INTO premium_showcase_bids (slot_id, bidder_user_id, bidder_team_id, bid_amount, is_user_bid)
        VALUES (?, ?, ?, ?, 1)
    """, (slot_id, user_id, lt['id'], bid_amount))
    conn.commit()
    return {'success': True}


def process_showcase_end(conn: sqlite3.Connection) -> Dict:
    """At timer end: Powerdog with most money bids 40-185% on each slot. Determine winners."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM premium_showcase_rounds
        WHERE status = 'active' AND expires_at <= ?
        ORDER BY id DESC LIMIT 1
    """, (datetime.now().isoformat(),))
    round_row = cur.fetchone()
    if not round_row:
        return {'success': False, 'processed': False}

    round_id = round_row['id']

    # Get all Powerdog teams (ordered by budget, exclude 141)
    cur.execute("""
        SELECT t.id, t.club_name, t.budget
        FROM teams t
        JOIN league_teams lt ON t.id = lt.id
        WHERE lt.user_id = 1 AND t.stance = 'Powerdog' AND t.id != 141
        ORDER BY COALESCE(t.budget, 0) DESC
    """)
    powerdogs = cur.fetchall()
    if not powerdogs:
        powerdogs = [{'id': None, 'club_name': 'Powerdog', 'budget': 0}]
    else:
        random.shuffle(powerdogs)  # Vary which Powerdog bids on which slot

    # Get slots with players (include age, salary, source for bid skew and toxic check)
    cur.execute("""
        SELECT ps.id, ps.player_id, ps.source, p.market_value, p.player_name, p.age, p.salary, p.contract_years_remaining
        FROM premium_showcase_slots ps
        LEFT JOIN players p ON ps.player_id = p.id
        WHERE ps.round_id = ?
    """, (round_id,))
    slots = cur.fetchall()

    def _is_user_slot_salary_toxic(conn: sqlite3.Connection, slot: dict) -> bool:
        """For user-listed slots: True if player salary >= 150% of fair salary (toxic)."""
        if (slot.get('source') or '') != 'user':
            return False
        salary = slot.get('salary') or 0
        if salary <= 0:
            return False
        player_id = slot.get('player_id')
        if not player_id:
            return False
        cur2 = conn.cursor()
        cur2.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        row = cur2.fetchone()
        cur2.close()
        if not row:
            return False
        player_dict = dict(row)
        try:
            from cpu_ai import CPUAI
            fair_salary = CPUAI(get_db_path()).calculate_fair_salary(player_dict)
        except Exception:
            return False
        if fair_salary <= 0:
            return False
        return salary >= fair_salary * 1.5

    # Toxic contract check: rough heuristic (salary * years > market_value * 2 = overpaid)
    def _is_toxic_slot(slot_dict) -> bool:
        salary = slot_dict.get('salary') or 0
        years = max(1, slot_dict.get('contract_years_remaining') or 1)
        mv = slot_dict.get('market_value') or 0
        if mv <= 0:
            return False
        total_commitment = salary * years
        return total_commitment > mv * 2  # Overpaid if total cost > 2x market value

    # Assign a different Powerdog per slot (cycle through if fewer Powerdogs than slots)
    for i, slot in enumerate(slots):
        slot = dict(slot)  # sqlite3.Row has no .get(); convert for dict-style access
        if not slot['player_id']:
            continue
        mv = slot['market_value'] or 0
        if mv <= 0:
            continue
        powerdog = powerdogs[i % len(powerdogs)]
        # Pre-check for user-listed players: if salary is toxic (>=150% of fair salary), bid 0€
        if _is_user_slot_salary_toxic(conn, slot):
            powerdog_bid = 0
            if powerdog['id']:
                cur.execute("""
                    INSERT INTO premium_showcase_bids (slot_id, bidder_user_id, bidder_team_id, bid_amount, is_user_bid)
                    VALUES (?, NULL, ?, ?, 0)
                """, (slot['id'], powerdog['id'], powerdog_bid))
            continue
        # Random bid 40% to 185%
        pct = random.uniform(0.40, 1.85)
        # Age-based skew: Powerdog undervalues youth, penalizes older players
        age = slot.get('age')
        if age is not None:
            try:
                age_int = int(age)
                if age_int < 21:
                    age_skew = random.uniform(-0.20, 0.20)   # -20% to +20%
                elif age_int <= 25:
                    age_skew = random.uniform(-0.35, 0.10)   # -35% to +10%
                elif age_int <= 29:
                    age_skew = random.uniform(-0.40, 0.00)   # -40% to 0%
                else:
                    age_skew = random.uniform(-0.50, -0.20)  # -50% to -20%
                pct = pct * (1 + age_skew)
            except (ValueError, TypeError):
                pass
        # Toxic salary skew: reduce bid for overpaid players
        if _is_toxic_slot(slot):
            toxic_skew = random.uniform(-0.35, -0.15)  # -35% to -15%
            pct = pct * (1 + toxic_skew)
        powerdog_bid = max(1, int(mv * pct))
        if powerdog['id']:
            cur.execute("""
                INSERT INTO premium_showcase_bids (slot_id, bidder_user_id, bidder_team_id, bid_amount, is_user_bid)
                VALUES (?, NULL, ?, ?, 0)
            """, (slot['id'], powerdog['id'], powerdog_bid))

    # Determine winners: highest bid per slot, get team names
    winners = []
    for slot in slots:
        if not slot['player_id']:
            continue
        cur.execute("""
            SELECT psb.bid_amount, psb.bidder_user_id, psb.bidder_team_id
            FROM premium_showcase_bids psb
            WHERE psb.slot_id = ?
            ORDER BY psb.bid_amount DESC
            LIMIT 1
        """, (slot['id'],))
        high_bid = cur.fetchone()
        if high_bid:
            bidder_team_id = high_bid['bidder_team_id']
            bidder_user_id = high_bid['bidder_user_id']
            winner_name = 'Unknown'
            if bidder_user_id:
                cur.execute("SELECT username FROM users WHERE id = ?", (bidder_user_id,))
                u = cur.fetchone()
                winner_name = u['username'] if u else 'Unknown'
            elif bidder_team_id:
                cur.execute("SELECT club_name FROM teams WHERE id = ?", (bidder_team_id,))
                t = cur.fetchone()
                winner_name = t['club_name'] if t else 'Unknown'
            # Include seller_team_id for transfer/finance logic (slot has team_id)
            cur.execute("SELECT team_id FROM premium_showcase_slots WHERE id = ?", (slot['id'],))
            slot_row = cur.fetchone()
            seller_team_id = slot_row['team_id'] if slot_row and slot_row['team_id'] else None
            winners.append({
                'player_id': slot['player_id'],
                'player_name': slot['player_name'],
                'winner_team': winner_name,
                'amount': high_bid['bid_amount'],
                'seller_team_id': seller_team_id,
                'buyer_team_id': bidder_team_id,
                'bidder_user_id': bidder_user_id,
            })

    cur.execute(
        "UPDATE premium_showcase_rounds SET status = 'closed' WHERE id = ?",
        (round_id,)
    )
    conn.commit()

    # Do NOT auto-start here: caller must apply transfers first, then call populate_showcase
    return {
        'success': True,
        'processed': True,
        'round_id': round_id,
        'winners': winners,
        'new_round_started': False
    }
