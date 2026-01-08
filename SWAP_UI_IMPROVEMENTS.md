# Swap UI Improvements ✅

## Changes Made

### 1. Removed "View Swap" Button
- **Reason**: Button didn't do anything useful
- **Location**: Both listed and unlisted swap offers
- **Result**: Cleaner UI with just Accept/Reject buttons

### 2. Made Swap Player Name Clickable
- **Change**: Swap player name now links to player page
- **Route**: `/pes6_player/<swap_player_id>`
- **Implementation**: Added `<a href="/pes6_player/{{ offer.swap_player_id }}">` around swap player name
- **Result**: Users can quickly view details of the player being offered in the swap

## Stance Variable Investigation

### Found:
- **Column**: `stance` in `teams` table
- **Default Value**: `'Tinkering'`
- **Current Usage**: Not currently used in swap AI logic
- **Location**: `refresh_and_reimport.py` line 399

### Next Steps for Swap AI:
The stance variable should be integrated into the swap AI logic in `attempt_player_swap_offer()` to influence:
1. **Which players to swap**: Teams with different stances might prioritize different positions
2. **Swap aggressiveness**: Some stances might be more willing to swap
3. **Position preferences**: Defensive stances might prefer defensive players, attacking stances prefer attackers

### Possible Stance Values:
- `'Tinkering'` (current default)
- Potentially: `'Balanced'`, `'Defensive'`, `'Attacking'`, `'Youth Development'`, etc.

## Status

✅ View Swap button removed
✅ Swap player name is now clickable
⏳ Stance variable ready for AI integration
