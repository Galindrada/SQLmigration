# Swap Accept Button Fix ✅

## Problem Found

**Issue:** Swap offers were not working because unlisted swap offers were using the wrong accept function.

**Root Cause:**
- **Listed swap offers**: Used `acceptOffer(offer_id)` → calls `/market_bazaar/accept_offer/<offer_id>` → properly handles swaps ✅
- **Unlisted swap offers**: Used `acceptCPUOfferDirect(player_id, ...)` → calls `/market_bazaar/accept_cpu_offer_direct` → doesn't handle swaps ❌

The `acceptCPUOfferDirect` route only handles cash transfers, not swaps.

## Fix Applied

**File:** `templates/market_bazaar.html`

### 1. Updated Unlisted Swap Offers to Use Correct Function

Changed unlisted swap offers to use `acceptOffer()` instead of `acceptCPUOfferDirect()`:

```html
{% if offer.swap_type in ['swap', 'cash+swap'] %}
    {# Unlisted swap offer buttons #}
    <button onclick="acceptOffer({{ offer.id }}, ...)">
        Accept
    </button>
{% else %}
    {# Regular unlisted cash offer #}
    <button onclick="acceptCPUOfferDirect(...)">
        Accept
    </button>
{% endif %}
```

### 2. Enhanced acceptOffer() Function

Updated `acceptOffer()` JavaScript function to:
- Accept optional swap parameters (`swapPlayerName`, `cashCompensation`)
- Show appropriate confirmation message for swap offers
- Show regular confirmation for cash offers

### 3. Updated All acceptOffer() Calls

Updated all `acceptOffer()` calls to pass swap information when available:
- Listed swap offers: Pass swap player name and cash compensation
- Unlisted swap offers: Pass swap player name and cash compensation
- Regular cash offers: Only pass basic parameters

## Result

✅ **Listed swap offers**: Now work correctly (already working)
✅ **Unlisted swap offers**: Now work correctly (fixed)
✅ **Confirmation messages**: Show swap details for swap offers
✅ **Backend route**: Already handles swaps correctly via `/market_bazaar/accept_offer/<offer_id>`

## Testing

To test:
1. Trigger CPU AI to create swap offers for unlisted players
2. Go to Market Bazaar → "CPU Offers for Your Unlisted Players"
3. Find a swap offer (should show 🔄 SWAP badge)
4. Click "Accept" button
5. Should see swap confirmation message
6. After accepting, both players should swap teams correctly

## Status

✅ Template updated to use correct function for unlisted swaps
✅ JavaScript function enhanced to handle swap confirmations
✅ All acceptOffer() calls updated with swap parameters
✅ Ready for testing
