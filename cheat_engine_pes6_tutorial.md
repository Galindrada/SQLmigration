# Cheat Engine Tutorial: Extracting PES6 Player Ratings

## Prerequisites

1. **Download Cheat Engine** from [cheatengine.org](https://cheatengine.org)
2. **Install with default settings**
3. **Run as Administrator** (required for memory access)
4. **Add antivirus exception** if needed

## Step-by-Step Process

### Step 1: Prepare PES6
1. Launch PES6
2. Start a league match
3. **Don't attach Cheat Engine yet** - wait for the match to finish

### Step 2: Initial Memory Scan
1. **Finish the match** and wait for the post-match rating screen
2. **Note down a specific player's rating** (e.g., Player X has rating 7.5)
3. **Launch Cheat Engine**
4. Click **"Select a process to open"** (computer icon)
5. Find and select **pes6.exe** (or similar process name)
6. Click **"Open"**

### Step 3: First Value Search
1. In the **Value** field, enter the rating you noted (e.g., 7.5)
2. Set **Value Type** to **"Float"** (ratings are usually decimal numbers)
3. Click **"First Scan"**
4. You'll see many results in the left panel - this is normal

### Step 4: Narrow Down Results
1. **Play another match** (or restart the current one)
2. **Wait for post-match screen** again
3. **Note the same player's new rating** (e.g., now 8.0)
4. In Cheat Engine, enter the **new rating value** (8.0)
5. Click **"Next Scan"**
6. **Repeat this process** 3-4 times with different matches

### Step 5: Identify Stable Addresses
After several scans, you should have only a few addresses left:

1. **Double-click promising addresses** to add them to the bottom panel
2. **Change their descriptions** to something meaningful (e.g., "Player 1 Rating")
3. **Test by playing another match** - the values should update correctly

### Step 6: Find All Player Ratings
Once you have one player's rating address:

1. **Right-click the address** → **"Browse this memory region"**
2. Look for **patterns in nearby memory**
3. Player ratings are usually stored **consecutively** or with **fixed offsets**
4. **Calculate the offset** between players (e.g., every 0x4C bytes)

### Step 7: Create Address Pointers
For more stable extraction:

1. **Right-click an address** → **"Find out what accesses this address"**
2. **Play through a match** to see what code accesses the ratings
3. **Create pointers** based on base addresses + offsets
4. **Test pointers** across game restarts

## Common Memory Patterns

### Typical Rating Storage Formats
- **Float values**: 7.5 stored as 32-bit float
- **Scaled integers**: 7.5 stored as 75 (multiply by 10)
- **Byte values**: 7.5 stored as 75 in single byte

### Expected Memory Layout
```
Base Address + 0x00: Home Player 1 Rating
Base Address + 0x04: Home Player 1 Goals
Base Address + 0x08: Home Player 1 Assists
Base Address + 0x0C: Home Player 1 Minutes
...
Base Address + 0x4C: Home Player 2 Rating
...
Base Address + 0x2D0: Away Player 1 Rating
```

## Advanced Techniques

### Using Cheat Engine's Lua Scripting
Create automated extraction scripts:

```lua
-- Cheat Engine Lua script for PES6 rating extraction
function extractAllRatings()
    local ratings = {}
    local baseAddr = 0x????????  -- Your discovered base address
    
    -- Extract home team (11 players)
    for i = 0, 10 do
        local addr = baseAddr + (i * 0x4C)  -- Adjust offset as needed
        local rating = readFloat(addr)
        if rating >= 0 and rating <= 10 then
            ratings[i+1] = rating
        end
    end
    
    -- Extract away team
    for i = 0, 10 do
        local addr = baseAddr + 0x2D0 + (i * 0x4C)  -- Adjust offset
        local rating = readFloat(addr)
        if rating >= 0 and rating <= 10 then
            ratings[i+12] = rating
        end
    end
    
    return ratings
end

-- Auto-save ratings to file
function saveRatingsToFile()
    local ratings = extractAllRatings()
    local file = io.open("pes6_ratings.txt", "a")
    file:write(os.date() .. "\n")
    for player, rating in pairs(ratings) do
        file:write("Player " .. player .. ": " .. rating .. "\n")
    end
    file:write("\n")
    file:close()
end
```

### Memory Breakpoints
1. **Set breakpoints** on rating calculation code
2. **Trace execution** to understand rating algorithms
3. **Hook functions** that update ratings

## Troubleshooting

### Common Issues

**"Process not found"**
- Ensure PES6 is running
- Check exact process name (might be different)
- Run Cheat Engine as Administrator

**"Too many results"**
- Use more specific value types
- Scan during stable game states
- Use "Unknown initial value" → "Changed value" approach

**"Values don't update"**
- Addresses might be temporary
- Game uses dynamic memory allocation
- Create pointers instead of static addresses

**"Access violation errors"**
- Some memory regions are protected
- Try different data types (float vs int)
- Use "Read-only" mode for safer scanning

### Alternative Search Strategies

1. **Unknown Initial Value Method**:
   - Start scan with "Unknown initial value"
   - After match: "Changed value"
   - Repeat until few results remain

2. **Range-based Search**:
   - Search for values between 0 and 10
   - Narrow down after each match

3. **Group Scan**:
   - Search for multiple related values simultaneously
   - More reliable for finding player data structures

## Integration with Python Script

Once you find stable addresses, add them to the Python extractor:

```python
# In pes6_rating_extractor.py
KNOWN_ADDRESSES = {
    'home_team_base': 0x????????,
    'away_team_base': 0x????????,
    'player_offset': 0x4C,
    'rating_offset': 0x00,
}
```

## Safety Notes

- **Backup your save games** before starting
- **Don't modify values** during extraction (read-only)
- **Close Cheat Engine** when not needed
- **Be aware of EULA implications**

## Expected Results

After successful setup, you should be able to:
- Extract all 22 player ratings automatically
- Monitor rating changes in real-time
- Export data to your league management system
- Track performance trends over multiple matches

Remember: This process requires patience and experimentation. Memory layouts can vary between game versions and system configurations.