def generate_initial_offer(player_to_sell, bidding_club_squad):
    sold_player_mv = player_to_sell.get('Market Value', 0)
    target_offer_value = sold_player_mv * random.uniform(0.25, 0.75)
    if random.random() < 0.3 and not bidding_club_squad.empty:
        suitable_exchange = bidding_club_squad[bidding_club_squad['Market Value'] < target_offer_value]
        if not suitable_exchange.empty:
            exchange_player = suitable_exchange.sample(1).iloc[0]
            cash_component = max(0, target_offer_value - exchange_player.get('Market Value', 0))
            return {'cash': cash_component, 'player_swap': exchange_player, 'loan': None}
    return {'cash': target_offer_value, 'player_swap': None, 'loan': None}

def generate_counter_offer(current_offer, player_to_sell, bidding_club_squad):
    current_cash = current_offer.get('cash', 0)
    swap_player = current_offer.get('player_swap')
    swap_player_mv = swap_player.get('Market Value', 0) if swap_player is not None else 0
    current_total_value = current_cash + swap_player_mv
    new_total_value = current_total_value * (1 + random.uniform(0.05, 0.15))
    offer_type = random.choices(['cash', 'player_swap', 'loan'], weights=[0.55, 0.3, 0.15], k=1)[0]
    
    if offer_type == 'cash':
        print(f"\nThey have improved their cash offer!")
        return {'cash': new_total_value, 'player_swap': None, 'loan': None}
    elif offer_type == 'player_swap' and not bidding_club_squad.empty:
        suitable_exchange = bidding_club_squad[bidding_club_squad['Market Value'] < new_total_value]
        if not suitable_exchange.empty:
            exchange_player = suitable_exchange.sample(1).iloc[0]
            exchange_name = exchange_player.get('NAME', 'N/A'); exchange_mv = exchange_player.get('Market Value', 0)
            cash_component = max(0, new_total_value - exchange_mv)
            print(f"\nAs a counter-offer, they are now offering {exchange_name} (MV: {exchange_mv:,.0f}) plus cash!")
            return {'cash': cash_component, 'player_swap': exchange_player, 'loan': current_offer.get('loan')}
    elif offer_type == 'loan' and not bidding_club_squad.empty and current_offer.get('loan') is None:
        salary_out = player_to_sell.get('Salary', 0)
        salary_in = swap_player.get('Salary', 0) if swap_player is not None else 0
        if salary_out > (salary_in + 1000000):
            loan_candidates = bidding_club_squad[bidding_club_squad['AGE'] <= 24]
            if loan_candidates.empty: loan_candidates = bidding_club_squad
            loan_player = loan_candidates.sample(1).iloc[0]
            loan_name = loan_player.get('NAME', 'N/A'); loan_salary = loan_player.get('Salary', 0)
            print(f"\nTo help with wages, they also offer to send {loan_name} (Salary: {loan_salary:,.0f}) to you on a fully paid loan!")
            return {'cash': current_cash, 'player_swap': swap_player, 'loan': loan_player}
    
    print(f"\nThey have improved their cash offer!") # Fallback
    return {'cash': new_total_value, 'player_swap': None, 'loan': None}

