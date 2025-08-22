#!/usr/bin/env python3
"""
Setup script for PES6 Rating Extraction System

This script helps set up the necessary dependencies and database schema
for extracting player ratings from PES6.
"""

import subprocess
import sys
import sqlite3
import os

def install_dependencies():
    """Install optional dependencies for rating extraction."""
    print("Installing dependencies for PES6 rating extraction...")
    
    dependencies = [
        "pyautogui==0.9.54",
        "pytesseract==0.3.10", 
        "Pillow==10.0.1",
        "pymem==1.13.0"
    ]
    
    for dep in dependencies:
        try:
            print(f"Installing {dep}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
            print(f"✓ {dep} installed successfully")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install {dep}: {e}")
            if "pymem" in dep:
                print("  Note: pymem is Windows-only for memory scanning")

def setup_database_schema():
    """Set up the match_ratings table in the database."""
    db_path = "pes6_league_db.sqlite"
    
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found. Please ensure PES6 league database exists.")
        return False
    
    print("Setting up match_ratings table...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create match_ratings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_ratings (
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
        )
    """)
    
    # Add indexes for better performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_match_ratings_player_id 
        ON match_ratings(player_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_match_ratings_date 
        ON match_ratings(match_date)
    """)
    
    conn.commit()
    conn.close()
    
    print("✓ Database schema updated successfully")
    return True

def check_tesseract_installation():
    """Check if Tesseract OCR is installed on the system."""
    print("Checking Tesseract OCR installation...")
    
    try:
        result = subprocess.run(["tesseract", "--version"], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✓ Tesseract OCR is installed")
            print(f"  Version: {result.stdout.split()[1]}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    print("✗ Tesseract OCR not found")
    print("  Please install Tesseract OCR:")
    print("  - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki")
    print("  - Linux: sudo apt-get install tesseract-ocr")
    print("  - macOS: brew install tesseract")
    return False

def create_example_config():
    """Create example configuration files."""
    print("Creating example configuration...")
    
    # Example screen calibration
    example_calibration = {
        "home_team": [100, 200, 400, 600],
        "away_team": [500, 200, 400, 600],
        "description": "Screen regions for rating extraction. Calibrate with actual coordinates."
    }
    
    with open("pes6_screen_calibration_example.json", "w") as f:
        import json
        json.dump(example_calibration, f, indent=2)
    
    print("✓ Example configuration created: pes6_screen_calibration_example.json")

def main():
    """Main setup function."""
    print("PES6 Rating Extraction Setup")
    print("============================")
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("✗ Python 3.7+ required")
        return
    
    print(f"✓ Python {sys.version}")
    
    # Install dependencies
    install_dependencies()
    
    # Setup database
    if setup_database_schema():
        print("✓ Database setup completed")
    
    # Check Tesseract
    check_tesseract_installation()
    
    # Create example config
    create_example_config()
    
    print("\n" + "="*50)
    print("Setup completed!")
    print("\nNext steps:")
    print("1. Install Tesseract OCR if not already installed")
    print("2. Run: python pes6_rating_extractor.py")
    print("3. Choose option 3 to calibrate screen regions")
    print("4. Start extracting ratings after PES6 matches!")
    print("\nFor advanced users:")
    print("- Review cheat_engine_pes6_tutorial.md for memory scanning")
    print("- Use Cheat Engine to find specific memory addresses")
    print("\nFiles created:")
    print("- pes6_rating_extractor.py (main extraction tool)")
    print("- pes6_rating_extraction_guide.md (comprehensive guide)")
    print("- cheat_engine_pes6_tutorial.md (advanced tutorial)")

if __name__ == "__main__":
    main()