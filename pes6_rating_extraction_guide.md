# PES6 Player Rating Extraction Guide

## Overview

PES6 generates dynamic player ratings after every league game that are displayed on the post-match screen. These ratings are **temporarily stored in memory** during gameplay but are **not saved to disk** in the standard save files. This guide explores various methods to extract these values while the game is running.

## Current System Analysis

Based on the existing codebase, the current system:
- Stores static player attributes in a SQLite database
- Calculates bundled skill ratings from base attributes:
  - `attack_rating` = attack value
  - `defense_rating` = (defense + aggression) / 2
  - `physical_rating` = (stamina + top_speed + acceleration + response + agility + jump) / 6
  - `power_rating` = (shot_power + balance + mentality) / 3
  - `technique_rating` = (technique + swerve + free_kick_accuracy + dribble_accuracy + dribble_speed + short_pass_accuracy + short_pass_speed + long_pass_accuracy + long_pass_speed) / 9
  - `goalkeeping_rating` = (defense + goal_keeping + response + agility) / 4

However, these are **static calculations** and don't capture the **dynamic post-match performance ratings** that PES6 generates.

## Memory Storage Behavior

According to research on similar PES versions:
- Player ratings are dynamically allocated in memory at match start
- The memory structure is deallocated when exiting post-match results
- Ratings reflect actual in-game performance (not just base stats)
- Memory block size is typically around 0x90000 bytes
- Separate memory areas for home/away team stats

## Extraction Methods

### Method 1: Manual Recording
**Difficulty**: Easy  
**Automation**: None  
**Reliability**: High  

Simply record the ratings displayed on the post-match screen:
- Take screenshots after each match
- Manually transcribe ratings to a spreadsheet/database
- Most reliable but time-consuming

### Method 2: Cheat Engine Memory Scanning
**Difficulty**: Advanced  
**Automation**: Partial  
**Reliability**: Medium  

Steps:
1. **Install Cheat Engine** (free memory scanner/debugger)
2. **Attach to PES6 process** while game is running
3. **Search for dynamic values**:
   - Start a match
   - Use "Unknown initial value" scan
   - After match ends, note a player's rating (e.g., 7.5)
   - Search for this value (as float or scaled integer)
   - Repeat for multiple matches to narrow down addresses
4. **Create memory pointers** for consistent access
5. **Export/monitor values** during gameplay

**Challenges**:
- Memory addresses may change between game sessions
- Requires understanding of data types (float vs integer scaling)
- Game updates may invalidate found addresses

### Method 3: Process Memory Reading (Python)
**Difficulty**: Expert  
**Automation**: High  
**Reliability**: Medium  

Using Python libraries like `pymem` or `ctypes`:

```python
import pymem
import struct

def extract_pes6_ratings():
    try:
        # Attach to PES6 process
        pm = pymem.Pymem("pes6.exe")  # Adjust process name
        
        # Known memory addresses (would need to be discovered)
        base_address = 0x????????  # Base address for player stats
        
        # Read player rating data
        for i in range(22):  # 11 players per team, 2 teams
            offset = base_address + (i * 0x???)  # Player data size
            rating_data = pm.read_bytes(offset, 4)  # 4 bytes for float
            rating = struct.unpack('f', rating_data)[0]
            print(f"Player {i}: {rating}")
            
    except Exception as e:
        print(f"Error: {e}")
```

**Requirements**:
- Reverse engineering to find memory addresses
- Process privileges (run as administrator)
- Stable memory layout identification

### Method 4: API Hooking/DLL Injection
**Difficulty**: Expert  
**Automation**: High  
**Reliability**: High  

Intercept game API calls that update player ratings:
- Hook DirectX/GDI calls that display ratings
- Inject custom DLL to capture rating calculations
- Most reliable but requires advanced programming

### Method 5: Screen Capture + OCR
**Difficulty**: Medium  
**Automation**: High  
**Reliability**: Medium  

Automated screenshot analysis:
1. **Capture post-match screen** using tools like `pyautogui`
2. **OCR text recognition** to extract rating numbers
3. **Parse and store** in database

```python
import pyautogui
import pytesseract
from PIL import Image

def capture_ratings():
    # Wait for post-match screen
    screenshot = pyautogui.screenshot(region=(x, y, width, height))
    text = pytesseract.image_to_string(screenshot)
    # Parse rating values from text
    return parse_ratings(text)
```

## Recommended Approach

For your existing PES6 league management system, I recommend a **hybrid approach**:

1. **Start with Method 5 (Screen Capture + OCR)** for automation
2. **Fallback to Method 1 (Manual)** for verification
3. **Explore Method 2 (Cheat Engine)** for advanced users

## Implementation Considerations

### Memory Scanning Prerequisites
- **Administrator privileges** required
- **Antivirus exceptions** may be needed for memory tools
- **Game version compatibility** - addresses vary between patches
- **Timing sensitivity** - ratings only available during specific screens

### Data Integration
The extracted ratings should be stored in a new table:

```sql
CREATE TABLE IF NOT EXISTS match_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER,
    match_date TIMESTAMP,
    rating REAL,
    position_played TEXT,
    minutes_played INTEGER,
    FOREIGN KEY (player_id) REFERENCES players(id)
);
```

### Legal and Ethical Considerations
- **Terms of Service**: Memory scanning may violate game EULA
- **Anti-cheat**: Some methods might trigger anti-cheat systems
- **Personal Use**: Keep extraction for personal analysis only

## Next Steps

To implement rating extraction for your system:
1. Choose appropriate method based on technical skill level
2. Set up memory scanning tools (if using advanced methods)
3. Modify database schema to store match ratings
4. Create extraction scripts/automation
5. Integrate with existing Flask application

## Tools and Resources

- **Cheat Engine**: Free memory scanner and debugger
- **Process Hacker**: Alternative process analysis tool
- **pymem**: Python library for memory manipulation
- **pyautogui**: Python library for screen automation
- **pytesseract**: Python OCR library

Remember: The dynamic nature of post-match ratings makes them valuable for performance analysis beyond static player attributes.