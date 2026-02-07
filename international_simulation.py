"""
International game simulation that works with player lists directly
(no database queries, so fake players never touch the database)
"""
import random

def simulate_international_game_with_players(home_players, away_players, fake_player_ids=None, for_international=False):
    """
    Simulate an international game using player lists directly.
    Works exactly like simulate_cpu_game but accepts player lists instead of querying by club_id.
    This allows fake players to exist only in memory.
    
    Args:
        home_players: List of player dicts for home team
        away_players: List of player dicts for away team
        fake_player_ids: Set/list of fake player IDs to exclude from MVP selection
        for_international: If True, international rules: goals + assists only. No YC/RC, no injuries,
                          no penalty/hail-mary/free-kick. Those are inter-leagues only.
    """
    if fake_player_ids is None:
        fake_player_ids = set()
    else:
        fake_player_ids = set(fake_player_ids)  # Convert to set for fast lookup
    # Helper function to convert registered_position from TEXT to int
    def get_pos_int(p):
        """Convert registered_position (TEXT) to int for comparison"""
        pos = p.get('registered_position')
        try:
            return int(pos) if pos is not None else -1
        except (ValueError, TypeError):
            return -1
    
    def select_starting_11(players):
        """Select exactly 11 players, ensuring 1 GK"""
        if not players or len(players) < 11:
            return players[:11] if players else []
        
        # Group by position
        gks = sorted([p for p in players if get_pos_int(p) == 0], 
                    key=lambda x: x.get('overall', 0), reverse=True)
        side_backs = sorted([p for p in players if get_pos_int(p) in [4, 6]], 
                           key=lambda x: x.get('overall', 0), reverse=True)
        centre_backs = sorted([p for p in players if get_pos_int(p) in [2, 3]], 
                             key=lambda x: x.get('overall', 0), reverse=True)
        centre_mids = sorted([p for p in players if get_pos_int(p) in [5, 7, 9]], 
                            key=lambda x: x.get('overall', 0), reverse=True)  # DMF (5), CMF (7), AMF (9)
        side_mids = sorted([p for p in players if get_pos_int(p) in [8, 10]], 
                          key=lambda x: x.get('overall', 0), reverse=True)
        forwards = sorted([p for p in players if get_pos_int(p) in [11, 12]], 
                         key=lambda x: x.get('overall', 0), reverse=True)
        
        lineup = []
        if gks:
            lineup.append(gks[0])
        for sb in side_backs[:2]:
            lineup.append(sb)
        for cb in centre_backs[:2]:
            lineup.append(cb)
        for cm in centre_mids[:2]:
            lineup.append(cm)
        for sm in side_mids[:2]:
            lineup.append(sm)
        for fwd in forwards[:2]:
            lineup.append(fwd)
        
        # Fill remaining slots
        used_ids = {p.get('id') for p in lineup}
        available = sorted([p for p in players if p.get('id') not in used_ids 
                          and get_pos_int(p) != 0], 
                         key=lambda x: x.get('overall', 0), reverse=True)
        needed = 11 - len(lineup)
        for p in available[:needed]:
            lineup.append(p)
        
        # Ensure exactly 1 GK
        gks_in_lineup = [p for p in lineup if get_pos_int(p) == 0]
        if len(gks_in_lineup) > 1:
            first_gk = gks_in_lineup[0]
            non_gks = [p for p in lineup if get_pos_int(p) != 0]
            lineup = [first_gk] + non_gks
        elif len(gks_in_lineup) == 0:
            # No GK - add best available
            available_gks = [p for p in players if get_pos_int(p) == 0]
            if available_gks:
                available_gks.sort(key=lambda x: x.get('overall', 0), reverse=True)
                if len(lineup) >= 11:
                    lineup = lineup[:-1]
                lineup = [available_gks[0]] + lineup
        
        return lineup[:11]
    
    # Select starting 11 for both teams
    home_lineup = select_starting_11(home_players)
    away_lineup = select_starting_11(away_players)
    
    # Make substitutions (2-3 per team)
    def make_substitutions(starting_11, all_players):
        """Make 2-3 substitutions"""
        if len(all_players) <= 11:
            return starting_11, []
        
        num_subs = random.randint(2, 3)
        used_ids = {p.get('id') for p in starting_11}
        available_subs = [p for p in all_players if p.get('id') not in used_ids and get_pos_int(p) != 0]
        
        if len(available_subs) < num_subs:
            num_subs = len(available_subs)
        
        if num_subs == 0:
            return starting_11, []
        
        non_gk_starters = [p for p in starting_11 if get_pos_int(p) != 0]
        if len(non_gk_starters) < num_subs:
            return starting_11, []
        
        players_to_sub_out = random.sample(non_gk_starters, num_subs)
        subs_made = []
        final_lineup = starting_11.copy()
        
        for player_out in players_to_sub_out:
            if not available_subs:
                break
            player_out_pos = get_pos_int(player_out)
            similar_subs = [p for p in available_subs if get_pos_int(p) == player_out_pos]
            
            if similar_subs:
                sub_in = random.choice(similar_subs)
            else:
                sub_in = random.choice(available_subs)
            
            for i, p in enumerate(final_lineup):
                if p.get('id') == player_out.get('id'):
                    final_lineup[i] = sub_in
                    break
            
            subs_made.append({
                'out': player_out,
                'in': sub_in,
                'minute': random.randint(60, 85)
            })
            available_subs.remove(sub_in)
        
        return final_lineup, subs_made
    
    home_lineup_final, home_subs = make_substitutions(home_lineup, home_players)
    away_lineup_final, away_subs = make_substitutions(away_lineup, away_players)
    
    # Ensure still only 1 GK after substitutions
    def ensure_one_gk(lineup):
        gks = [p for p in lineup if get_pos_int(p) == 0]
        non_gks = [p for p in lineup if get_pos_int(p) != 0]
        if len(gks) > 1:
            return [gks[0]] + non_gks
        elif len(gks) == 1:
            return lineup
        else:
            return lineup
    
    home_lineup_final = ensure_one_gk(home_lineup_final)
    away_lineup_final = ensure_one_gk(away_lineup_final)
    
    # Calculate minutes played for ALL players (starters and subs)
    def calculate_minutes(starting_lineup, final_lineup, subs_made):
        minutes = {}
        
        # Initialize ALL starters first (they all play at least some minutes)
        starter_ids = {p.get('id') for p in starting_lineup}
        subbed_out_ids = {sub['out'].get('id') for sub in subs_made}
        
        # All starters who weren't subbed out play 90 minutes
        for p in starting_lineup:
            player_id = p.get('id')
            if player_id not in subbed_out_ids:
                minutes[player_id] = 90
        
        # Handle substitutions - update minutes for subbed-out and subbed-in players
        for sub in subs_made:
            player_out_id = sub['out'].get('id')
            player_in_id = sub['in'].get('id')
            sub_minute = sub['minute']
            minutes[player_out_id] = sub_minute  # Player subbed out
            minutes[player_in_id] = 90 - sub_minute  # Player subbed in
        
        # Ensure all players in final lineup have minutes (in case they weren't in starting lineup)
        for p in final_lineup:
            player_id = p.get('id')
            if player_id not in minutes:
                # This shouldn't happen, but if it does, give them 0 minutes
                minutes[player_id] = 0
        
        # CRITICAL: Ensure ALL starters are in minutes dict (even if they somehow weren't added)
        for p in starting_lineup:
            player_id = p.get('id')
            if player_id not in minutes:
                # This should never happen, but ensure all starters are tracked
                minutes[player_id] = 90 if player_id not in subbed_out_ids else 0
        
        return minutes
    
    home_minutes = calculate_minutes(home_lineup, home_lineup_final, home_subs)
    away_minutes = calculate_minutes(away_lineup, away_lineup_final, away_subs)
    
    # Calculate strength and scores
    home_strength = sum(p['overall'] for p in home_lineup) / len(home_lineup) if home_lineup else 50
    away_strength = sum(p['overall'] for p in away_lineup) / len(away_lineup) if away_lineup else 50
    strength_diff = (home_strength - away_strength) / 10
    home_expected = max(0.5, 1.5 + strength_diff * 1.75 + 0.3)
    away_expected = max(0.5, 1.5 - strength_diff * 1.75)
    home_score = max(0, min(6, int(random.gauss(home_expected, 0.9))))
    away_score = max(0, min(6, int(random.gauss(away_expected, 0.9))))
    
    # Cards, injuries, penalties, hail-mary, free-kicks: INTER-LEAGUES ONLY.
    # International games: goals + assists only. No YC/RC, no injuries, no special events.
    home_events = []
    away_events = []
    penalty_events = []
    hail_mary_events = []
    free_kick_events = []
    
    if not for_international:
        # Inter-leagues only: cards, injuries, red-card score reduction, special events
        def _gen_cards_injuries(lineup_final, minutes_dict, team_id, team_strength, is_weaker):
            ev = []
            eligible = [p for p in lineup_final if minutes_dict.get(p.get('id'), 0) > 0]
            if not eligible:
                return ev
            base_y = 0.12 + (max(0, min(1, (50 - team_strength) / 30)) * 0.03) if is_weaker else 0.10 - (max(0, min(1, (team_strength - 50) / 30)) * 0.02)
            for p in eligible:
                if random.random() < base_y:
                    ev.append({'type': 'yellow_card', 'minute': random.randint(1, 90), 'player_id': p.get('id'), 'player_name': p.get('player_name'), 'team_id': team_id})
            if random.random() < 0.10:
                rp = random.choice(eligible)
                m = random.randint(1, 90)
                ev.append({'type': 'red_card', 'minute': m, 'player_id': rp.get('id'), 'player_name': rp.get('player_name'), 'team_id': team_id})
                if not any(e['type'] == 'yellow_card' and e['player_id'] == rp.get('id') for e in ev):
                    ev.append({'type': 'yellow_card', 'minute': m, 'player_id': rp.get('id'), 'player_name': rp.get('player_name'), 'team_id': team_id})
            ni = random.choices([0, 1, 2], weights=[80, 15, 5])[0]
            if ni > 0:
                for p in random.sample(eligible, min(ni, len(eligible))):
                    ev.append({'type': 'injury', 'minute': random.randint(1, 90), 'player_id': p.get('id'), 'player_name': p.get('player_name'), 'team_id': team_id, 'weeks': random.randint(1, 8)})
            return ev
        is_hw = home_strength < away_strength
        is_aw = away_strength < home_strength
        home_events = _gen_cards_injuries(home_lineup_final, home_minutes, 'home', home_strength, is_hw)
        away_events = _gen_cards_injuries(away_lineup_final, away_minutes, 'away', away_strength, is_aw)
        for _ in range(sum(1 for e in home_events if e['type'] == 'red_card')):
            home_score = max(0, home_score - 1)
        for _ in range(sum(1 for e in away_events if e['type'] == 'red_card')):
            away_score = max(0, away_score - 1)
        num_penalties = random.choices([0, 1, 2], weights=[85, 12, 3])[0]
        for _ in range(num_penalties):
            penalty_events.append({'type': 'penalty', 'minute': random.randint(1, 90), 'team': 'home' if random.random() < 0.5 else 'away', 'needs_user_input': False})
        if home_score < away_score and away_score - home_score == 1 and random.random() < 0.15:
            hail_mary_events.append({'type': 'hail_mary_corner', 'minute': random.randint(85, 90), 'team': 'home', 'needs_user_input': False})
        elif away_score < home_score and home_score - away_score == 1 and random.random() < 0.15:
            hail_mary_events.append({'type': 'hail_mary_corner', 'minute': random.randint(85, 90), 'team': 'away', 'needs_user_input': False})
        elif home_score == away_score and random.random() < 0.10:
            hail_mary_events.append({'type': 'hail_mary_corner', 'minute': random.randint(85, 90), 'team': 'home' if random.random() < 0.5 else 'away', 'needs_user_input': False})
        if random.random() < 0.05:
            free_kick_events.append({'type': 'dangerous_free_kick', 'minute': random.randint(1, 90), 'team': 'home' if random.random() < 0.5 else 'away', 'needs_user_input': False})
    
    # Player stats
    player_stats = []
    stats_dict = {}
    
    def get_stat(player_id, player_name, team_id):
        if player_id not in stats_dict:
            stats_dict[player_id] = {
                'player_id': player_id,
                'player_name': player_name,
                'team_id': team_id,
                'goals': 0,
                'assists': 0,
                'minutes_played': 90,
                'is_starter': 1,
                'yellow_cards': 0,
                'red_cards': 0,
                'injuries': 0
            }
            player_stats.append(stats_dict[player_id])
        return stats_dict[player_id]
    
    # Position probabilities
    def score_prob(pos):
        if pos == 0: return 0.0
        elif pos in [2, 3, 4, 6]: return 0.10
        elif pos in [5, 7, 8]: return 0.15
        elif pos in [10]: return 0.20
        elif pos in [11, 12]: return 0.55
        return 0.10
    
    def assist_prob(pos):
        if pos == 0: return 0.01
        elif pos in [2, 3, 4, 6]: return 0.14
        elif pos in [5, 7, 8]: return 0.35
        elif pos in [10]: return 0.25
        elif pos in [11, 12]: return 0.25
        return 0.14
    
    # Distribute goals AND assists together (prevents self-assists and ensures assists <= goals)
    # Track scorers so we can exclude them from assist candidates
    home_goal_scorers = []
    non_gk_home = [p for p in home_lineup_final if get_pos_int(p) != 0]
    
    for _ in range(home_score):
        if not non_gk_home:
            continue
        
        # Calculate weights with:
        # 1. Position probability
        # 2. Overall rating SQUARED (favors higher-rated players more)
        # 3. Minutes played factor (subs less likely to score)
        weights = []
        for p in non_gk_home:
            player_id = p.get('id')
            minutes = home_minutes.get(player_id, 90)
            
            # Minutes factor: full starters (90 min) = 1.0, subs get reduced weight
            # Subs typically play 10-30 minutes, so they get 0.11-0.33x weight
            minutes_factor = minutes / 90.0
            
            # Overall squared to favor better players (85 overall = 7225, 70 overall = 4900)
            overall_squared = (p['overall'] ** 2) / 10000  # Normalize to reasonable range
            
            weight = score_prob(get_pos_int(p)) * overall_squared * minutes_factor
            weights.append((p, weight))
        
        total = sum(w for _, w in weights)
        if total > 0:
            r = random.random() * total
            cumsum = 0
            scorer = None
            for p, w in weights:
                cumsum += w
                if r <= cumsum:
                    scorer = p
                    break
            
            if scorer:
                stat = get_stat(scorer['id'], scorer['player_name'], 'home')
                stat['goals'] += 1
                home_goal_scorers.append(scorer['id'])
                
                # Assign assist (60% of goals have assists, exclude the scorer)
                if random.random() < 0.60:
                    assist_candidates = [p for p in non_gk_home if p['id'] != scorer['id']]
                    if assist_candidates:
                        # Same weighting system for assists
                        assist_weights = []
                        for p in assist_candidates:
                            player_id = p.get('id')
                            minutes = home_minutes.get(player_id, 90)
                            minutes_factor = minutes / 90.0
                            overall_squared = (p['overall'] ** 2) / 10000
                            weight = assist_prob(get_pos_int(p)) * overall_squared * minutes_factor
                            assist_weights.append((p, weight))
                        
                        total_assist = sum(w for _, w in assist_weights)
                        if total_assist > 0:
                            r = random.random() * total_assist
                            cumsum = 0
                            for p, w in assist_weights:
                                cumsum += w
                                if r <= cumsum:
                                    stat = get_stat(p['id'], p['player_name'], 'home')
                                    stat['assists'] += 1
                                    break
    
    # Distribute away goals AND assists
    away_goal_scorers = []
    non_gk_away = [p for p in away_lineup_final if get_pos_int(p) != 0]
    
    for _ in range(away_score):
        if not non_gk_away:
            continue
        
        # Calculate weights with minutes factor and squared overall
        weights = []
        for p in non_gk_away:
            player_id = p.get('id')
            minutes = away_minutes.get(player_id, 90)
            minutes_factor = minutes / 90.0
            overall_squared = (p['overall'] ** 2) / 10000
            weight = score_prob(get_pos_int(p)) * overall_squared * minutes_factor
            weights.append((p, weight))
        
        total = sum(w for _, w in weights)
        if total > 0:
            r = random.random() * total
            cumsum = 0
            scorer = None
            for p, w in weights:
                cumsum += w
                if r <= cumsum:
                    scorer = p
                    break
            
            if scorer:
                stat = get_stat(scorer['id'], scorer['player_name'], 'away')
                stat['goals'] += 1
                away_goal_scorers.append(scorer['id'])
                
                # Assign assist (60% of goals have assists, exclude the scorer)
                if random.random() < 0.60:
                    assist_candidates = [p for p in non_gk_away if p['id'] != scorer['id']]
                    if assist_candidates:
                        # Same weighting system for assists
                        assist_weights = []
                        for p in assist_candidates:
                            player_id = p.get('id')
                            minutes = away_minutes.get(player_id, 90)
                            minutes_factor = minutes / 90.0
                            overall_squared = (p['overall'] ** 2) / 10000
                            weight = assist_prob(get_pos_int(p)) * overall_squared * minutes_factor
                            assist_weights.append((p, weight))
                        
                        total_assist = sum(w for _, w in assist_weights)
                        if total_assist > 0:
                            r = random.random() * total_assist
                            cumsum = 0
                            for p, w in assist_weights:
                                cumsum += w
                                if r <= cumsum:
                                    stat = get_stat(p['id'], p['player_name'], 'away')
                                    stat['assists'] += 1
                                    break
    
    # Create stats for ALL players who played (not just scorers/assisters)
    # CRITICAL: Add ALL starters first (even if they were subbed out)
    # This ensures all 11 (or however many) starters are in stats_dict
    home_starter_ids = {p.get('id') for p in home_lineup}
    away_starter_ids = {p.get('id') for p in away_lineup}
    
    # Add ALL home starters to stats_dict first
    # CRITICAL: Always ensure is_starter=1, even if player already has stats from goals/assists
    for p in home_lineup:
        player_id = p.get('id')
        if player_id not in stats_dict:
            stat = get_stat(player_id, p['player_name'], 'home')
        # CRITICAL: Always set is_starter=1 for starters, even if they already have stats
        stats_dict[player_id]['is_starter'] = 1
    
    # Add ALL away starters to stats_dict first
    # CRITICAL: Always ensure is_starter=1, even if player already has stats from goals/assists
    for p in away_lineup:
        player_id = p.get('id')
        if player_id not in stats_dict:
            stat = get_stat(player_id, p['player_name'], 'away')
        # CRITICAL: Always set is_starter=1 for starters, even if they already have stats
        stats_dict[player_id]['is_starter'] = 1
    
    # Add all substitutes who came on (they're in final lineup but not starting lineup)
    for p in home_lineup_final:
        player_id = p.get('id')
        if player_id not in stats_dict:
            stat = get_stat(player_id, p['player_name'], 'home')
            stat['is_starter'] = 0  # Explicitly set as substitute
    
    for p in away_lineup_final:
        player_id = p.get('id')
        if player_id not in stats_dict:
            stat = get_stat(player_id, p['player_name'], 'away')
            stat['is_starter'] = 0  # Explicitly set as substitute
    
    # Now update minutes and ensure is_starter is correct for all players
    for player_id, minutes in home_minutes.items():
        if player_id in stats_dict:
            stats_dict[player_id]['minutes_played'] = minutes
            # Ensure is_starter is set correctly (1 if in home_starter_ids, 0 otherwise)
            stats_dict[player_id]['is_starter'] = 1 if player_id in home_starter_ids else 0
    
    for player_id, minutes in away_minutes.items():
        if player_id in stats_dict:
            stats_dict[player_id]['minutes_played'] = minutes
            # Ensure is_starter is set correctly (1 if in away_starter_ids, 0 otherwise)
            stats_dict[player_id]['is_starter'] = 1 if player_id in away_starter_ids else 0
    
    # CRITICAL: Final pass - ensure ALL starters have stats entries with correct is_starter flag
    # This catches any starters that might have been missed
    for p in home_lineup:
        player_id = p.get('id')
        if player_id not in stats_dict:
            stat = get_stat(player_id, p['player_name'], 'home')
            stat['is_starter'] = 1
            stat['minutes_played'] = home_minutes.get(player_id, 90)
        else:
            # Double-check: ensure is_starter is 1 (in case it was overwritten)
            stats_dict[player_id]['is_starter'] = 1
    
    for p in away_lineup:
        player_id = p.get('id')
        if player_id not in stats_dict:
            stat = get_stat(player_id, p['player_name'], 'away')
            stat['is_starter'] = 1
            stat['minutes_played'] = away_minutes.get(player_id, 90)
        else:
            # Double-check: ensure is_starter is 1 (in case it was overwritten)
            stats_dict[player_id]['is_starter'] = 1
    
    # Select MVP (best performing player, not GK)
    # CRITICAL: Only consider players who actually played in THIS game (from home or away teams)
    mvp_player_id = None
    
    # Build sets of valid player IDs for this game (home and away)
    home_player_ids = {p.get('id') for p in home_lineup_final + [sub['out'] for sub in home_subs]}
    away_player_ids = {p.get('id') for p in away_lineup_final + [sub['out'] for sub in away_subs]}
    all_valid_player_ids = home_player_ids | away_player_ids
    
    # Get player objects for all players who played to check positions
    players_who_played = {}
    for p in home_lineup_final + away_lineup_final:
        players_who_played[p.get('id')] = p
    # Also include subbed-out players
    for sub in home_subs + away_subs:
        players_who_played[sub['out'].get('id')] = sub['out']
    
    if player_stats:
        # Determine winning team (if any)
        winning_team = None
        if home_score > away_score:
            winning_team = 'home'
        elif away_score > home_score:
            winning_team = 'away'
        
        # Filter to only non-GK players who actually played in THIS game
        # CRITICAL: Verify player_id is in all_valid_player_ids AND is not a fake player
        non_gk_stats = []
        for stat in player_stats:
            player_id = stat.get('player_id')
            # CRITICAL: Only consider players who are actually in this game
            if player_id not in all_valid_player_ids:
                continue
            # CRITICAL: Exclude fake players from MVP selection
            if player_id in fake_player_ids:
                continue
            if player_id in players_who_played:
                player_obj = players_who_played[player_id]
                if get_pos_int(player_obj) != 0:  # Not a goalkeeper
                    non_gk_stats.append(stat)
        
        if non_gk_stats:
            # Prefer MVP from winning team if there's a winner
            if winning_team:
                winning_stats = [s for s in non_gk_stats if s.get('team_id') == winning_team]
                if winning_stats:
                    mvp = max(winning_stats, key=lambda s: s['goals'] * 3 + s['assists'] * 2 + random.random())
                    mvp_player_id = mvp['player_id']
                else:
                    # No winning team contributors, select from all
                    mvp = max(non_gk_stats, key=lambda s: s['goals'] * 3 + s['assists'] * 2 + random.random())
                    mvp_player_id = mvp['player_id']
            else:
                # Draw - select best performer
                mvp = max(non_gk_stats, key=lambda s: s['goals'] * 3 + s['assists'] * 2 + random.random())
                mvp_player_id = mvp['player_id']
        
        # Fallback: best non-GK player from winning team (or any team if draw)
        # CRITICAL: Exclude fake players from fallback selection
        if not mvp_player_id:
            if winning_team == 'home':
                non_gk_players = [p for p in home_lineup_final 
                                if get_pos_int(p) != 0 and p.get('id') not in fake_player_ids]
            elif winning_team == 'away':
                non_gk_players = [p for p in away_lineup_final 
                                if get_pos_int(p) != 0 and p.get('id') not in fake_player_ids]
            else:
                # Draw - select from either team
                non_gk_players = [p for p in (home_lineup_final + away_lineup_final) 
                                if get_pos_int(p) != 0 and p.get('id') not in fake_player_ids]
            
            if non_gk_players:
                mvp_player_id = max(non_gk_players, key=lambda x: x.get('overall', 0)).get('id')
        
        # Final fallback: any non-GK player from the game (excluding fake players)
        if not mvp_player_id:
            all_non_gk = [p for p in (home_lineup_final + away_lineup_final) 
                          if get_pos_int(p) != 0 and p.get('id') not in fake_player_ids]
            if all_non_gk:
                mvp_player_id = all_non_gk[0].get('id')
            else:
                # Only fake players available - set MVP to None
                mvp_player_id = None
    
    # Update player stats with cards and injuries (inter-leagues only; international has no events)
    for event in home_events + away_events:
        player_id = event['player_id']
        if player_id in stats_dict:
            if event['type'] == 'yellow_card':
                stats_dict[player_id]['yellow_cards'] = stats_dict[player_id].get('yellow_cards', 0) + 1
            elif event['type'] == 'red_card':
                stats_dict[player_id]['red_cards'] = stats_dict[player_id].get('red_cards', 0) + 1
            elif event['type'] == 'injury':
                stats_dict[player_id]['injuries'] = event.get('weeks', 1)
    
    return {
        'home_score': home_score,
        'away_score': away_score,
        'player_stats': player_stats,
        'mvp_player_id': mvp_player_id,
        'events': home_events + away_events,  # Include cards and injuries in events
        'penalty_events': penalty_events,  # Penalties that may need user input
        'hail_mary_events': hail_mary_events,  # Hail-Mary corners that may need user input
        'free_kick_events': free_kick_events  # Dangerous free-kicks that may need user input
    }