def run_sell_player(routine1_output_path, id_col_csv, club_team_col_csv):
    print(f"Starting Player Seller using: {routine1_output_path}")
    if not os.path.exists(routine1_output_path): print(f"Error: Input file '{routine1_output_path}' not found. Run R1 first."); return
    df = load_csv_for_utility(routine1_output_path)
    if df is None or df.empty: print("Failed to load data for Player Seller."); return
    df.columns = [' '.join(str(c).split()) for c in df.columns]
    id_col_cleaned = ' '.join(id_col_csv.split()); club_team_col_cleaned = ' '.join(club_team_col_csv.split())
    if id_col_cleaned not in df.columns or club_team_col_cleaned not in df.columns: print(f"Error: Essential columns missing."); return
    df[id_col_cleaned] = df[id_col_cleaned].astype(str)
    
    top_clubs = ['A.C. Milan', 'Ajax', 'Arsenal', 'CSKA Moskva', 'F.C. Barcelona', 'Inter', 'Juventus', 'Manchester City', 'Manchester United', 'Newcastle United', 'PSV Eindhoven', 'SBV Excelsior', 'Udinese', 'West Ham United', 'Valencia C.F.', 'Olympique Lyonnais']
    all_clubs = df[club_team_col_cleaned].dropna().unique().tolist()
    other_clubs = [club for club in all_clubs if club not in top_clubs and club != 'No Club']
    if not other_clubs: print("Error: No 'other' clubs available to make offers."); return

    while True:
        player_to_sell_id = input("\nWhich player do you want to sell? (Enter player ID, or 'back'): ").strip()
        if player_to_sell_id.lower() == 'back': break
        player_to_sell_series = df[df[id_col_cleaned] == player_to_sell_id]
        if player_to_sell_series.empty: print(f"Error: Player with ID '{player_to_sell_id}' not found."); continue
        player_to_sell = player_to_sell_series.iloc[0]
        player_name = player_to_sell.get('NAME', 'N/A'); player_mv = player_to_sell.get('Market Value', 0)
        print(f"\nPutting {player_name} (MV: {player_mv:,.0f}) on the market...")
        time.sleep(1)

        new_club_interest_prob = 1.0; bidding_clubs_tried = []; deal_done = False
        
        while True: 
            if random.random() > new_club_interest_prob and len(bidding_clubs_tried) > 0:
                print("\nNo other clubs have shown interest at this time."); break
            
            available_bidders = [c for c in other_clubs if c not in bidding_clubs_tried]
            if not available_bidders: print("\nNo more clubs available to make an offer."); break
            
            bidding_club_name = random.choice(available_bidders); bidding_clubs_tried.append(bidding_club_name)
            bidding_club_squad = df[df[club_team_col_cleaned] == bidding_club_name]
            negotiation_prob = 0.75
            current_offer = generate_initial_offer(player_to_sell, bidding_club_squad)
            print(f"\n... News coming in ...\n{bidding_club_name} is interested in {player_name}.")

            while True:
                cash_val = current_offer.get('cash', 0); swap_player = current_offer.get('player_swap'); loan_player = current_offer.get('loan')
                swap_player_mv = swap_player.get('Market Value', 0) if swap_player is not None else 0
                total_value = cash_val + swap_player_mv
                print("\n" + "="*40); print(f"Negotiating with: {bidding_club_name}")
                print(f"CURRENT OFFER (Total Value: {total_value:,.0f}):")
                print(f"  Cash: {cash_val:,.0f}")
                if swap_player is not None: print(f"  + Player: {swap_player['NAME']} (MV: {swap_player_mv:,.0f})")
                if loan_player is not None: print(f"  + Player on Loan: {loan_player['NAME']}")
                print("="*40)
                
                action = input("Your decision? (1: Accept, 2: Negotiate, 3: Reject & Walk Away): ").strip()
                if action == '1': print(f"\n✅ DEAL! {player_name} sold to {bidding_club_name}."); deal_done = True; break
                elif action == '2':
                    if random.random() < negotiation_prob:
                        print("...Their representative is considering a new proposal..."); time.sleep(1.5)
                        current_offer = generate_counter_offer(current_offer, player_to_sell, bidding_club_squad)
                        negotiation_prob -= random.uniform(0.05, 0.15)
                    else: print("\nThey've walked away from negotiations!"); break
                elif action == '3': print("You have walked away."); break
                else: print("Invalid choice.")
            
            if deal_done: break 
            new_club_interest_prob *= (1 - random.uniform(0.15, 0.25))
            if new_club_interest_prob > 0.01 : print(f"Probability of new club interest is now: {new_club_interest_prob:.0%}")
