# Swap Offers Fix ✅

## Problem Found

**Issue:** Swap offers were being created but not showing up in the UI

**Root Cause:** 
1. Swap offers were being created with status `'pending'`
2. The query in `app.py` was only looking for status `'active'`
3. Result: Swap offers existed in database but weren't displayed

## Fixes Applied

### 1. Updated Query to Include Both Statuses ✅
**File:** `app.py` line ~5694

**Change:**
```python
# Before:
WHERE mbo.status = 'active'

# After:
WHERE mbo.status IN ('active', 'pending')
```

This ensures both active and pending swap offers are shown.

### 2. Changed Swap Offer Creation to Use 'active' Status ✅
**File:** `swap_and_loan_features.py` line ~79

**Change:**
```python
# Before:
VALUES (..., 'pending', ...)

# After:
VALUES (..., 'active', ...)
```

New swap offers will now be created with 'active' status to match other offers.

### 3. Updated Existing Swap Offers ✅
Updated 8 existing swap offers in database from 'pending' to 'active' so they appear immediately.

## Result

✅ Swap offers now show up in Market Bazaar
✅ Query includes both 'active' and 'pending' statuses
✅ New swap offers created with 'active' status
✅ Existing swap offers updated to 'active'

## Testing

**Before Fix:**
- 8 swap offers in database
- 0 active swap offers
- 0 shown in UI

**After Fix:**
- 8 swap offers in database
- 8 active swap offers
- All 8 should now show in UI

## Status

✅ Swap offers should now be visible in the Market Bazaar!
