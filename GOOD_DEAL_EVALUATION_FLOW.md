# Good Deal Evaluation - When and How Often It's Applied

## Overview
The "good deal" evaluation is a new acceptance criteria that CPU teams use to evaluate offers on user-listed players. It works alongside the existing sophisticated evaluation system.

## CPU AI Action Flow (trigger_cpu_ai route)

When you trigger CPU AI activity from `tools.html`, here's what happens:

### Step 1: Process ALL User Offers to CPU Teams (100% of offers)
**Function**: `process_user_offers()`
**When**: Runs FIRST, before any other CPU actions
**Frequency**: **100% of pending user offers are evaluated every trigger**

- Evaluates ALL pending offers from users on CPU players
- **NOTE**: This is the OPPOSITE direction - users offering to buy CPU players
- **Good Deal Evaluation**: ❌ **NOT APPLIED HERE** - This is for CPU selling players, not buying
- Uses sophisticated valuation system only (age, contract, team needs, etc.)
- **Example**: If you have 10 user offers pending, ALL 10 are evaluated using sophisticated criteria only

### Step 2: Process Each CPU Team (40% chance per team)
**Function**: `process_cpu_ai_actions()`
**When**: After processing user offers
**Frequency**: Each CPU team has:
- **100% chance** to act if they have < 16 players (urgent need)
- **40% chance** to act if they have ≥ 16 players

### Step 3: CPU Team Action Distribution (if team acts)
**Location**: Lines 2973-3013 in `cpu_ai.py`

When a CPU team decides to act, they choose one action:

