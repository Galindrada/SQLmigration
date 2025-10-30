#!/usr/bin/env python3
import argparse
import csv
import os
import random
import sqlite3
import sys
from datetime import datetime
from typing import Dict, List, Tuple

# Ensure project root is on sys.path so we can import game_mechanics when run from dev_tools/
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Ensure relative resources in game_mechanics (e.g., 'pes6_league_db.sqlite') resolve
try:
    os.chdir(PROJECT_ROOT)
except Exception:
    pass

# Import model mechanics from the project
from game_mechanics import (
    calculate_player_skill_development,
    generate_complete_development_key,
    get_position_skill_weights_from_averages,
    calculate_position_averages_from_db,
    get_seed_player_targets,
)


# Core player skill columns used in game_mechanics.calculate_player_skill_development
SKILL_COLUMNS: List[str] = [
    'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
    'response', 'agility', 'dribble_accuracy', 'dribble_speed',
    'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
    'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
    'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
    'team_work'
]


def read_base_players(db_path: str, limit: int, include_gk: bool) -> List[Dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        # Prefer outfield players, optionally include a few GKs
        base_players: List[Dict] = []

        def fetch_block(pos_filter: str, count: int) -> List[Dict]:
            cur.execute(
                f"""
                SELECT id, player_name AS name, age, registered_position,
                       {', '.join(SKILL_COLUMNS)}
                FROM players
                WHERE registered_position {pos_filter}
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (count,),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

        # Outfield first (registered_position != '0')
        outfield_count = limit if not include_gk else max(0, limit - max(1, limit // 6))
        if outfield_count > 0:
            base_players.extend(fetch_block("!= '0'", outfield_count))

        if include_gk:
            gk_count = max(1, limit - len(base_players))
            base_players.extend(fetch_block("= '0'", gk_count))

        return base_players[:limit]
    finally:
        conn.close()


def clone_player_state(base: Dict) -> Dict:
    cloned = {
        'name': base.get('name', 'Regen'),
        'age': int(base.get('age', 22)),
        'registered_position': str(base.get('registered_position', '7')),
        'games_played': 0,
        'goals': 0,
        'assists': 0,
    }
    for k in SKILL_COLUMNS:
        if k in base and base[k] is not None:
            try:
                cloned[k] = int(base[k])
            except Exception:
                cloned[k] = 60
        else:
            cloned[k] = 60
    return cloned


def build_regen_from_seed(seed_player_id: int, original_db_path: str = '/home/anibalgalindro/SQLiteMigration/original.sqlite') -> Dict:
    """Create a synthetic regen starting point from a seed player (original.sqlite).
    Applies a youth penalty and sets seed_player for development orientation.
    """
    conn = sqlite3.connect(original_db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE id = ?", (seed_player_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise RuntimeError(f"Seed player id {seed_player_id} not found in {original_db_path}")

    base = dict(row)
    # Age 16-18
    age = random.randint(16, 18)
    regen = {
        'name': base.get('player_name', f'Regen_{seed_player_id}'),
        'age': age,
        'registered_position': str(base.get('registered_position', '7')),
        'games_played': 0,
        'goals': 0,
        'assists': 0,
        'seed_player': int(seed_player_id),
    }
    # Youth penalty 8-15 points per skill baseline
    penalty = random.randint(8, 15)
    for k in SKILL_COLUMNS:
        bv = base.get(k, 60)
        try:
            bv_i = int(bv)
        except Exception:
            bv_i = 60
        regen[k] = max(1, bv_i - penalty)
    return regen


def compute_weighted_overall(player: Dict, pos_avg_df) -> float:
    try:
        weights = get_position_skill_weights_from_averages(pos_avg_df, str(player.get('registered_position', '7')))
        total_w = 0.0
        total_v = 0.0
        for k, w in weights.items():
            if k in player:
                total_w += max(0.0, float(w))
                total_v += max(0.0, float(w)) * float(player[k])
        if total_w > 0:
            return total_v / total_w
    except Exception:
        pass
    # Fallback: simple average of skills
    vals = [int(player[k]) for k in SKILL_COLUMNS if k in player]
    return sum(vals) / len(vals) if vals else 60.0


def run_season(player: Dict, profile_key: int, trait_key: int, games: int, goals: int, assists: int) -> Dict:
    # Feed performance into player state for this season
    player['games_played'] = int(games)
    player['goals'] = int(goals)
    player['assists'] = int(assists)

    dev = calculate_player_skill_development(player_data=player, development_key=profile_key, trait_key=trait_key)

    # Apply changes to player for next season
    for k, meta in dev['skill_changes'].items():
        player[k] = meta['new']
    player['age'] = int(player.get('age', 25)) + 1

    return dev


def simulate_careers(
    db_path: str,
    base_players: List[Dict],
    careers_per_base: int,
    seasons: int,
    scenarios: List[Tuple[str, int, int, int]],
    seed: int,
    detailed_csv_path: str,
    summary_csv_path: str,
) -> None:
    random.seed(seed)

    pos_avg_df = None
    try:
        pos_avg_df = calculate_position_averages_from_db(db_path)
    except Exception:
        pos_avg_df = None

    # Writers
    os.makedirs(os.path.dirname(detailed_csv_path), exist_ok=True)
    with open(detailed_csv_path, 'w', newline='') as fd, open(summary_csv_path, 'w', newline='') as fs:
        detail_writer = csv.writer(fd)
        summary_writer = csv.writer(fs)

        # Headers
        detail_writer.writerow([
            'scenario', 'run_id', 'base_player_id', 'base_name', 'season', 'age', 'games', 'goals', 'assists',
            'weighted_overall', 'avg_skill', 'total_skill_change', 'final_multiplier',
            'profile_name', 'trait_name'
        ] + [f'skill_{k}' for k in SKILL_COLUMNS])

        summary_writer.writerow([
            'scenario', 'season', 'pool_count', 'pool_weighted_overall_mean', 'pool_weighted_overall_std',
            'pool_avg_skill_mean', 'pool_avg_skill_std'
        ])

        # Storage for per-scenario, per-season pool stats
        per_scn_overalls: Dict[str, Dict[int, List[float]]] = {}
        per_scn_avgs: Dict[str, Dict[int, List[float]]] = {}

        for label, games, goals, assists in scenarios:
            per_scn_overalls[label] = {s: [] for s in range(1, seasons + 1)}
            per_scn_avgs[label] = {s: [] for s in range(1, seasons + 1)}

            run_id = 0
            for base in base_players:
                for _ in range(careers_per_base):
                    run_id += 1
                    player = clone_player_state(base)
                    profile_key, trait_key = generate_complete_development_key()

                    for season_idx in range(1, seasons + 1):
                        dev = run_season(player, profile_key, trait_key, games, goals, assists)

                        weighted_overall = compute_weighted_overall(player, pos_avg_df)
                        avg_skill = sum(int(player[k]) for k in SKILL_COLUMNS) / len(SKILL_COLUMNS)

                        per_scn_overalls[label][season_idx].append(weighted_overall)
                        per_scn_avgs[label][season_idx].append(avg_skill)

                        detail_writer.writerow([
                            label,
                            run_id,
                            base.get('id', ''),
                            base.get('name', ''),
                            season_idx,
                            int(player.get('age', 25)),
                            games,
                            goals,
                            assists,
                            round(weighted_overall, 3),
                            round(avg_skill, 3),
                            int(dev.get('total_skill_change', 0)),
                            round(float(dev.get('final_multiplier', 0.0)), 4),
                            dev.get('profile_name', ''),
                            dev.get('trait_name', ''),
                        ] + [int(player[k]) for k in SKILL_COLUMNS])

        # Write summary
        import math

        for label, _, _, _ in scenarios:
            for season_idx in range(1, seasons + 1):
                ow = per_scn_overalls[label][season_idx]
                av = per_scn_avgs[label][season_idx]
                n = len(ow)
                if n == 0:
                    summary_writer.writerow([label, season_idx, 0, '', '', '', ''])
                    continue
                mean_o = sum(ow) / n
                mean_a = sum(av) / n
                std_o = math.sqrt(sum((x - mean_o) ** 2 for x in ow) / n)
                std_a = math.sqrt(sum((x - mean_a) ** 2 for x in av) / n)
                summary_writer.writerow([label, season_idx, n, round(mean_o, 3), round(std_o, 3), round(mean_a, 3), round(std_a, 3)])


def simulate_seed_cohort(
    db_path: str,
    seed_player_id: int,
    cohort_size: int,
    until_age: int,
    run_scenarios: List[Tuple[str, int, int, int]],
    seed: int,
    detailed_csv_path: str,
    summary_csv_path: str,
) -> None:
    random.seed(seed)

    pos_avg_df = None
    try:
        pos_avg_df = calculate_position_averages_from_db(db_path)
    except Exception:
        pos_avg_df = None

    os.makedirs(os.path.dirname(detailed_csv_path), exist_ok=True)
    with open(detailed_csv_path, 'w', newline='') as fd, open(summary_csv_path, 'w', newline='') as fs:
        detail_writer = csv.writer(fd)
        summary_writer = csv.writer(fs)

        detail_writer.writerow([
            'scenario', 'run_id', 'seed_player_id', 'season', 'age', 'games', 'goals', 'assists',
            'weighted_overall', 'avg_skill', 'total_skill_change', 'final_multiplier',
            'profile_name', 'trait_name'
        ] + [f'skill_{k}' for k in SKILL_COLUMNS])

        summary_writer.writerow([
            'scenario', 'season', 'pool_count', 'pool_weighted_overall_mean', 'pool_weighted_overall_std',
            'pool_avg_skill_mean', 'pool_avg_skill_std'
        ])

        per_scn_overalls: Dict[str, Dict[int, List[float]]] = {}
        per_scn_avgs: Dict[str, Dict[int, List[float]]] = {}

        # Prepare cohort
        cohort = []
        for i in range(cohort_size):
            player = build_regen_from_seed(seed_player_id)
            profile_key, trait_key = generate_complete_development_key()
            label, g, go, a = run_scenarios[i % len(run_scenarios)]
            cohort.append((label, player, profile_key, trait_key, g, go, a))
            if label not in per_scn_overalls:
                per_scn_overalls[label] = {}
                per_scn_avgs[label] = {}

        run_id = 0
        # Simulate until target age
        while True:
            all_done = True
            for idx, (label, player, profile_key, trait_key, games, goals, assists) in enumerate(cohort):
                if int(player.get('age', 25)) >= until_age:
                    continue
                all_done = False
                run_id += 1
                # Determine season index per player: age progression - simple counter by age
                season_idx = (int(player['age']) - int(player['age'])) + 1  # placeholder not used in summaries; we can compute from age post
                dev = run_season(player, profile_key, trait_key, games, goals, assists)

                weighted_overall = compute_weighted_overall(player, pos_avg_df)
                avg_skill = sum(int(player[k]) for k in SKILL_COLUMNS) / len(SKILL_COLUMNS)

                season_key = int(player.get('age', 25))  # age after increment
                per_scn_overalls.setdefault(label, {}).setdefault(season_key, []).append(weighted_overall)
                per_scn_avgs.setdefault(label, {}).setdefault(season_key, []).append(avg_skill)

                detail_writer.writerow([
                    label,
                    run_id,
                    seed_player_id,
                    season_key,
                    int(player.get('age', 25)),
                    games,
                    goals,
                    assists,
                    round(weighted_overall, 3),
                    round(avg_skill, 3),
                    int(dev.get('total_skill_change', 0)),
                    round(float(dev.get('final_multiplier', 0.0)), 4),
                    dev.get('profile_name', ''),
                    dev.get('trait_name', ''),
                ] + [int(player[k]) for k in SKILL_COLUMNS])

            if all_done:
                break

        # Write summary by scenario and age
        import math
        for label, ages in per_scn_overalls.items():
            for age_key in sorted(ages.keys()):
                ow = per_scn_overalls[label][age_key]
                av = per_scn_avgs[label][age_key]
                n = len(ow)
                mean_o = sum(ow) / n
                mean_a = sum(av) / n
                std_o = math.sqrt(sum((x - mean_o) ** 2 for x in ow) / n)
                std_a = math.sqrt(sum((x - mean_a) ** 2 for x in av) / n)
                summary_writer.writerow([label, age_key, n, round(mean_o, 3), round(std_o, 3), round(mean_a, 3), round(std_a, 3)])


def main() -> None:
    parser = argparse.ArgumentParser(description='Simulate multi-season player development scenarios and export CSVs.')
    parser.add_argument('--db', default='pes6_league_db.sqlite', help='Path to SQLite DB')
    parser.add_argument('--players', type=int, default=20, help='Number of base players to sample')
    parser.add_argument('--careers-per-base', type=int, default=5, help='Regenerated careers per base player')
    parser.add_argument('--seasons', type=int, default=5, help='Number of seasons to simulate')
    parser.add_argument('--games', type=int, default=30, help='Games per season (custom scenario)')
    parser.add_argument('--goals', type=int, default=10, help='Goals per season (custom scenario)')
    parser.add_argument('--assists', type=int, default=8, help='Assists per season (custom scenario)')
    parser.add_argument('--presets', action='store_true', help='Run three presets: low, medium, great')
    parser.add_argument('--seed-player', type=int, help='Seed player id from original.sqlite to build a regen cohort')
    parser.add_argument('--cohort-size', type=int, default=5, help='Number of regens in the seed cohort')
    parser.add_argument('--until-age', type=int, default=35, help='Simulate until this age (seed cohort mode)')
    parser.add_argument('--include-gk', action='store_true', help='Include goalkeepers in base sample')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    parser.add_argument('--outdir', default='analysis', help='Output directory for CSVs')

    args = parser.parse_args()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    detailed_csv = os.path.join(args.outdir, f'development_details_{timestamp}.csv')
    summary_csv = os.path.join(args.outdir, f'development_summary_{timestamp}.csv')

    if args.seed_player:
        # Seed cohort mode
        if args.presets:
            run_scenarios = [
                ('zero', 0, 0, 0),
                ('low', 12, 1, 1),
                ('medium', 26, 6, 5),
                ('great', 35, 15, 15),
                ('starter', 34, 2, 4),
                ('bench', 8, 0, 0),
            ]
        else:
            run_scenarios = [('custom', args.games, args.goals, args.assists)]

        simulate_seed_cohort(
            db_path=args.db,
            seed_player_id=args.seed_player,
            cohort_size=args.cohort_size,
            until_age=args.until_age,
            run_scenarios=run_scenarios,
            seed=args.seed,
            detailed_csv_path=detailed_csv,
            summary_csv_path=summary_csv,
        )
    else:
        # Baseline multi-scenario mode
        base_players = read_base_players(args.db, args.players, args.include_gk)
        if args.presets:
            scenarios = [
                ('zero', 0, 0, 0),
                ('low', 12, 1, 1),
                ('medium', 26, 6, 5),
                ('great', 35, 15, 15),
            ]
        else:
            scenarios = [('custom', args.games, args.goals, args.assists)]

        simulate_careers(
            db_path=args.db,
            base_players=base_players,
            careers_per_base=args.careers_per_base,
            seasons=args.seasons,
            scenarios=scenarios,
            seed=args.seed,
            detailed_csv_path=detailed_csv,
            summary_csv_path=summary_csv,
        )

    print(f'Wrote detailed results to: {detailed_csv}')
    print(f'Wrote summary to:       {summary_csv}')


if __name__ == '__main__':
    main()


