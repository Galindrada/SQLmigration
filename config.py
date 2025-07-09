import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'

    # File Upload Configuration
    UPLOAD_FOLDER = 'static/uploads' # Path relative to app.py
    # Allowed image and video extensions
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi', 'mov', 'webp'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # 16 MB limit for uploads

    # SQLite DB path
    SQLITE_DB_PATH = os.environ.get('SQLITE_DB_PATH') or 'pes6_league_db.sqlite'
