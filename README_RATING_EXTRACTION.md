# PES6 Player Rating Extraction Solution

## The Problem

PES6 generates dynamic player ratings after every league game that reflect actual in-game performance. These ratings are displayed on the post-match screen but are **only temporarily stored in memory** and are **not saved to disk** with the regular save files. This makes extracting these valuable performance metrics challenging.

## The Solution

I've created a comprehensive solution that provides **multiple methods** to extract these ratings, ranging from simple manual input to advanced memory scanning techniques.

## Quick Start

1. **Run the setup script**:
   ```bash
   python setup_rating_extraction.py
   ```

2. **Install Tesseract OCR** (for automated screen capture):
   - **Windows**: Download from [Tesseract GitHub](https://github.com/UB-Mannheim/tesseract/wiki)
   - **Linux**: `sudo apt-get install tesseract-ocr`

3. **Start the extraction tool**:
   ```bash
   python pes6_rating_extractor.py
   ```

4. **Calibrate screen regions** (option 3) for automated extraction

5. **Extract ratings** after each PES6 match!

## Available Extraction Methods

### 1. 🖥️ OCR Screen Capture (Recommended)
- **Difficulty**: Medium
- **Automation**: High  
- **Setup**: One-time screen calibration required
- **How it works**: Automatically captures and reads the post-match rating screen using OCR

### 2. ✍️ Manual Input
- **Difficulty**: Easy
- **Automation**: None
- **Setup**: None required
- **How it works**: Simple interface to manually input ratings you see on screen

### 3. 🧠 Memory Scanning (Advanced)
- **Difficulty**: Expert
- **Automation**: Very High
- **Setup**: Requires Cheat Engine and memory address discovery
- **How it works**: Directly reads ratings from PES6's memory while running

### 4. 📱 Screen Capture + OCR (Hybrid)
- **Difficulty**: Medium
- **Automation**: High
- **Setup**: Minimal
- **How it works**: Takes screenshots and uses OCR to extract text

## Files Created

| File | Purpose |
|------|---------|
| `pes6_rating_extractor.py` | Main extraction tool with GUI |
| `pes6_rating_extraction_guide.md` | Comprehensive technical guide |
| `cheat_engine_pes6_tutorial.md` | Step-by-step Cheat Engine tutorial |
| `setup_rating_extraction.py` | Automated setup script |

## Database Integration

The extracted ratings are stored in a new `match_ratings` table:

```sql
CREATE TABLE match_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER,
    match_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rating REAL,
    position_played TEXT,
    minutes_played INTEGER,
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    extraction_method TEXT,
    notes TEXT,
    FOREIGN KEY (player_id) REFERENCES players(id)
);
```

This integrates seamlessly with your existing PES6 league management system.

## Key Insights About PES6 Rating Storage

Based on research and analysis:

1. **Temporary Memory Storage**: Ratings exist only during the post-match screen display
2. **Dynamic Allocation**: Memory is allocated at match start, deallocated when leaving results
3. **Performance-Based**: Ratings reflect actual gameplay performance, not just base stats
4. **No Disk Storage**: Standard save files don't contain these dynamic ratings
5. **Memory Block Size**: Approximately 0x90000 bytes for the stats table
6. **Separate Team Areas**: Home and away team stats stored in different memory regions

## Memory Scanning Technical Details

For advanced users using Cheat Engine:

- **Process Name**: Usually `pes6.exe` or `PES6.exe`
- **Data Type**: Likely 32-bit float values (4 bytes each)
- **Value Range**: 0.0 to 10.0 (standard PES rating scale)
- **Alternative Storage**: Some versions may use scaled integers (75 for 7.5)
- **Memory Layout**: Players stored consecutively with fixed offsets

## Usage Examples

### Basic OCR Extraction
```python
from pes6_rating_extractor import PES6RatingManager

manager = PES6RatingManager()
ratings = manager.extract_ratings_interactive()
# Follow on-screen prompts
```

### Manual Rating Input
```python
manager = PES6RatingManager()
ratings = manager.manual_input_ratings()
# Enter ratings in format: player_id:rating
```

### Export Reports
```python
manager = PES6RatingManager()
filename = manager.export_ratings_report(days=30)
# Creates CSV with last 30 days of ratings
```

## Integration with Existing System

The rating extraction system is designed to work alongside your current PES6 league management application. You can:

- **View ratings** in the Flask web interface
- **Analyze performance trends** over time
- **Compare dynamic ratings** vs static player attributes
- **Export data** for external analysis

## Limitations and Considerations

### Technical Limitations
- **Screen resolution dependent** (OCR method)
- **Game version specific** (memory addresses)
- **Windows-focused** (memory scanning tools)
- **Timing sensitive** (ratings only available briefly)

### Legal Considerations
- **Personal use only** - respect game's EULA
- **No redistribution** of extracted data
- **Memory scanning** may trigger anti-cheat systems

## Troubleshooting

### Common Issues

**OCR not working**:
- Calibrate screen regions properly
- Check Tesseract installation
- Verify game resolution and display settings

**Memory scanning fails**:
- Run as Administrator
- Check process name matches
- Verify game version compatibility
- Use Cheat Engine to find addresses first

**Database errors**:
- Ensure PES6 league database exists
- Run setup script to create tables
- Check file permissions

## Future Enhancements

Potential improvements for the system:
- **Automated match detection** (monitor for game state changes)
- **Player name matching** (OCR → database player lookup)
- **Real-time monitoring** (continuous background extraction)
- **Web interface integration** (display ratings in Flask app)
- **Statistical analysis** (performance trend calculations)

## Support

For technical questions about:
- **OCR setup**: Check `pes6_rating_extraction_guide.md`
- **Memory scanning**: Review `cheat_engine_pes6_tutorial.md`
- **Database issues**: Examine existing `app.py` and `db_helper.py`

---

**Note**: This solution provides the foundation for extracting PES6's dynamic player ratings. The specific implementation may need adjustment based on your game version, screen resolution, and system configuration.