| Action | Probability | Code Location | Good Deal Used? | Description |
|--------|-------------|---------------|-----------------|-------------|
| **Buy Listed Player** | 40% | Line 2974 (`action_choice < 0.4`) | ✅ **YES** | CPU directly buys a player from market bazaar listings |
| **Loan Player** | 20% | Line 2982 (`action_choice < 0.6`) | ❌ No | CPU loans a player (loans don't use good deal) |
| **Free Agency** | 25% | Line 2990 (`action_choice < 0.85`) | ❌ No | CPU makes/raises free agency offers |
| **Make Market Offer** | 5% | Line 3013 (`action_choice < 0.9`) | ✅ **YES** | CPU makes an offer on a listed player |
| **List for Sale** | 10% | Line 3020 (`action_choice < 1.0`) | ❌ No | CPU lists their own players for sale |
| **List for Loan** | 10% | (Remaining probability) | ❌ No | CPU lists their own players for loan |

## Where Good Deal Evaluation is Applied

**IMPORTANT**: Good deal evaluation is ONLY applied when CPU is evaluating **user-listed players** (CPU as buyer). It is NOT applied when CPU is selling their own players.

### 1. `buy_listed_player()` - CPU Buying User-Listed Players
**Location**: Lines 1298-1310 in `cpu_ai.py`
**Frequency**: **40% of acting CPU teams** × **only if they find suitable players**
**Player Limit**: **Evaluates up to 40 players** (LIMIT 40, line 1167)
**Action Limit**: **Buys ONLY 1 player** per team per trigger (breaks after first match, line 1311)

**Logic**:
```python
is_good_deal_offer = self.is_good_deal(asking_price, player_data)
if (other_criteria OR is_good_deal_offer):
    # Buy player (only first match)
    break
```

**When it applies**:
- CPU team decides to buy (40% chance)
- CPU queries up to 40 listed players (user_sale + cpu_sale)
- Evaluates all 40 players for good deal criteria
- **BUT only buys the FIRST player that meets criteria** (stops after first purchase)
- If asking price qualifies as good deal, CPU will buy even if other criteria aren't fully met

### 2. `make_cpu_market_bazaar_offer()` - CPU Making Offers on User-Listed Players
**Location**: Lines 2329-2402 in `cpu_ai.py`
**Frequency**: **5% of acting CPU teams** × **only if they find suitable players**
**Player Limit**: **Evaluates up to 50 players** (LIMIT 50, line 2216)
**Action Limit**: **Makes ONLY 1 offer** per team per trigger (selects one from top deals, lines 2419-2426)

**Logic**:
```python
if is_user_listed:
    is_good_deal_offer = self.is_good_deal(asking_price, player_data)
    if is_good_deal_offer:
        deal_score = 150  # High priority (prioritizes good deals)
```

**Selection Process** (lines 2419-2426):
- Sorts all evaluated players by deal_score (good deals get score 150)
- **60% chance** to pick from top 3 deals
- **30% chance** to pick from top 5 deals  
- **10% chance** to pick from top 10 deals
- Makes offer on the selected player

**When it applies**:
- CPU team decides to make market offers (5% chance)
- CPU queries up to 50 listed players (user_sale + cpu_sale + cpu_loan)
- Evaluates all 50 players for good deal criteria
- Good deals get HIGH priority (deal_score = 150)
- **BUT only makes 1 offer** (selected from top deals with weighted probability)

## Summary: Good Deal Evaluation Frequency

### Per CPU AI Trigger:

1. **User Offers to CPU Players** (`process_user_offers()`): 
   - **100% of pending offers** are evaluated
   - Example: 10 offers = 10 evaluations
   - **No limit** - all offers are processed
   - **Good Deal**: ❌ **NOT APPLIED** - This is CPU selling, not buying

2. **CPU Buying User-Listed Players**:
   - **40% of CPU teams** attempt to buy (if they act)
   - **Evaluates up to 40 players** per team (LIMIT 40)
   - **Buys ONLY 1 player** per team per trigger
   - Example: 20 CPU teams × 40% act × 40% buy = ~3 teams attempt to buy
   - If 100 good deals exist, CPU will only buy 1 per team (max ~3 total purchases)

2. **CPU Making Offers on User-Listed Players**:
   - **5% of CPU teams** make market offers (if they act)
   - **Evaluates up to 50 players** per team (LIMIT 50)
   - **Makes ONLY 1 offer** per team per trigger (selected from top deals)
   - Example: 20 CPU teams × 40% act × 5% offer = ~0-1 team makes offers
   - If 100 good deals exist, CPU will only make 1 offer per team (max ~1 total offer)

## Example Scenario: 10 User Offers Pending + 100 User-Listed Players

**When trigger_cpu_ai is called:**

1. **Step 1 - Process User Offers** (100%):
   - **All 10 offers are evaluated** (no limit)
   - Each offer checked against good deal criteria
   - Offers that qualify as good deals can be accepted even if below sophisticated valuation
   - **Result**: Some offers accepted, some rejected

2. **Step 2 - CPU Teams Act** (40% per team):
   - If 20 CPU teams exist: ~8 teams will act (40% chance each)
   - ~3 teams will try to buy (40% of acting teams = 8 × 0.4 = ~3)
   - ~0-1 team will make offers (5% of acting teams = 8 × 0.05 = ~0-1)

3. **Step 3 - CPU Actions on User-Listed Players**:
   - **Buying** (~3 teams):
     - Each team evaluates up to **40 players** (LIMIT 40)
     - Each team **buys ONLY 1 player** (stops after first match)
     - **Result**: Max ~3 players bought total (even if 100 good deals exist)
   
   - **Making Offers** (~0-1 team):
     - Each team evaluates up to **50 players** (LIMIT 50)
     - Each team **makes ONLY 1 offer** (selected from top deals)
     - **Result**: Max ~1 offer made total (even if 100 good deals exist)

4. **Good Deal Impact**:
   - User offers to CPU: All 10 evaluated, but good deal NOT applied (CPU selling) ❌
   - CPU buying user-listed: Evaluates up to 40 players, buys only 1 per team, good deal applied ✅
   - CPU offering on user-listed: Evaluates up to 50 players, makes only 1 offer per team, good deal applied ✅

**Key Point**: Even if there are 100 good deals available, CPU will only:
- Buy 1 player per team (max ~3 total purchases)
- Make 1 offer per team (max ~1 total offer)

## Key Points

1. **Good deal is an ADDITIONAL criteria**, not a replacement
   - Works as: `(sophisticated_valuation OR good_deal)`
   - Offers can be accepted via either path

2. **100% of user offers are evaluated** every trigger
   - No random chance - all pending offers go through good deal check

3. **CPU actions are probabilistic**:
   - 40% chance per team to act
   - 40% of acting teams try to buy
   - 5% of acting teams make offers
   - Good deal only applies to user-listed players in these actions

4. **Good deal prioritizes user-listed players**:
   - Makes CPU teams more likely to interact with user listings
   - Encourages market activity between users and CPU

