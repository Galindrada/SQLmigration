import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost'
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD') or 'your_mysql_password'
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'pes6_league_db'

    # New: File Upload Configuration
    UPLOAD_FOLDER = 'static/uploads' # Path relative to app.py
    # Allowed image and video extensions
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi', 'mov', 'webp'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # 16 MB limit for uploads
