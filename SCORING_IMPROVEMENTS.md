# Scoring and Assist Improvements

## Changes Implemented

### 1. ⭐ Higher-Rated Players More Likely to Score/Assist

**Old Formula**:
```python
weight = position_prob * (overall / 100)
```
- Linear relationship with overall
- 85 overall player = 0.85x weight
- 70 overall player = 0.70x weight
- Ratio: 1.21x (not much difference)

**New Formula**:
```python
overall_squared = (overall ** 2) / 10000
weight = position_prob * overall_squared * minutes_factor
```
- Quadratic relationship with overall
- 85 overall player = 7.225 weight
- 70 overall player = 4.900 weight
- **Ratio: 1.47x** (much more significant)

**Impact**:
- ✅ Star players score/assist much more frequently
- ✅ Lower-rated players less likely to be involved
- ✅ More realistic stat distribution

### 2. 🔄 Substitutes Less Likely to Score/Assist

**New Factor**: Minutes played weight
```python
minutes_factor = minutes_played / 90.0
```

**Examples**:
- **Full starter** (90 minutes): Factor = 1.0 (full weight)
- **Subbed at 70'** (70 minutes): Factor = 0.78 (22% reduction)
- **Sub comes on at 70'** (20 minutes): Factor = 0.22 (78% reduction)
- **Sub comes on at 80'** (10 minutes): Factor = 0.11 (89% reduction)

**Impact**:
- ✅ Starters much more likely to score/assist
- ✅ Subs have reduced impact (realistic)
- ✅ Late subs rarely score (realistic)

### 3. Combined Effect

**Example Comparison**:

**Starter** (85 overall, 90 minutes):
```
weight = position_prob * (85²/10000) * (90/90)
weight = position_prob * 7.225 * 1.0
weight = position_prob * 7.225
```

**Sub** (85 overall, 20 minutes):
```
weight = position_prob * (85²/10000) * (20/90)
weight = position_prob * 7.225 * 0.22
weight = position_prob * 1.59
```

**Result**: Starter is **4.5x more likely** to score than sub with same overall!

**Lower-Rated Starter** (70 overall, 90 minutes):
```
weight = position_prob * (70²/10000) * (90/90)
weight = position_prob * 4.9 * 1.0
weight = position_prob * 4.9
```

**Result**: 85-rated starter is **1.47x more likely** to score than 70-rated starter

## Mathematical Examples

### Scoring Probability Comparison

**Scenario**: Forward position (score_prob = 0.55)

| Player | Overall | Minutes | Old Weight | New Weight | Relative Probability |
|--------|---------|---------|------------|------------|---------------------|
| Star Starter | 90 | 90 | 0.495 | 4.455 | 100% (baseline) |
| Good Starter | 80 | 90 | 0.440 | 3.520 | 79% |
| Average Starter | 70 | 90 | 0.385 | 2.695 | 60% |
| Star Sub | 90 | 20 | 0.495 | 0.990 | 22% |
| Average Sub | 70 | 20 | 0.385 | 0.599 | 13% |

**Key Insights**:
- Star starters dominate scoring (as expected)
- Average subs have only 13% chance vs star starters
- Quality matters much more now
- Playing time matters significantly

### Assist Probability Comparison

**Scenario**: Midfielder position (assist_prob = 0.35)

| Player | Overall | Minutes | Old Weight | New Weight | Relative Probability |
|--------|---------|---------|------------|------------|---------------------|
| Star Starter | 90 | 90 | 0.315 | 2.835 | 100% (baseline) |
| Good Starter | 80 | 90 | 0.280 | 2.240 | 79% |
| Average Starter | 70 | 90 | 0.245 | 1.715 | 60% |
| Star Sub | 90 | 20 | 0.315 | 0.630 | 22% |
| Average Sub | 70 | 20 | 0.245 | 0.381 | 13% |

## Benefits

### 1. ✅ More Realistic Stat Distribution
- Star players get more goals/assists (as in real football)
- Bench players rarely score
- Late subs almost never score

### 2. ✅ Quality Matters More
- Investing in high-overall players pays off
- 90-rated striker >> 70-rated striker
- Visible difference in performance

### 3. ✅ Minutes Played Impact
- Starters dominate stats (realistic)
- Subs contribute less (realistic)
- Substitution timing matters

### 4. ✅ No Self-Assists
- Scorer always excluded from assist candidates
- Assists always <= goals
- ~60% of goals have assists

## Files Modified

1. **international_simulation.py** (Lines 245-340)
   - Added minutes_factor to scoring weights
   - Added overall² to favor higher-rated players
   - Applied to both goals and assists

2. **cpu_leagues.py** (Lines 2507-2600)
   - Added minutes_factor to scoring weights
   - Added overall² to favor higher-rated players
   - Applied to both goals and assists

3. **SCORING_IMPROVEMENTS.md** (THIS FILE)
   - Complete documentation
   - Mathematical examples
   - Impact analysis

## Testing

Simulate new games to see the improvements:
- Higher-rated players will score/assist more frequently
- Substitutes will rarely score
- No self-assists
- Assists <= goals

## Expected Results

**Top Scorer Profile** (after 22 games):
- 85+ overall forward
- Plays 90 minutes most games
- Expected: 15-25 goals

**Average Player** (after 22 games):
- 70-75 overall midfielder
- Plays 90 minutes most games
- Expected: 3-8 goals

**Substitute** (after 22 games):
- 75-80 overall
- Plays 20-30 minutes per game
- Expected: 1-3 goals

## Notes

- Overall² creates exponential advantage for better players
- Minutes factor creates linear disadvantage for subs
- Combined effect: Starters with high overall dominate
- Position probabilities still apply (forwards > midfielders > defenders)
- 60% assist rate ensures assists <= goals
- Scorer exclusion prevents self-assists

The scoring system is now much more realistic and rewards quality and playing time! ⚽

