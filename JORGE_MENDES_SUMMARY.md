# Jorge Mendes System - Summary

## ✅ Confirmed: Same Salary Calculation as contract_renewal.py

Both systems now use **identical** salary calculation:

### Calculation Flow:
1. **Base Salary:** `calculate_player_salary_base()` 
   - Uses position-specific skill averages
   - Applies skill importance weighting
   - Applies binary skill bonuses

2. **Defensive Boost:** 1.75x multiplier for positions 0, 2, 3, 4 (GK, CBT, DMF, FB)

3. **No Random Adjustment:** Fair salary is deterministic (contract_renewal.py doesn't use random, so Jorge Mendes doesn't either)

### Result:
✅ Fair salary calculation is **100% consistent** with contract renewals
✅ Toxicity calculation is **accurate and reliable**

---

## How Jorge Mendes Works

### 1. Calculate Fair Salary (from skills)
Uses same calculation as contract renewals - deterministic, no randomness.

### 2. Calculate Toxicity
```python
toxicity = (current_salary - fair_salary) × contract_years × 1.03

Positive toxicity = Overpaid contract (reduces sale price)
Negative toxicity = Underpaid contract (increases sale price)
```

### 3. Calculate Sale Price
```python
base_price = market_value × (50% to 75% random)
sale_price = base_price - toxicity

Can go negative for extremely toxic contracts!
```

### 4. Calculate Commission (Always Positive)
```python
commission = abs(sale_price) × 25%
Always positive, even for compensation payments
```

### 5. Calculate Net Amount
```python
If sale_price >= 0:
    net_amount = sale_price - commission
    (User receives money minus commission)

If sale_price < 0:
    net_amount = sale_price - commission
    (User pays compensation + commission)
```

---

## Example Calculations

### Example 1: Good Contract (Neymar with fix)
- Market Value: €45,390,000 (from database)
- Current Salary: €1,000,000/year
- Fair Salary: €7,478,000/year (calculated)
- Contract: 3 years
- **Toxicity:** (€1M - €7.5M) × 3 × 1.03 = **-€20M** (underpaid)
- **Sale Price:** (€45.4M × 65%) - (-€20M) = **€49.5M** ✅
- **Commission:** €49.5M × 25% = **€12.4M**
- **Net Amount:** €49.5M - €12.4M = **€37.1M** ✅

### Example 2: Toxic Contract
- Market Value: €5,000,000
- Current Salary: €6,000,000/year (overpaid!)
- Fair Salary: €1,000,000/year
- Contract: 4 years
- **Toxicity:** (€6M - €1M) × 4 × 1.03 = **+€20.6M** (overpaid)
- **Sale Price:** (€5M × 60%) - €20.6M = **-€17.6M** (compensation!)
- **Commission:** €17.6M × 25% = **€4.4M** (always positive)
- **Net Amount:** -€17.6M - €4.4M = **-€22M** (total cost) ✅

---

## What Gets Updated

### User's Team:
- ✅ Budget increases/decreases by net_amount
- ✅ Total salaries decreases (player leaves)
- ✅ Available cap increases

### CPU Buyer Team:
- ✅ Budget decreases/increases by sale_price
- ✅ Total salaries increases (player joins)
- ✅ Available cap decreases

### Player:
- ✅ Transferred to CPU team with least players in that position
- ✅ Keeps current contract (salary, years remain)

### Financial Records:
- ✅ User movement recorded in `user_movements`
- ✅ Movement type: "Transfer In" or "Transfer Out"
- ✅ Includes balance_after calculation

### Blog Post (posts table):
- ✅ Shows player name, from/to clubs
- ✅ Shows sale price or compensation
- ✅ Shows commission amount
- ✅ Shows net amount to seller
- ✅ Color-coded (blue for sales, red for compensation)

---

## Team Selection Algorithm

CPU team selected based on:
1. **Fewest players in that position** (priority)
2. **Has sufficient budget** to pay sale_price
3. **Has roster space** (< 32 players)
4. **Random tiebreaker** if multiple teams match

This ensures optimal team placement!

---

## Commission Rules

Jorge Mendes **always gets paid** (25% of transaction value):
- Normal sale: 25% of sale price
- Compensation: 25% of compensation (added to user's cost)
- Commission is ALWAYS positive and deducted from proceeds or added to costs

---

## System Consistency Verified ✅

- ✅ Uses same salary calculation as contract_renewal.py
- ✅ Uses player's database market_value (not recalculated)
- ✅ Applies same defensive position boost (1.75x)
- ✅ No random adjustments (deterministic for fairness)
- ✅ Blog posts go to correct table (posts, not blog_posts)
- ✅ Financial movements tracked properly
- ✅ Secondary teams included in buyer pool

