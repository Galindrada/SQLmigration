#!/usr/bin/env python3
"""
PES6 Player Rating Extractor

This script provides multiple methods to extract player ratings from PES6
after league matches. The ratings are temporarily stored in memory during
gameplay and displayed on the post-match screen.
"""

import time
import sqlite3
import re
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

# Optional imports for different extraction methods
try:
    import pyautogui
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("OCR libraries not available. Install: pip install pyautogui pytesseract pillow")

try:
    import pymem
    import struct
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    print("Memory scanning libraries not available. Install: pip install pymem")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PES6RatingExtractor:
    """
    Main class for extracting player ratings from PES6 using various methods.
    """
    
    def __init__(self, db_path: str = "pes6_league_db.sqlite"):
        self.db_path = db_path
        self.setup_database()
    
    def setup_database(self):
        """Create match_ratings table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
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
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Database setup completed")
    
    def save_ratings(self, ratings: List[Dict], extraction_method: str):
        """Save extracted ratings to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for rating_data in ratings:
            cursor.execute("""
                INSERT INTO match_ratings 
                (player_id, rating, position_played, minutes_played, goals, assists, extraction_method)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                rating_data.get('player_id'),
                rating_data.get('rating'),
                rating_data.get('position'),
                rating_data.get('minutes', 90),
                rating_data.get('goals', 0),
                rating_data.get('assists', 0),
                extraction_method
            ))
        
        conn.commit()
        conn.close()
        logger.info(f"Saved {len(ratings)} ratings using method: {extraction_method}")

class OCRRatingExtractor(PES6RatingExtractor):
    """
    Extract player ratings using screen capture and OCR.
    """
    
    def __init__(self, db_path: str = "pes6_league_db.sqlite"):
        super().__init__(db_path)
        self.rating_regions = {
            # These coordinates need to be calibrated for your screen resolution
            'home_team': (100, 200, 400, 600),  # (x, y, width, height)
            'away_team': (500, 200, 400, 600),
        }
    
    def calibrate_screen_regions(self):
        """
        Interactive calibration to identify rating display areas.
        Run this once to set up screen coordinates for your resolution.
        """
        if not OCR_AVAILABLE:
            logger.error("OCR libraries not available")
            return
        
        print("Position your mouse over the top-left of the home team ratings and press Enter...")
        input()
        x1, y1 = pyautogui.position()
        
        print("Position your mouse over the bottom-right of the home team ratings and press Enter...")
        input()
        x2, y2 = pyautogui.position()
        
        self.rating_regions['home_team'] = (x1, y1, x2-x1, y2-y1)
        
        print("Position your mouse over the top-left of the away team ratings and press Enter...")
        input()
        x1, y1 = pyautogui.position()
        
        print("Position your mouse over the bottom-right of the away team ratings and press Enter...")
        input()
        x2, y2 = pyautogui.position()
        
        self.rating_regions['away_team'] = (x1, y1, x2-x1, y2-y1)
        
        # Save calibration
        with open('pes6_screen_calibration.json', 'w') as f:
            json.dump(self.rating_regions, f, indent=2)
        
        logger.info("Screen calibration completed and saved")
    
    def load_calibration(self):
        """Load saved screen calibration."""
        try:
            with open('pes6_screen_calibration.json', 'r') as f:
                self.rating_regions = json.load(f)
            logger.info("Screen calibration loaded")
            return True
        except FileNotFoundError:
            logger.warning("No calibration file found. Run calibrate_screen_regions() first.")
            return False
    
    def preprocess_image(self, image: Image) -> Image:
        """Enhance image for better OCR accuracy."""
        # Convert to grayscale
        image = image.convert('L')
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)
        
        # Apply slight blur to smooth text
        image = image.filter(ImageFilter.SMOOTH)
        
        # Scale up for better OCR
        width, height = image.size
        image = image.resize((width * 3, height * 3), Image.LANCZOS)
        
        return image
    
    def extract_ratings_from_text(self, text: str) -> List[Dict]:
        """Parse OCR text to extract player ratings."""
        ratings = []
        lines = text.split('\n')
        
        # Look for rating patterns (e.g., "7.5", "8.0", etc.)
        rating_pattern = r'(\d+\.?\d*)\s*(?:/10)?'
        player_pattern = r'([A-Z][A-Za-z\s]+)\s+(\d+\.?\d*)'
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Try to match player name + rating
            match = re.search(player_pattern, line)
            if match:
                player_name = match.group(1).strip()
                rating = float(match.group(2))
                
                if 0 <= rating <= 10:  # Valid rating range
                    ratings.append({
                        'player_name': player_name,
                        'rating': rating,
                        'raw_text': line
                    })
            
            # Also look for standalone ratings
            rating_matches = re.findall(rating_pattern, line)
            for rating_str in rating_matches:
                try:
                    rating = float(rating_str)
                    if 0 <= rating <= 10:
                        ratings.append({
                            'rating': rating,
                            'raw_text': line
                        })
                except ValueError:
                    continue
        
        return ratings
    
    def wait_for_post_match_screen(self, timeout: int = 300) -> bool:
        """
        Wait for the post-match screen to appear.
        Returns True if detected, False if timeout.
        """
        if not OCR_AVAILABLE:
            return False
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Take a small screenshot to check for post-match indicators
                screenshot = pyautogui.screenshot(region=(0, 0, 200, 100))
                text = pytesseract.image_to_string(screenshot).lower()
                
                # Look for common post-match screen text
                if any(keyword in text for keyword in ['rating', 'performance', 'statistics', 'stats']):
                    logger.info("Post-match screen detected")
                    return True
                
                time.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"Error checking for post-match screen: {e}")
                time.sleep(5)
        
        logger.warning("Post-match screen detection timeout")
        return False
    
    def extract_ratings_ocr(self) -> List[Dict]:
        """
        Extract player ratings using OCR from post-match screen.
        """
        if not OCR_AVAILABLE:
            logger.error("OCR libraries not available")
            return []
        
        if not self.load_calibration():
            logger.error("Screen calibration required. Run calibrate_screen_regions() first.")
            return []
        
        all_ratings = []
        
        for team_name, region in self.rating_regions.items():
            try:
                # Capture the rating area
                screenshot = pyautogui.screenshot(region=region)
                
                # Preprocess for better OCR
                processed_image = self.preprocess_image(screenshot)
                
                # Extract text using OCR
                text = pytesseract.image_to_string(processed_image, 
                                                 config='--psm 6 -c tessedit_char_whitelist=0123456789.ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ')
                
                # Parse ratings from text
                team_ratings = self.extract_ratings_from_text(text)
                
                # Add team info
                for rating in team_ratings:
                    rating['team'] = team_name
                
                all_ratings.extend(team_ratings)
                
                # Save debug image
                debug_filename = f"debug_{team_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                processed_image.save(debug_filename)
                logger.info(f"Debug image saved: {debug_filename}")
                
            except Exception as e:
                logger.error(f"Error extracting ratings for {team_name}: {e}")
        
        return all_ratings

class MemoryRatingExtractor(PES6RatingExtractor):
    """
    Extract player ratings using memory scanning (requires pymem).
    """
    
    def __init__(self, db_path: str = "pes6_league_db.sqlite", process_name: str = "pes6.exe"):
        super().__init__(db_path)
        self.process_name = process_name
        self.pm = None
        self.known_addresses = {}
    
    def attach_to_process(self) -> bool:
        """Attach to PES6 process."""
        if not MEMORY_AVAILABLE:
            logger.error("Memory scanning libraries not available")
            return False
        
        try:
            self.pm = pymem.Pymem(self.process_name)
            logger.info(f"Attached to process: {self.process_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to attach to process {self.process_name}: {e}")
            return False
    
    def scan_for_rating_value(self, rating_value: float, data_type: str = 'float') -> List[int]:
        """
        Scan memory for a specific rating value.
        Returns list of memory addresses where the value was found.
        """
        if not self.pm:
            logger.error("Not attached to process")
            return []
        
        addresses = []
        
        try:
            if data_type == 'float':
                # Search for float value
                search_value = struct.pack('f', rating_value)
            elif data_type == 'int':
                # Search for integer (scaled by 10, e.g., 7.5 -> 75)
                search_value = struct.pack('i', int(rating_value * 10))
            else:
                logger.error(f"Unsupported data type: {data_type}")
                return []
            
            # Scan memory regions
            for module in self.pm.list_modules():
                try:
                    module_base = module.lpBaseOfDll
                    module_size = module.SizeOfImage
                    
                    # Read module memory
                    memory_data = self.pm.read_bytes(module_base, module_size)
                    
                    # Search for the value
                    offset = 0
                    while True:
                        pos = memory_data.find(search_value, offset)
                        if pos == -1:
                            break
                        
                        address = module_base + pos
                        addresses.append(address)
                        offset = pos + 1
                        
                except Exception as e:
                    # Skip modules we can't read
                    continue
            
            logger.info(f"Found {len(addresses)} potential addresses for value {rating_value}")
            return addresses
            
        except Exception as e:
            logger.error(f"Error scanning memory: {e}")
            return []
    
    def monitor_addresses(self, addresses: List[int], duration: int = 60) -> Dict[int, List[float]]:
        """
        Monitor specific memory addresses for changes over time.
        Returns dictionary mapping addresses to lists of values.
        """
        if not self.pm:
            logger.error("Not attached to process")
            return {}
        
        results = {addr: [] for addr in addresses}
        start_time = time.time()
        
        while time.time() - start_time < duration:
            for addr in addresses:
                try:
                    # Read as float
                    value_bytes = self.pm.read_bytes(addr, 4)
                    value = struct.unpack('f', value_bytes)[0]
                    
                    # Only store reasonable rating values
                    if 0 <= value <= 10:
                        results[addr].append(value)
                        
                except Exception:
                    # Address might be invalid now
                    continue
            
            time.sleep(1)  # Check every second
        
        return results

class PES6RatingManager:
    """
    Main manager class that coordinates different extraction methods.
    """
    
    def __init__(self, db_path: str = "pes6_league_db.sqlite"):
        self.db_path = db_path
        self.ocr_extractor = OCRRatingExtractor(db_path) if OCR_AVAILABLE else None
        self.memory_extractor = MemoryRatingExtractor(db_path) if MEMORY_AVAILABLE else None
    
    def extract_ratings_interactive(self) -> List[Dict]:
        """
        Interactive rating extraction - prompts user to position game correctly.
        """
        print("\n=== PES6 Rating Extraction ===")
        print("1. Play a PES6 league match")
        print("2. Wait for the post-match rating screen")
        print("3. Press Enter when ready to extract ratings...")
        input()
        
        ratings = []
        
        # Try OCR method first
        if self.ocr_extractor:
            print("Attempting OCR extraction...")
            ocr_ratings = self.ocr_extractor.extract_ratings_ocr()
            if ocr_ratings:
                ratings.extend(ocr_ratings)
                print(f"OCR extracted {len(ocr_ratings)} ratings")
        
        # Try memory scanning as backup
        if self.memory_extractor and not ratings:
            print("OCR failed, attempting memory scanning...")
            if self.memory_extractor.attach_to_process():
                # This would require known addresses or scanning
                print("Memory scanning requires manual address discovery")
                print("Use Cheat Engine to find rating addresses first")
        
        return ratings
    
    def manual_input_ratings(self) -> List[Dict]:
        """
        Manual input method for recording ratings.
        """
        print("\n=== Manual Rating Input ===")
        ratings = []
        
        # Get list of players from database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, player_name FROM players ORDER BY player_name")
        players = cursor.fetchall()
        conn.close()
        
        print("Available players:")
        for i, (player_id, name) in enumerate(players[:20]):  # Show first 20
            print(f"{i+1}. {name} (ID: {player_id})")
        
        print("\nEnter ratings (format: player_id:rating or 'done' to finish):")
        
        while True:
            user_input = input("Rating: ").strip().lower()
            
            if user_input == 'done':
                break
            
            try:
                if ':' in user_input:
                    player_id, rating = user_input.split(':')
                    player_id = int(player_id)
                    rating = float(rating)
                    
                    if 0 <= rating <= 10:
                        ratings.append({
                            'player_id': player_id,
                            'rating': rating,
                            'extraction_method': 'manual'
                        })
                        print(f"Added rating {rating} for player {player_id}")
                    else:
                        print("Rating must be between 0 and 10")
                else:
                    print("Format: player_id:rating (e.g., 123:7.5)")
                    
            except ValueError:
                print("Invalid format. Use: player_id:rating")
        
        return ratings
    
    def export_ratings_report(self, days: int = 30) -> str:
        """
        Export recent ratings to CSV report.
        """
        conn = sqlite3.connect(self.db_path)
        
        query = """
            SELECT 
                p.player_name,
                p.club_id,
                mr.rating,
                mr.match_date,
                mr.position_played,
                mr.minutes_played,
                mr.extraction_method
            FROM match_ratings mr
            JOIN players p ON mr.player_id = p.id
            WHERE mr.match_date >= datetime('now', '-{} days')
            ORDER BY mr.match_date DESC
        """.format(days)
        
        import pandas as pd
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        filename = f"pes6_ratings_report_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False)
        
        logger.info(f"Ratings report exported to {filename}")
        return filename

def main():
    """Main function demonstrating usage."""
    print("PES6 Player Rating Extractor")
    print("============================")
    
    manager = PES6RatingManager()
    
    while True:
        print("\nChoose extraction method:")
        print("1. OCR Screen Capture (automated)")
        print("2. Manual Input")
        print("3. Calibrate OCR Screen Regions")
        print("4. Export Ratings Report")
        print("5. Memory Scanning (advanced)")
        print("6. Exit")
        
        choice = input("Enter choice (1-6): ").strip()
        
        if choice == '1':
            if OCR_AVAILABLE:
                ratings = manager.extract_ratings_interactive()
                if ratings:
                    manager.ocr_extractor.save_ratings(ratings, 'ocr')
                    print(f"Saved {len(ratings)} ratings to database")
                else:
                    print("No ratings extracted. Check calibration and screen position.")
            else:
                print("OCR libraries not installed")
        
        elif choice == '2':
            ratings = manager.manual_input_ratings()
            if ratings:
                manager.ocr_extractor.save_ratings(ratings, 'manual')
                print(f"Saved {len(ratings)} ratings to database")
        
        elif choice == '3':
            if manager.ocr_extractor:
                manager.ocr_extractor.calibrate_screen_regions()
            else:
                print("OCR not available")
        
        elif choice == '4':
            filename = manager.export_ratings_report()
            print(f"Report exported to {filename}")
        
        elif choice == '5':
            if MEMORY_AVAILABLE and manager.memory_extractor:
                print("Memory scanning requires manual setup with Cheat Engine first.")
                print("1. Use Cheat Engine to find rating memory addresses")
                print("2. Input found addresses into this script")
                print("3. Run automated memory monitoring")
                # Advanced users would implement this
            else:
                print("Memory scanning libraries not installed")
        
        elif choice == '6':
            break
        
        else:
            print("Invalid choice")

if __name__ == "__main__":
    main()