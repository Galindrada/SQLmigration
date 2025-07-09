import sqlite3
from flask import g
from config import Config

DATABASE = getattr(Config, 'SQLITE_DB_PATH', 'pes6_league_db.sqlite')

# Flask app context: store connection in g

def get_connection():
    if 'db_conn' not in g:
        g.db_conn = sqlite3.connect(DATABASE)
        g.db_conn.row_factory = sqlite3.Row
        g.db_conn.execute('PRAGMA foreign_keys = ON;')
    return g.db_conn

def get_cursor():
    return get_connection().cursor()

def commit():
    get_connection().commit()

# Optional: close connection at end of request
from flask import current_app
from flask import has_app_context

def close_connection(e=None):
    db_conn = g.pop('db_conn', None)
    if db_conn is not None:
        db_conn.close()

# In your app factory or main file, register this:
# from db_helper import close_connection
# app.teardown_appcontext(close_connection) 