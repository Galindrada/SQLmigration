def generate_cpu_counter_proposal(current_deal, buying_user_squad):
    """Generates a CPU counter-offer, which is a lower total demand, possibly with a player request."""
    current_cash_demand = current_deal.get('cash_paid', 0)
    player_demand = current_deal.get('player_given')
    player_demand_mv = player_demand.get('Market Value', 0) if player_demand is not None else 0
    current_total_demand_value = current_cash_demand + player_demand_mv
    
    # CPU makes a concession, reducing its total demand value by 5-15%
    new_total_demand_value = current_total_demand_value * (1 - random.uniform(0.05, 0.15))
    
    # High chance CPU just lowers the cash price
    if random.random() < 0.7 or buying_user_squad.empty:
        print("\nThey've considered your position and are willing to lower the cash price.")
        return {'cash_paid': new_total_demand_value, 'player_given': None}
    
    # Lesser chance the CPU asks for one of your players to reduce the cash part
    else:
        # CPU looks for a player from your squad with a value less than the new total demand
        suitable_players = buying_user_squad[buying_user_squad['Market Value'] < new_total_demand_value]
        if not suitable_players.empty:
            player_request = suitable_players.sample(1).iloc[0]
            player_request_name = player_request.get('NAME', 'N/A')
            player_request_mv = player_request.get('Market Value', 0)
            new_cash_demand = max(0, new_total_demand_value - player_request_mv)
            print(f"\nThey have a new proposal. They will lower the price if you include {player_request_name} (MV: {player_request_mv:,.0f}) in the deal!")
            return {'cash_paid': new_cash_demand, 'player_given': player_request}

    # Fallback to simple cash reduction
    print("\nThey have considered your position and are willing to lower the cash price.")
    return {'cash_paid': new_total_demand_value, 'player_given': None}

def run_buy_player(routine1_output_path, id_col_csv, club_team_col_csv):
    print(f"Starting 'Buy a Player' module using: {routine1_output_path}")
    if not os.path.exists(routine1_output_path): print(f"Error: Input file '{routine1_output_path}' not found. Run R1 first."); return
    df = load_csv_for_utility(routine1_output_path)
    if df is None or df.empty: print("Failed to load data for 'Buy a Player'."); return
    
    df.columns = [' '.join(str(c).split()) for c in df.columns]
    id_col_cleaned = ' '.join(id_col_csv.split()); club_team_col_cleaned = ' '.join(club_team_col_csv.split())
    if id_col_cleaned not in df.columns or club_team_col_cleaned not in df.columns: print(f"Error: Essential columns missing."); return
    df[id_col_cleaned] = df[id_col_cleaned].astype(str)

    while True:
        target_player_id = input("\nWhich player do you want to buy? (Enter player ID, or 'back'): ").strip()
        if target_player_id.lower() == 'back': break

        target_player_series = df[df[id_col_cleaned] == target_player_id]
        if target_player_series.empty: print(f"Error: Player with ID '{target_player_id}' not found."); continue
        
        target_player = target_player_series.iloc[0]
        target_name = target_player.get('NAME', 'N/A'); target_mv = target_player.get('Market Value', 0)
        selling_club = target_player.get(club_team_col_cleaned, 'N/A')
        
        print("\nWhich user is buying?")
        for key, user_info in USER_TEAMS.items(): print(f"{key}: {user_info['name']} (Manages: {', '.join(user_info['teams'])})")
        
        buyer_choice = input(f"Select the number of the buying user (1-{len(USER_TEAMS)}): ").strip()
        if buyer_choice not in USER_TEAMS: print("Invalid user choice."); continue
        
        buying_user = USER_TEAMS[buyer_choice]
        if selling_club in buying_user['teams']: print(f"Error: You cannot buy a player from one of your own teams ({selling_club})."); continue
        if selling_club == 'No Club': print(f"Error: You can sign free agents, not 'buy' them. This module is for transfers between clubs."); continue

        print(f"\n{buying_user['name']} is attempting to buy {target_name} from {selling_club}...")
        buying_user_squad = df[df[club_team_col_cleaned].isin(buying_user['teams'])]
        
        initial_asking_price = target_mv * random.uniform(1.25, 1.75)
        current_deal = {'cash_paid': initial_asking_price, 'player_given': None}
        negotiation_prob = 0.75
        deal_done = False

        while True:
            cash_demand = current_deal.get('cash_paid', 0); player_demand = current_deal.get('player_given')
            print("\n" + "="*40); print(f"Negotiating for: {target_name} (MV: {target_mv:,.0f})")
            print(f"Selling club ({selling_club}) is demanding:")
            print(f"  Cash Payment: {cash_demand:,.0f}")
            if player_demand is not None:
                player_demand_name = player_demand.get('NAME', 'N/A'); player_demand_mv = player_demand.get('Market Value', 0)
                print(f"  + Your Player: {player_demand_name} (MV: {player_demand_mv:,.0f})")
            print("="*40)

            action = input("Your decision? (1: Accept Demands, 2: Negotiate for a better deal, 3: Walk Away): ").strip()
            if action == '1': print(f"\n✅ DEAL! {target_name} will join {buying_user['name']}'s club."); deal_done = True; break
            elif action == '2':
                if random.random() < negotiation_prob:
                    print("...Their Director of Football is considering your request..."); time.sleep(1.5)
                    current_deal = generate_cpu_counter_proposal(current_deal, buying_user_squad)
                    negotiation_prob -= random.uniform(0.05, 0.15)
                else: print("\nThey are firm on their price and have ended negotiations!"); break
            elif action == '3': print("You have walked away from the negotiation."); break
            else: print("Invalid choice.")
        
        if deal_done: break


