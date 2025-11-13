import os
import json
import sqlite3
import random
from datetime import datetime, timedelta
import time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, send_from_directory, session, Response, make_response
from io import StringIO
import csv
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
import db_helper
import game_mechanics  # Import the new game mechanics module

from config import Config
import db_helper  # New helper module for SQLite access

# Market Bazaar Activity Toggle
MARKET_BAZAAR_ENABLED = True  # Set to False to disable automatic market activity

def get_next_market_activity_time():
    """Get the next market activity time (3 hours from now)"""
    return (datetime.now() + timedelta(minutes=180000)).isoformat()

def update_market_activity_timer():
    """Update the market activity timer in the database"""
    next_time = get_next_market_activity_time()
    cur = db_helper.get_cursor()
    cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('next_market_activity', ?)",
               (next_time,))
    db_helper.commit()
    cur.close()
    return next_time

def check_and_run_scheduled_market_activity():
    """Check if it's time to run scheduled market activity and execute it once"""
    cur = db_helper.get_cursor()
    try:
        # Get current time and stored times
        now = datetime.now()
        cur.execute("SELECT value FROM app_settings WHERE key = 'next_market_activity'")
        next_time_row = cur.fetchone()
        cur.execute("SELECT value FROM app_settings WHERE key = 'last_market_activity_run'")
        last_run_row = cur.fetchone()

        if not next_time_row:
            return False

        next_time = datetime.fromisoformat(next_time_row[0])
        last_run = datetime.fromisoformat(last_run_row[0]) if last_run_row else datetime.min

        # Check if it's time to run and hasn't run yet for this cycle
        if now >= next_time and last_run < next_time:
            # Check lock to prevent simultaneous runs
            cur.execute("SELECT value FROM app_settings WHERE key = 'market_activity_running'")
            running_check = cur.fetchone()

            if running_check and running_check[0] == 'true':
                return False  # Already running

            # Set lock
            cur.execute("""
                INSERT OR REPLACE INTO app_settings (key, value, updated_at)
                VALUES ('market_activity_running', 'true', CURRENT_TIMESTAMP)
            """)
            db_helper.commit()

            try:
                # Run the scheduled activity
                from cpu_ai import cpu_ai

                # Trigger CPU AI activity
                cpu_result = cpu_ai.process_cpu_ai_actions()

                # Process expired offers
                from app import check_expired_offers
                check_expired_offers()

                # Create blog post
                actions_count = cpu_result.get('actions_count', 0)
                actions_taken = cpu_result.get('actions_taken', [])

                if actions_count > 0:
                    actions_taken = cpu_result.get('actions_taken', [])
                    blog_title = f"⚡ Scheduled Market Activity - {actions_count} Actions Taken"
                    blog_content = f"🤖 <strong>Automated Market Activity Report</strong><br><br>The scheduled market activity has completed with <strong>{actions_count}</strong> CPU actions taken.<br><br>"
                    if actions_taken:
                        blog_content += "<strong>Actions:</strong><br><ul>"
                        for action in actions_taken[:10]:  # Limit to 10 for brevity
                            blog_content += f"<li>{action}</li>"
                        blog_content += "</ul>"
                    blog_content += "<br><em>This activity runs automatically every 3 hours.</em>"
                    post_transfer_news(blog_title, blog_content, user_id=1)

                # Update last run time
                cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('last_market_activity_run', ?)", (now.isoformat(),))

                # Update next activity time
                next_activity_time = get_next_market_activity_time()
                cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('next_market_activity', ?)", (next_activity_time,))

                db_helper.commit()
                app.logger.info(f"Scheduled market activity completed at {now}, next at {next_activity_time}")
                return True

            finally:
                # Unlock
                cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('market_activity_running', 'false')")
                db_helper.commit()

        return False

    except Exception as e:
        app.logger.error(f"Error in check_and_run_scheduled_market_activity: {e}")
        return False
    finally:
        cur.close()

app = Flask(__name__)
app.config.from_object(Config)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Ensure the upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Define DOWNLOAD_FOLDER for generated CSVs
DOWNLOAD_FOLDER = os.path.join(app.root_path, 'static', 'downloads')
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Register DB connection teardown
from db_helper import close_connection
app.teardown_appcontext(close_connection)

# User model for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

    @staticmethod
    def get(user_id):
        cur = db_helper.get_cursor()
        cur.execute("SELECT id, username, email FROM users WHERE id = ?", (user_id,))
        user_data = cur.fetchone()
        cur.close()
        if user_data:
            return User(user_data[0], user_data[1], user_data[2])
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# --- Helper function for file uploads ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_media_type(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'}:
        return 'image'
    elif ext in {'mp4', 'avi', 'mov'}:
        return 'video'
    return 'none'

# --- Jinja2 Filter for Currency Formatting ---
@app.template_filter('format_currency')
def format_currency_filter(value):
    if isinstance(value, (int, float)):
        return f"€{value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return value

@app.template_filter('format_currency_compact')
def format_currency_compact_filter(value):
    """Format currency in compact format (e.g., 1.1M for 1,100,000)"""
    if not isinstance(value, (int, float)) or value is None:
        return "0"
    value = float(value)
    if value >= 1000000:
        # Round to nearest 100K
        millions = round(value / 100000) / 10
        return f"{millions:.1f}M"
    elif value >= 1000:
        # Round to nearest 1K
        thousands = round(value / 100) / 10
        return f"{thousands:.1f}K"
    else:
        return f"{int(value)}"

@app.template_filter('from_json')
def from_json_filter(value):
    if value is None:
        return []
    try:
        return json.loads(value)
    except:
        return []
# --- END Jinja2 Filter ---

# --- Routes ---

@app.route('/')
def index():
    cur = db_helper.get_cursor()
    cur.execute("""
        SELECT p.id, p.title, p.content, u.username, p.created_at, p.media_type, p.media_path
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC LIMIT 5
    """)
    recent_posts = [dict(row) for row in cur.fetchall()]
    cur.close()
    return render_template('index.html', recent_posts=recent_posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    cur = db_helper.get_cursor()
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    pes6_teams_for_selection = cur.fetchall()
    cur.close()

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        selected_team_ids = request.form.getlist('selected_teams') # Get list of selected team IDs

        if len(selected_team_ids) == 0:
            flash('Please select at least 1 team to manage.', 'danger')
            return render_template('register.html', teams=pes6_teams_for_selection,
                                   old_username=username, old_email=email) # Pass back data

        new_user_id = None
        try:
            cur = db_helper.get_cursor()
            # Insert new user
            cur.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                        (username, email, hashed_password))
            db_helper.commit()
            new_user_id = cur.lastrowid # Get the ID of the newly created user

            # Process all selected teams
            for pes6_team_id_str in selected_team_ids:
                pes6_team_id = int(pes6_team_id_str)
                # Get the name of the selected PES6 team
                cur.execute("SELECT club_name FROM teams WHERE id = ?", (pes6_team_id,))
                pes6_team_name_result = cur.fetchone()
                if not pes6_team_name_result:
                    raise Exception(f"Selected PES6 team with ID {pes6_team_id} not found.")
                pes6_team_name = pes6_team_name_result[0]

                # Check if this team is already managed by another human user (not CPU)
                cur.execute("SELECT user_id FROM league_teams WHERE team_name = ? AND user_id IS NOT NULL AND user_id != 1", (pes6_team_name,))
                existing_team = cur.fetchone()
                if existing_team and existing_team[0] != new_user_id:
                    raise Exception(f"Team '{pes6_team_name}' is already managed by another user.")

                # Create or update league team for this user
                cur.execute("SELECT id FROM league_teams WHERE team_name = ?", (pes6_team_name,))
                league_team = cur.fetchone()
                if league_team:
                    league_team_id = league_team[0]
                    cur.execute("UPDATE league_teams SET user_id = ? WHERE id = ?", (new_user_id, league_team_id))
                else:
                    cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (?, ?)", (new_user_id, pes6_team_name))
                    league_team_id = cur.lastrowid

                # Repopulate team_players for this team
                cur.execute("DELETE FROM team_players WHERE team_id = ?", (league_team_id,))
                cur.execute("SELECT id FROM players WHERE club_id = ?", (pes6_team_id,))
                players_in_pes6_team = cur.fetchall()
                if players_in_pes6_team:
                    player_team_data = [(league_team_id, player[0]) for player in players_in_pes6_team]
                    cur.executemany("INSERT INTO team_players (team_id, player_id) VALUES (?, ?)", player_team_data)

            db_helper.commit()

            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            db_helper.get_connection().rollback()
            # If user was created but team creation failed, try to clean up user (optional, complex)
            if new_user_id:
                try:
                    cur.execute("DELETE FROM users WHERE id = ?", (new_user_id,))
                    db_helper.commit()
                    flash(f"Error during team setup for new user. User account rolled back. Please try again. Error: {e}", 'danger')
                except Exception as cleanup_e:
                    flash(f"Error during registration and cleanup failed. Contact admin. Error: {e}, Cleanup Error: {cleanup_e}", 'danger')
            else:
                flash(f'Registration failed: {e}', 'danger')
            app.logger.error(f"Registration Error: {e}", exc_info=True)
            return render_template('register.html', teams=pes6_teams_for_selection,
                                   old_username=username, old_email=email) # Pass back data

        finally:
            cur.close()

    return render_template('register.html', teams=pes6_teams_for_selection)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cur = db_helper.get_cursor()
        cur.execute("SELECT id, username, password, email FROM users WHERE username = ?", (username,))
        user_data = cur.fetchone()
        cur.close()

        if user_data and check_password_hash(user_data[2], password):
            user = User(user_data[0], user_data[1], user_data[3])
            login_user(user)
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/dashboard/user_deals', methods=['GET', 'POST'])
@login_required
def dashboard_user_deals():
    cur = db_helper.get_cursor()

    # Ensure user has an active team
    active_team_id = session.get('active_team_id')
    if not active_team_id:
        # Get user's first team as active
        cur.execute("SELECT id FROM league_teams WHERE user_id = ? ORDER BY id LIMIT 1", (current_user.id,))
        first_team = cur.fetchone()
        if first_team:
            active_team_id = first_team['id']
            session['active_team_id'] = active_team_id

    # Get user's teams for selection
    cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = ? ORDER BY team_name", (current_user.id,))
    my_teams = cur.fetchall()

    # Exclude CPU users (user_id = 1) and current user from the list
    cur.execute("SELECT id, username FROM users WHERE id != ? AND id != 1 ORDER BY username ASC", (current_user.id,))
    users = cur.fetchall()

    # Get current user's team players (from all teams)
    cur.execute("""
        SELECT p.id, p.player_name, p.registered_position, p.market_value, lt.team_name
        FROM players p
        JOIN teams t ON p.club_id = t.id
        JOIN league_teams lt ON t.club_name = lt.team_name
        WHERE lt.user_id = ?
        ORDER BY lt.team_name, p.player_name ASC
    """, (current_user.id,))
    my_players = cur.fetchall()

    recipient_players = []
    selected_receiver_id = request.form.get('receiver_id') if request.method == 'POST' else request.args.get('receiver_id')
    selected_my_team_id = request.form.get('my_team_id') if request.method == 'POST' else request.args.get('my_team_id', active_team_id)
    selected_their_team_id = request.form.get('their_team_id') if request.method == 'POST' else request.args.get('their_team_id')

    if selected_receiver_id:
        try:
            selected_receiver_id_int = int(selected_receiver_id)
            # Get recipient's teams
            cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = ? ORDER BY team_name", (selected_receiver_id_int,))
            recipient_teams = cur.fetchall()

            # Get recipient's team players (from all teams)
            cur.execute("""
                SELECT p.id, p.player_name, p.registered_position, p.market_value, lt.team_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.club_name = lt.team_name
                WHERE lt.user_id = ?
                ORDER BY lt.team_name, p.player_name ASC
            """, (selected_receiver_id_int,))
            recipient_players = cur.fetchall()
        except ValueError:
            recipient_players = []

    cur.close()

    if request.method == 'POST':
        receiver_id = request.form['receiver_id']
        my_team_id = request.form.get('my_team_id', active_team_id)
        their_team_id = request.form.get('their_team_id')
        offered_players = request.form.getlist('offered_players')
        offered_money = int(request.form.get('offered_money', 0) or 0)
        requested_players = request.form.getlist('requested_players')
        requested_money = int(request.form.get('requested_money', 0) or 0)

        # Validate that at least one side has something to offer
        if not offered_players and offered_money == 0 and not requested_players and requested_money == 0:
            flash('You must offer something or request something!', 'danger')
            return render_template('dashboard_user_deals.html',
                                users=users,
                                my_players=my_players,
                                recipient_players=recipient_players,
                                selected_receiver_id=selected_receiver_id,
                                my_teams=my_teams,
                                recipient_teams=recipient_teams if 'recipient_teams' in locals() else [],
                                selected_my_team_id=selected_my_team_id,
                                selected_their_team_id=selected_their_team_id)

        cur = db_helper.get_cursor()
        # For user-to-user offers, we need to provide a player_id (use the first offered player or a default)
        default_player_id = offered_players[0] if offered_players else requested_players[0] if requested_players else None

        if default_player_id:
            cur.execute("""
                INSERT INTO offers (sender_id, receiver_id, player_id, offer_amount, offered_players, offered_money, requested_players, requested_money, sender_team_id, receiver_team_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (current_user.id, receiver_id, default_player_id, offered_money, json.dumps(offered_players), offered_money, json.dumps(requested_players), requested_money, my_team_id, their_team_id, 'pending'))
        else:
            # If no players involved, we can't create an offer with the current schema
            flash('You must include at least one player in the offer!', 'danger')
            return render_template('dashboard_user_deals.html',
                                users=users,
                                my_players=my_players,
                                recipient_players=recipient_players,
                                selected_receiver_id=selected_receiver_id,
                                my_teams=my_teams,
                                recipient_teams=recipient_teams if 'recipient_teams' in locals() else [],
                                selected_my_team_id=selected_my_team_id,
                                selected_their_team_id=selected_their_team_id)
        db_helper.commit()
        cur.close()
        flash('Offer sent!', 'success')
        return redirect(url_for('dashboard'))

    # Get current user's pending offers (sent and received)
    cur = db_helper.get_cursor()
    cur.execute("""
        SELECT o.id, o.sender_id, o.receiver_id, o.status, o.created_at,
               u1.username as sender_name, u2.username as receiver_name,
               o.offered_players, o.offered_money, o.requested_players, o.requested_money
        FROM offers o
        JOIN users u1 ON o.sender_id = u1.id
        JOIN users u2 ON o.receiver_id = u2.id
        WHERE (o.sender_id = ? OR o.receiver_id = ?) AND o.status != 'deleted'
        ORDER BY o.created_at DESC
    """, (current_user.id, current_user.id))
    current_deals = cur.fetchall()
    cur.close()

    return render_template('dashboard_user_deals.html',
                         users=users,
                         my_players=my_players,
                         recipient_players=recipient_players,
                         selected_receiver_id=selected_receiver_id,
                         my_teams=my_teams,
                         recipient_teams=recipient_teams if 'recipient_teams' in locals() else [],
                         selected_my_team_id=selected_my_team_id,
                         selected_their_team_id=selected_their_team_id,
                         current_deals=current_deals)

@app.route('/dashboard/clear_completed_offers', methods=['POST'])
@login_required
def clear_completed_offers():
    cur = db_helper.get_cursor()
    cur.execute("""
        UPDATE offers
        SET status = 'deleted'
        WHERE (sender_id = ? OR receiver_id = ?)
        AND status IN ('accepted', 'rejected')
    """, (current_user.id, current_user.id))
    db_helper.commit()
    cur.close()
    flash('Completed offers cleared!', 'success')
    return redirect(url_for('dashboard_user_deals'))

@app.route('/finances')
@login_required
def finances():
    # Get user's unified budget
    current_budget = get_user_budget(current_user.id)

    # Calculate total salaries across all user's teams
    cur = db_helper.get_cursor()
    cur.execute("""
        SELECT COALESCE(SUM(p.salary), 0) as total_salaries
        FROM players p
        JOIN teams t ON p.club_id = t.id
        JOIN league_teams lt ON t.club_name = lt.team_name
        WHERE lt.user_id = ?
    """, (current_user.id,))
    salary_result = cur.fetchone()
    total_salaries = salary_result['total_salaries'] if salary_result else 0

    # Calculate available cap
    available_cap = current_budget - int(total_salaries/2) # UPDATE HERE BY THE END OF SEASON TO FULL SALARY

    # Get transaction movements
    cur.execute("""
        SELECT type, description, amount, balance_after, created_at
        FROM user_movements
        WHERE user_id = ?
        ORDER BY datetime(created_at) DESC, rowid DESC
        LIMIT 50
    """, (current_user.id,))
    movements_raw = cur.fetchall()

    # Convert to dictionaries and add type colors for badges
    movements = []
    for movement in movements_raw:
        movement_dict = dict(movement)

        # Convert created_at string to datetime object for template
        if movement_dict['created_at']:
            try:
                movement_dict['created_at'] = datetime.fromisoformat(movement_dict['created_at'].replace('Z', '+00:00'))
            except:
                # If conversion fails, keep as string
                pass

        if movement_dict['type'] == 'Transfer Out':
            movement_dict['type_color'] = 'danger'
        elif movement_dict['type'] == 'Transfer In':
            movement_dict['type_color'] = 'success'
        elif movement_dict['type'] == 'CPU Negotiation':
            movement_dict['type_color'] = 'warning'
        elif movement_dict['type'] == 'User Deal':
            movement_dict['type_color'] = 'info'
        elif movement_dict['type'] == 'Free Agency':
            movement_dict['type_color'] = 'info'
        elif movement_dict['type'] == 'Signing Bonus':
            movement_dict['type_color'] = 'danger'
        else:
            movement_dict['type_color'] = 'secondary'
        movements.append(movement_dict)

    cur.close()

    return render_template('finances.html',
                         current_budget=current_budget,
                         total_salaries=total_salaries,
                         available_cap=available_cap,
                         movements=movements)

@app.route('/blog')
def blog():
    cur = db_helper.get_cursor()
    cur.execute("""
        SELECT p.id, p.title, p.content, u.username, p.created_at, p.media_type, p.media_path
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
    """)
    posts = [dict(row) for row in cur.fetchall()]

    # Convert datetime strings to datetime objects
    from datetime import datetime
    for post in posts:
        if post['created_at']:
            post['created_at'] = datetime.fromisoformat(post['created_at'].replace('Z', '+00:00'))

    cur.close()
    return render_template('blog.html', posts=posts)

@app.route('/blog/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        user_id = current_user.id
        media_type = 'none'
        media_path = None

        if not title or not content:
            flash('Title and content are required.', 'danger')
            return redirect(url_for('create_post'))

        if 'media_file' in request.files:
            file = request.files['media_file']
            if file.filename == '':
                flash('No selected file', 'warning')
            elif file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                full_upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(full_upload_path)
                media_type = get_media_type(filename)
                media_path = filename

        cur = db_helper.get_cursor()
        try:
            cur.execute("INSERT INTO posts (user_id, title, content, media_type, media_path) VALUES (?, ?, ?, ?, ?)",
                        (user_id, title, content, media_type, media_path))
            db_helper.commit()
            flash('Post created successfully!', 'success')
            return redirect(url_for('blog'))
        except Exception as e:
            db_helper.get_connection().rollback()
            flash(f'Error creating post: {e}', 'danger')
        finally:
            cur.close()
    return render_template('create_post.html')

@app.route('/blog/post/<int:post_id>', methods=['GET', 'POST'])
def view_post(post_id):
    cur = db_helper.get_cursor()
    cur.execute("""
        SELECT p.id, p.title, p.content, u.username, p.created_at, p.media_type, p.media_path
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.id = ?
    """, (post_id,))
    post = cur.fetchone()

    if not post:
        flash('Post not found.', 'danger')
        return redirect(url_for('blog'))

    # Convert post to dict and handle datetime
    post = dict(post)
    if post['created_at']:
        from datetime import datetime
        post['created_at'] = datetime.fromisoformat(post['created_at'].replace('Z', '+00:00'))

    cur.execute("""
        SELECT c.content, u.username, c.created_at
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.post_id = ?
        ORDER BY c.created_at ASC
    """, (post_id,))
    comments = [dict(row) for row in cur.fetchall()]

    # Convert datetime strings to datetime objects for comments
    from datetime import datetime
    for comment in comments:
        if comment['created_at']:
            comment['created_at'] = datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00'))

    cur.close()

    if request.method == 'POST' and current_user.is_authenticated:
        comment_content = request.form['comment_content']
        user_id = current_user.id

        if not comment_content:
            flash('Comment cannot be empty.', 'danger')
            return redirect(url_for('view_post', post_id=post_id))

        cur = db_helper.get_cursor()
        try:
            cur.execute("INSERT INTO comments (post_id, user_id, content) VALUES (?, ?, ?)",
                        (post_id, user_id, comment_content))
            db_helper.commit()
            flash('Comment added successfully!', 'success')
            return redirect(url_for('view_post', post_id=post_id))
        except Exception as e:
            db_helper.get_connection().rollback()
            flash(f'Error adding comment: {e}', 'danger')
        finally:
            cur.close()
    return render_template('view_post.html', post=post, comments=comments)


@app.route('/team_management')
@login_required
def team_management():
    cur = db_helper.get_cursor()
    cur.execute("SELECT id, team_name, budget FROM league_teams WHERE user_id = ?", (current_user.id,))
    user_teams_meta = cur.fetchall() # Fetch all teams this user manages
    cur.close()

    # Get active team from session, or default to first team
    active_team_id = session.get('active_team_id')
    if not active_team_id:
        if user_teams_meta:
            active_team_id = user_teams_meta[0]['id']
            session['active_team_id'] = active_team_id
        else:
            active_team_id = None

    managed_teams_data = []
    total_salaries_user_teams = 0 # Initialize total salaries for financial summary

    # Get unified budget
    user_total_budget = get_user_budget(current_user.id)

    for team_meta in user_teams_meta:
        team_id = team_meta['id']
        team_name = team_meta['team_name']

        cur = db_helper.get_cursor()
        # Fetch players for this specific team using club_id to ensure consistency with PES6 teams view
        cur.execute("""
            SELECT
                p.id, p.player_name, p.age, p.game_position, p.strong_foot, p.salary, p.contract_years_remaining, p.market_value
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE t.club_name = ?
            ORDER BY
                CASE p.game_position
                    WHEN 'Goal-Keeper' THEN 1
                    WHEN 'Sweeper' THEN 2
                    WHEN 'Centre-Back' THEN 3
                    WHEN 'Side-Back' THEN 4
                    WHEN 'Wing-Back' THEN 5
                    WHEN 'Defensive Midfielder' THEN 6
                    WHEN 'Center-Midfielder' THEN 7
                    WHEN 'Side-Midfielder' THEN 8
                    WHEN 'Attacking Midfielder' THEN 9
                    WHEN 'Winger' THEN 10
                    WHEN 'Shadow Striker' THEN 11
                    WHEN 'Striker' THEN 12
                    ELSE 13
                END ASC
        """, (team_name,))
        team_players_roster = cur.fetchall()
        cur.close()

        # Sum salaries for this team
        team_salary_sum = sum(p['salary'] for p in team_players_roster if p['salary'] is not None)
        total_salaries_user_teams += team_salary_sum

        managed_teams_data.append({
            'id': team_id,
            'name': team_name,
            'players': team_players_roster,
            'team_salary_sum': team_salary_sum, # Optionally pass per-team salary sum
            'is_active': team_id == active_team_id
        })

    # Calculate financial summary for the user's managed teams
    free_cap_user_teams = user_total_budget - total_salaries_user_teams

    # Check if user can create more teams (removed limit for multiple teams)
    can_create_team = True

    # Get loaned players for all user teams
    loaned_players = []
    if user_teams_meta:
        user_team_names = [team['team_name'] for team in user_teams_meta]

        cur = db_helper.get_cursor()
        # Find players that are currently loaned out by any of the user's teams
        placeholders = ','.join(['?' for _ in user_team_names])
        cur.execute(f"""
            SELECT
                p.id, p.player_name, p.age, p.game_position, p.salary,
                p.market_value, p.loaned_by, t.club_name as current_team
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE p.loaned_by IN ({placeholders})
            ORDER BY p.loaned_by, p.player_name
        """, user_team_names)
        loaned_players = cur.fetchall()
        cur.close()

    return render_template('team_management.html',
                           managed_teams=managed_teams_data,
                           can_create_team=can_create_team,
                           coach_username=current_user.username,
                           total_budget_display=user_total_budget,
                           total_salaries_user_teams=total_salaries_user_teams,
                           free_cap_user_teams=free_cap_user_teams,
                           active_team_id=active_team_id,
                           loaned_players=loaned_players)

@app.route('/team_management/create', methods=['POST'])
@login_required
def create_team():
    team_name = request.form['team_name']
    user_id = current_user.id

    # Check if team name already exists
    cur = db_helper.get_cursor()
    cur.execute("SELECT id FROM league_teams WHERE team_name = ?", (team_name,))
    existing_team = cur.fetchone()
    cur.close()

    if existing_team:
        flash(f'Team "{team_name}" already exists.', 'danger')
        return redirect(url_for('team_management'))

    cur = db_helper.get_cursor()
    try:
        cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (?, ?)",
                    (user_id, team_name))
        db_helper.commit()
        flash(f'Team "{team_name}" created successfully!', 'success')
    except Exception as e:
        db_helper.get_connection().rollback()
        flash(f'Error creating team: {e}', 'danger')
    finally:
        cur.close()
    return redirect(url_for('team_management'))

@app.route('/team_management/switch_team/<int:team_id>', methods=['POST'])
@login_required
def switch_active_team(team_id):
    """Switch the active team for the current user."""
    cur = db_helper.get_cursor()

    # Verify the team belongs to the current user
    cur.execute("SELECT id FROM league_teams WHERE id = ? AND user_id = ?", (team_id, current_user.id))
    team = cur.fetchone()
    cur.close()

    if not team:
        flash('Invalid team selected.', 'danger')
        return redirect(url_for('team_management'))

    # Set the active team in session
    session['active_team_id'] = team_id
    flash('Active team switched successfully!', 'success')
    return redirect(url_for('team_management'))

@app.route('/team_management/add_player', methods=['POST'])
@login_required
def add_player_to_team():
    player_id = request.form['player_id'] # This player_id comes from a form field, assuming user picked from a list
    team_id = request.form['team_id'] # New: need to know which of the user's teams to add to

    cur = db_helper.get_cursor()
    # Verify the team_id belongs to the current user
    cur.execute("SELECT id FROM league_teams WHERE id = ? AND user_id = ?", (team_id, current_user.id))
    user_team_check = cur.fetchone()
    cur.close()

    if not user_team_check:
        flash('Invalid team selected for adding player.', 'danger')
        return redirect(url_for('team_management'))

    cur = db_helper.get_cursor()
    try:
        # Optional: Check if player is already in ANY of the user's teams, or a specific team
        # For this design, let's allow a player to be in only ONE of a user's teams
        cur.execute("SELECT tp.player_id FROM team_players tp JOIN league_teams lt ON tp.team_id = lt.id WHERE lt.user_id = ? AND tp.player_id = ?", (current_user.id, player_id))
        player_already_in_user_teams = cur.fetchone()
        if player_already_in_user_teams:
            flash("This player is already in one of your managed teams!", "warning")
            return redirect(url_for('team_management'))

        # Insert player into the specified team
        cur.execute("INSERT INTO team_players (team_id, player_id) VALUES (?, ?)",
                    (team_id, player_id))

        # Update the player's club_id to match the corresponding PES6 team
        cur.execute("SELECT team_name FROM league_teams WHERE id = ?", (team_id,))
        team_name = cur.fetchone()[0]

        # Find the corresponding PES6 team ID
        cur.execute("SELECT id FROM teams WHERE club_name = ?", (team_name,))
        pes6_team_result = cur.fetchone()
        if pes6_team_result:
            pes6_team_id = pes6_team_result[0]
            # Update the player's club_id
            cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (pes6_team_id, player_id))

        db_helper.commit()
        flash('Player added to your team!', 'success')
    except Exception as e:
            db_helper.get_connection().rollback()
            flash(f'Error adding player: {e}', 'danger')
    finally:
            cur.close()
    return redirect(url_for('team_management'))

@app.route('/team_management/remove_player/<int:team_id>/<int:player_id>', methods=['POST'])
@login_required
def remove_player_from_team(team_id, player_id): # Team ID added to parameters
    # Verify the team_id belongs to the current user
    cur = db_helper.get_cursor()
    cur.execute("SELECT id FROM league_teams WHERE id = ? AND user_id = ?", (team_id, current_user.id))
    user_team_check = cur.fetchone()
    cur.close()

    if not user_team_check:
        flash('Invalid team selected for removing player.', 'danger')
        return redirect(url_for('team_management'))

    cur = db_helper.get_cursor()
    try:
        cur.execute("DELETE FROM team_players WHERE team_id = ? AND player_id = ?",
                    (team_id, player_id))

        # Clear the player's club_id since they're no longer assigned to any team
        cur.execute("UPDATE players SET club_id = NULL WHERE id = ?", (player_id,))

        db_helper.commit()
        flash('Player removed from your team!', 'success')
    except Exception as e:
            db_helper.get_connection().rollback()
            flash(f'Error removing player: {e}', 'danger')
    finally:
            cur.close()
    return redirect(url_for('team_management'))

# --- New Routes for PES6 Game Data ---

@app.route('/pes6_game_teams')
def pes6_game_teams():
    cur = db_helper.get_cursor()
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    game_teams = cur.fetchall()
    # Get all team names from league_teams that are managed by a real user (user_id != 1)
    cur.execute("SELECT team_name FROM league_teams WHERE user_id != 1")
    user_assigned_team_names = set(row[0] for row in cur.fetchall())
    cur.close()
    return render_template('pes6_teams.html', game_teams=game_teams, user_assigned_team_names=user_assigned_team_names)

@app.route('/pes6_game_teams/<int:team_id>')
def pes6_team_details(team_id):
    cur = db_helper.get_cursor()
    cur.execute("SELECT club_name, total_salaries, budget, available_cap FROM teams WHERE id = ?", (team_id,))
    team_data = cur.fetchone()
    if not team_data:
        flash("PES6 Team not found!", "danger")
        return redirect(url_for('pes6_game_teams'))

    team_name = team_data[0]

    # Check if this team is managed by a user (not CPU)
    cur.execute("SELECT user_id FROM league_teams WHERE team_name = ? AND user_id != 1", (team_name,))
    user_managed = cur.fetchone()

    # Always calculate financial data dynamically to ensure accuracy
    cur.execute("SELECT COALESCE(SUM(salary), 0) as total_salaries FROM players WHERE club_id = ?", (team_id,))
    salary_result = cur.fetchone()
    total_salaries = salary_result[0] if salary_result else 0

    # Calculate total market value
    cur.execute("SELECT SUM(market_value) as total_market_value FROM players WHERE club_id = ?", (team_id,))
    total_market_value_result = cur.fetchone()
    total_market_value = total_market_value_result['total_market_value'] or 0

    if user_managed:
        # For user-managed teams, don't show individual team budget (use unified budget)
        budget = 0  # Hide budget for user teams
        available_cap = 0  # Hide available cap for user teams
        is_user_team = True
    else:
        # For CPU teams, show actual budget
        budget = team_data[2] if team_data[2] is not None else 400000000
        available_cap = budget - total_salaries
        is_user_team = False

    # Fetch players with fresh data - ensure we get the most up-to-date information
    cur.execute("""
        SELECT id, player_name, registered_position, age, height, strong_foot, attack,
               attack_rating, defense_rating, physical_rating, power_rating, technique_rating, goalkeeping_rating,
               game_position, salary, contract_years_remaining, market_value, championships_won, cups_won
        FROM players
        WHERE club_id = ?
        ORDER BY
            CASE game_position
                WHEN 'Goal-Keeper' THEN 1
                WHEN 'Sweeper' THEN 2
                WHEN 'Centre-Back' THEN 3
                WHEN 'Side-Back' THEN 4
                WHEN 'Wing-Back' THEN 5
                WHEN 'Defensive Midfielder' THEN 6
                WHEN 'Center-Midfielder' THEN 7
                WHEN 'Side-Midfielder' THEN 8
                WHEN 'Attacking Midfielder' THEN 9
                WHEN 'Winger' THEN 10
                WHEN 'Shadow Striker' THEN 11
                WHEN 'Striker' THEN 12
                ELSE 13
            END ASC
    """, (team_id,))
    players_in_team = cur.fetchall()
    
    # Fetch team historical data
    cur.execute("""
        SELECT season, competition, place
        FROM team_historical_data
        WHERE team_id = ?
        ORDER BY season DESC, competition ASC
    """, (team_id,))
    historical_data = cur.fetchall()
    cur.close()

    # Add cache-busting headers to ensure fresh data
    response = make_response(render_template('pes6_team_details.html',
                         team_name=team_name,
                         team_id=team_id,
                         players_in_team=players_in_team,
                         total_salaries=total_salaries,
                         budget=budget,
                         available_cap=available_cap,
                         is_user_team=is_user_team,
                         total_market_value=total_market_value,
                         historical_data=historical_data))

    # Add headers to prevent caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response


@app.route('/pes6_player/<int:player_id>')
def pes6_player_details(player_id):
    cur = db_helper.get_cursor()
    cur.execute("SELECT * FROM players WHERE id = ?", (player_id,))
    player_data = cur.fetchone()

    if not player_data:
        cur.close()
        flash("PES6 Player not found!", "danger")
        return redirect(url_for('pes6_game_teams'))

    # Update game_position from registered_position to ensure it's current
    position_mapping = {
        '0': 'Goal-Keeper',
        '2': 'Sweeper',
        '3': 'Centre-Back',
        '4': 'Side-Back',
        '5': 'Defensive Midfielder',
        '6': 'Wing-Back',
        '7': 'Center-Midfielder',
        '8': 'Side-Midfielder',
        '9': 'Attacking Midfielder',
        '10': 'Winger',
        '11': 'Shadow Striker',
        '12': 'Striker',
        '13': 'Unknown'
    }

    current_game_position = position_mapping.get(str(player_data['registered_position']), 'Unknown')

    # Update game_position in database if it's different
    if player_data['game_position'] != current_game_position:
        cur.execute("UPDATE players SET game_position = ? WHERE id = ?", (current_game_position, player_id))
        db_helper.commit()
        # Refresh player data after update
        cur.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        player_data = cur.fetchone()

    basic_info = {
        'Name': player_data['player_name'],
        'Age': player_data['age'],
        'Height': player_data['height'],
        'Weight': player_data['weight'],
        'Nationality': player_data['nationality'],
        'Strong Foot': player_data['strong_foot'],
        'Favoured Side': player_data['favoured_side'],
        'Registered Position': player_data['registered_position'],
        'Game Position': current_game_position,  # Use updated position
        'Games': player_data['games_played'] if 'games_played' in player_data.keys() else 0,
        'Assists': player_data['assists'] if 'assists' in player_data.keys() else 0,
        'Goals': player_data['goals'] if 'goals' in player_data.keys() else 0
    }

    # Add loan information if player is on loan
    if player_data['loaned_by'] and player_data['loaned_by'] != '':
        temp_cur = db_helper.get_cursor()
        temp_cur.execute("SELECT club_name FROM teams WHERE id = ?", (player_data['loaned_by'],))
        loaned_to_result = temp_cur.fetchone()
        if loaned_to_result:
            basic_info['On Loan To'] = loaned_to_result[0]
        temp_cur.close()

    club_name = None
    if player_data['club_id']:
        temp_cur = db_helper.get_cursor()
        temp_cur.execute("SELECT club_name FROM teams WHERE id = ?", (player_data['club_id'],))
        club_name_result = temp_cur.fetchone()
        if club_name_result:
            club_name = club_name_result[0]
        temp_cur.close()
    basic_info['Club'] = club_name

    # Display career earnings as stored in database (starts at 0, increases during end-of-season)
    career_earnings = player_data['career_earnings'] if player_data['career_earnings'] else 0

    financial_info = {
        'Salary': player_data['salary'],
        'Contract Years': player_data['contract_years_remaining'],
        'Market Value': player_data['market_value'],
        'Yearly Wage Rise': player_data['yearly_wage_rise'],
        'Career Earnings': career_earnings
    }

    cur.close()

    # Bundled skill ratings - use database columns for consistency with team roster
    bundled_skills = {
        'Attack': player_data['attack_rating'] if player_data['attack_rating'] else (player_data['attack'] + player_data['shot_technique'] +
                 player_data['shot_accuracy'] + player_data['aggression']) // 4,
        'Defense': player_data['defense_rating'] if player_data['defense_rating'] else (player_data['defense'] + player_data['heading'] + player_data['jump'] + player_data['balance']) // 4,
        'Physical': player_data['physical_rating'] if player_data['physical_rating'] else (player_data['stamina'] + player_data['top_speed'] +
                    player_data['acceleration'] + player_data['response'] +
                    player_data['agility'] + player_data['jump']) // 6,
        'Power': player_data['power_rating'] if player_data['power_rating'] else (player_data['shot_power'] + player_data['balance'] +
                 player_data['mentality']) // 3,
        'Technique': player_data['technique_rating'] if player_data['technique_rating'] else (player_data['technique'] + player_data['swerve'] +
                    player_data['free_kick_accuracy'] + player_data['dribble_accuracy'] +
                    player_data['dribble_speed'] + player_data['short_pass_accuracy'] +
                    player_data['short_pass_speed'] + player_data['long_pass_accuracy'] +
                    player_data['long_pass_speed']) // 9,
        'Goalkeeping': player_data['goalkeeping_rating'] if player_data['goalkeeping_rating'] else (player_data['defense'] + player_data['goal_keeping'] +
                      player_data['response'] + player_data['agility']) // 4
    }

    skills_numeric = {
        'Attack': player_data['attack'],
        'Defense': player_data['defense'],
        'Balance': player_data['balance'],
        'Stamina': player_data['stamina'],
        'Top Speed': player_data['top_speed'],
        'Acceleration': player_data['acceleration'],
        'Response': player_data['response'],
        'Agility': player_data['agility'],
        'Dribble Accuracy': player_data['dribble_accuracy'],
        'Dribble Speed': player_data['dribble_speed'],
        'Short Pass Accuracy': player_data['short_pass_accuracy'],
        'Short Pass Speed': player_data['short_pass_speed'],
        'Long Pass Accuracy': player_data['long_pass_accuracy'],
        'Long Pass Speed': player_data['long_pass_speed'],
        'Shot Accuracy': player_data['shot_accuracy'],
        'Shot Power': player_data['shot_power'],
        'Shot Technique': player_data['shot_technique'],
        'Free Kick Accuracy': player_data['free_kick_accuracy'],
        'Swerve': player_data['swerve'],
        'Heading': player_data['heading'],
        'Jump': player_data['jump'],
        'Technique': player_data['technique'],
        'Aggression': player_data['aggression'],
        'Mentality': player_data['mentality'],
        'Goal Keeping': player_data['goal_keeping'],
        'Team Work': player_data['team_work'],
        'Consistency': player_data['consistency'],
        'Condition / Fitness': player_data['condition_fitness'],
    }

    positional_skills = {
        'GK': player_data['gk'], 'CWP': player_data['cwp'], 'CBT': player_data['cbt'],
        'SB': player_data['sb'], 'DMF': player_data['dmf'], 'WB': player_data['wb'],
        'CMF': player_data['cmf'], 'SMF': player_data['smf'], 'AMF': player_data['amf'],
        'WF': player_data['wf'], 'SS': player_data['ss'], 'CF': player_data['cf']
    }

    special_skills = {
        'Dribbling': player_data['dribbling_skill'],
        'Tactical Dribble': player_data['tactical_dribble'],
        'Positioning': player_data['positioning'],
        'Reaction': player_data['reaction'],
        'Playmaking': player_data['playmaking'],
        'Passing': player_data['passing'],
        'Scoring': player_data['scoring'],
        '1-on-1 Scoring': player_data['one_one_scoring'],
        'Post Player': player_data['post_player'],
        'Lines': player_data['lines'],
        'Middle Shooting': player_data['middle_shooting'],
        'Side': player_data['side'],
        'Centre': player_data['centre'],
        'Penalties': player_data['penalties'],
        '1-Touch Pass': player_data['one_touch_pass'],
        'Outside': player_data['outside'],
        'Marking': player_data['marking'],
        'Sliding': player_data['sliding'],
        'Covering': player_data['covering'],
        'D-Line Control': player_data['d_line_control'],
        'Penalty Stopper': player_data['penalty_stopper'],
        '1-on-1 Stopper': player_data['one_on_one_stopper'],
        'Long Throw': player_data['long_throw'],
    }


    # Get player historical data
    history_cur = db_helper.get_cursor()
    history_cur.execute("""
        SELECT season, club_name, games_played, goals, assists, salary
        FROM player_season_history
        WHERE player_id = ?
        ORDER BY season DESC
    """, (player_id,))
    player_history = history_cur.fetchall()
    history_cur.close()

    return render_template('pes6_player_details.html',
                           player=player_data,
                           basic_info=basic_info,
                           financial_info=financial_info, # Pass new financial_info dictionary
                           bundled_skills=bundled_skills,
                           skills_numeric=skills_numeric,
                           player_history=player_history,
                           positional_skills=positional_skills,
                           special_skills=special_skills)

# --- NEW ROUTES FOR TOOLS PAGE AND CSV DOWNLOAD ---
@app.route('/tools')
def tools():
    cur = db_helper.get_cursor()
    # Get players with age and team info for retire player tool
    cur.execute("""
        SELECT p.id, p.player_name, p.age, t.club_name
        FROM players p
        JOIN teams t ON p.club_id = t.id
        ORDER BY p.player_name ASC
    """)
    players = cur.fetchall()
    # Get players with financial info for the salary tool
    cur.execute("SELECT id, player_name, salary, contract_years_remaining, yearly_wage_rise FROM players ORDER BY player_name ASC")
    players_salary = cur.fetchall()
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    teams = cur.fetchall()
    # Get distinct nationalities for retire player tool
    cur.execute("SELECT DISTINCT nationality FROM players WHERE nationality IS NOT NULL ORDER BY nationality ASC")
    nationalities = [row[0] for row in cur.fetchall()]
    cur.close()

    # Get season message from flash if available
    season_message = None

    return render_template('tools.html', players=players, players_salary=players_salary, teams=teams, nationalities=nationalities, season_message=season_message)

@app.route('/download_updated_csv')
@login_required # Often good to require login for tools/downloads
def download_updated_csv():
    try:
        # Read the original CSV file to get header and data
        original_csv_path = os.path.join(app.root_path, 'pe6_player_data.csv')
        if not os.path.exists(original_csv_path):
            flash("Original CSV file not found.", "danger")
            return redirect(url_for('tools'))

        # Read the original CSV to get header and preserve original data for missing columns
        # Try different encodings to handle the original CSV file
        encodings_to_try = ['latin-1', 'iso-8859-1', 'utf-8-sig', 'utf-8', 'cp1252']
        df_original = None

        for encoding in encodings_to_try:
            try:
                df_original = pd.read_csv(original_csv_path, encoding=encoding)
                break
            except UnicodeDecodeError:
                continue

        if df_original is None:
            flash("Error reading original CSV file - unable to decode with any supported encoding", "danger")
            return redirect(url_for('tools'))
        original_header = df_original.columns.tolist()

        # Fetch all player data from the current database
        cur = db_helper.get_cursor()
        cur.execute("""
            SELECT
                p.id, p.player_name, p.shirt_name, p.gk, p.cwp, p.cbt, p.sb, p.dmf, p.wb,
                p.cmf, p.smf, p.amf, p.wf, p.ss, p.cf, p.registered_position, p.height,
                p.strong_foot, p.favoured_side,
                p.attack, p.defense, p.balance, p.stamina, p.top_speed, p.acceleration,
                p.response, p.agility, p.dribble_accuracy, p.dribble_speed, p.short_pass_accuracy,
                p.short_pass_speed, p.long_pass_accuracy, p.long_pass_speed, p.shot_accuracy,
                p.shot_power, p.shot_technique, p.free_kick_accuracy, p.swerve, p.heading,
                p.jump, p.technique, p.aggression, p.mentality, p.goal_keeping, p.team_work,
                p.consistency, p.condition_fitness, p.dribbling_skill, p.tactical_dribble,
                p.positioning, p.reaction, p.playmaking, p.passing, p.scoring, p.one_one_scoring,
                p.post_player, p.lines, p.middle_shooting, p.side, p.centre, p.penalties,
                p.one_touch_pass, p.outside, p.marking, p.sliding, p.covering, p.d_line_control,
                p.penalty_stopper, p.one_on_one_stopper, p.long_throw, p.injury_tolerance,
                p.dribble_style, p.free_kick_style, p.pk_style, p.drop_kick_style, p.age,
                p.weight, p.nationality, p.skin_color, p.face_type, p.preset_face_number,
                p.head_width, p.neck_length, p.neck_width, p.shoulder_height, p.shoulder_width,
                p.chest_measurement, p.waist_circumference, p.arm_circumference, p.leg_circumference,
                p.calf_circumference, p.leg_length, p.wristband, p.wristband_color,
                p.international_number, p.classic_number, p.club_number,
                CASE
                    WHEN t.club_name IS NULL OR t.club_name = 'No Club' OR t.csv_visible = 0 THEN ''
                    ELSE t.club_name
                END AS club_team_raw,
                p.salary, p.contract_years_remaining, p.market_value, p.yearly_wage_rise
            FROM players p
            LEFT JOIN teams t ON p.club_id = t.id
            ORDER BY p.id
        """)
        players_data = cur.fetchall()

        # Get column names from the cursor description BEFORE closing
        column_names = [description[0] for description in cur.description]
        cur.close()

        if not players_data:
            flash("No player data available to export.", "warning")
            return redirect(url_for('tools'))

        # Create DataFrame from database data with proper column names
        df_players = pd.DataFrame(players_data, columns=column_names)

        # Map database columns to original CSV headers
        db_to_csv_map = {
            'id': 'ID',
            'player_name': 'NAME',
            'shirt_name': 'SHIRT_NAME',
            'gk': 'GK  0',
            'cwp': 'CWP  2',
            'cbt': 'CBT  3',
            'sb': 'SB  4',
            'dmf': 'DMF  5',
            'wb': 'WB  6',
            'cmf': 'CMF  7',
            'smf': 'SMF  8',
            'amf': 'AMF  9',
            'wf': 'WF 10',
            'ss': 'SS  11',
            'cf': 'CF  12',
            'registered_position': 'REGISTERED POSITION',
            'height': 'HEIGHT',
            'strong_foot': 'STRONG FOOT',
            'favoured_side': 'FAVOURED SIDE',
            'attack': 'ATTACK',
            'defense': 'DEFENSE',
            'balance': 'BALANCE',
            'stamina': 'STAMINA',
            'top_speed': 'TOP SPEED',
            'acceleration': 'ACCELERATION',
            'response': 'RESPONSE',
            'agility': 'AGILITY',
            'dribble_accuracy': 'DRIBBLE ACCURACY',
            'dribble_speed': 'DRIBBLE SPEED',
            'short_pass_accuracy': 'SHORT PASS ACCURACY',
            'short_pass_speed': 'SHORT PASS SPEED',
            'long_pass_accuracy': 'LONG PASS ACCURACY',
            'long_pass_speed': 'LONG PASS SPEED',
            'shot_accuracy': 'SHOT ACCURACY',
            'shot_power': 'SHOT POWER',
            'shot_technique': 'SHOT TECHNIQUE',
            'free_kick_accuracy': 'FREE KICK ACCURACY',
            'swerve': 'SWERVE',
            'heading': 'HEADING',
            'jump': 'JUMP',
            'technique': 'TECHNIQUE',
            'aggression': 'AGGRESSION',
            'mentality': 'MENTALITY',
            'goal_keeping': 'GOAL KEEPING',
            'team_work': 'TEAM WORK',
            'consistency': 'CONSISTENCY',
            'condition_fitness': 'CONDITION / FITNESS',
            'dribbling_skill': 'DRIBBLING',
            'tactical_dribble': 'TACTIAL DRIBBLE',
            'positioning': 'POSITIONING',
            'reaction': 'REACTION',
            'playmaking': 'PLAYMAKING',
            'passing': 'PASSING',
            'scoring': 'SCORING',
            'one_one_scoring': '1-1 SCORING',
            'post_player': 'POST PLAYER',
            'lines': 'LINES',
            'middle_shooting': 'MIDDLE SHOOTING',
            'side': 'SIDE',
            'centre': 'CENTRE',
            'penalties': 'PENALTIES',
            'one_touch_pass': '1-TOUCH PASS',
            'outside': 'OUTSIDE',
            'marking': 'MARKING',
            'sliding': 'SLIDING',
            'covering': 'COVERING',
            'd_line_control': 'D-LINE CONTROL',
            'penalty_stopper': 'PENALTY STOPPER',
            'one_on_one_stopper': '1-ON-1 STOPPER',
            'long_throw': 'LONG THROW',
            'injury_tolerance': 'INJURY TOLERANCE',
            'dribble_style': 'DRIBBLE STYLE',
            'free_kick_style': 'FREE KICK STYLE',
            'pk_style': 'PK STYLE',
            'drop_kick_style': 'DROP KICK STYLE',
            'age': 'AGE',
            'weight': 'WEIGHT',
            'nationality': 'NATIONALITY',
            'skin_color': 'SKIN COLOR',
            'face_type': 'FACE TYPE',
            'preset_face_number': 'PRESET FACE NUMBER',
            'head_width': 'HEAD WIDTH',
            'neck_length': 'NECK LENGTH',
            'neck_width': 'NECK WIDTH',
            'shoulder_height': 'SHOULDER HEIGHT',
            'shoulder_width': 'SHOULDER WIDTH',
            'chest_measurement': 'CHEST MEASUREMENT',
            'waist_circumference': 'WAIST CIRCUMFERENCE',
            'arm_circumference': 'ARM CIRCUMFERENCE',
            'leg_circumference': 'LEG CIRCUMFERENCE',
            'calf_circumference': 'CALF CIRCUMFERENCE',
            'leg_length': 'LEG LENGTH',
            'wristband': 'WRISTBAND',
            'wristband_color': 'WRISTBAND COLOR',
            'international_number': 'INTERNATIONAL NUMBER',
            'classic_number': 'CLASSIC NUMBER',
            'club_number': 'CLUB NUMBER',
            'club_team_raw': 'CLUB TEAM',
            'salary': 'SALARY',
            'contract_years_remaining': 'CONTRACT YEARS REMAINING',
            'market_value': 'MARKET VALUE',
            'yearly_wage_rise': 'YEARLY WAGE RISE'
        }

        # Rename columns to match original CSV headers
        df_players = df_players.rename(columns=db_to_csv_map)

        # Create a new DataFrame with the exact original header order
        df_output = pd.DataFrame()

        # Use only the original header (no financial columns added)
        original_header_only = original_header

        # Populate the DataFrame with data in the original header order
        for col in original_header_only:
            if col in df_players.columns:
                if col == 'CLUB TEAM':
                    # Special handling for club team - use the database value
                    df_output[col] = df_players[col]
                else:
                    df_output[col] = df_players[col]
            else:
                # For missing columns, only fall back to original CSV data for specific missing columns
                # (like WEAK FOOT ACCURACY and WEAK FOOT FREQUENCY that don't exist in database)
                if col in df_original.columns:
                    # Only use original data for columns that are actually missing from database
                    # For regen players (ID > 5184), fill with default values instead of original data
                    if col in ['WEAK FOOT ACCURACY', 'WEAK FOOT FREQUENCY']:
                        # These columns don't exist in database, generate random values (3-8)
                        import random
                        df_output[col] = random.randint(3, 8)  # Random value between 3-8
                    else:
                        # For other missing columns, use original data
                        df_output[col] = df_original[col]
                else:
                    # Fill missing columns with empty string
                    df_output[col] = ''

        # Fill NaN values appropriately and ensure proper data types
        for col in df_output.columns:
            if col in ['NAME', 'SHIRT_NAME', 'NATIONALITY', 'STRONG FOOT', 'FAVOURED SIDE', 'INJURY TOLERANCE', 'WRISTBAND', 'WRISTBAND COLOR', 'CLUB TEAM']:
                # Text columns - fill with empty string
                df_output[col] = df_output[col].fillna('').astype(str)
            elif col in ['AGE', 'HEIGHT', 'WEIGHT', 'GK  0', 'CWP  2', 'CBT  3', 'SB  4', 'DMF  5', 'WB  6', 'CMF  7', 'SMF  8', 'AMF  9', 'WF 10', 'SS  11', 'CF  12', 'REGISTERED POSITION', 'WEAK FOOT ACCURACY', 'WEAK FOOT FREQUENCY', 'ATTACK', 'DEFENSE', 'BALANCE', 'STAMINA', 'TOP SPEED', 'ACCELERATION', 'RESPONSE', 'AGILITY', 'DRIBBLE ACCURACY', 'DRIBBLE SPEED', 'SHORT PASS ACCURACY', 'SHORT PASS SPEED', 'LONG PASS ACCURACY', 'LONG PASS SPEED', 'SHOT ACCURACY', 'SHOT POWER', 'SHOT TECHNIQUE', 'FREE KICK ACCURACY', 'SWERVE', 'HEADING', 'JUMP', 'TECHNIQUE', 'AGGRESSION', 'MENTALITY', 'GOAL KEEPING', 'TEAM WORK', 'CONSISTENCY', 'CONDITION / FITNESS', 'DRIBBLING', 'TACTIAL DRIBBLE', 'POSITIONING', 'REACTION', 'PLAYMAKING', 'PASSING', 'SCORING', '1-1 SCORING', 'POST PLAYER', 'LINES', 'MIDDLE SHOOTING', 'SIDE', 'CENTRE', 'PENALTIES', '1-TOUCH PASS', 'OUTSIDE', 'MARKING', 'SLIDING', 'COVERING', 'D-LINE CONTROL', 'PENALTY STOPPER', '1-ON-1 STOPPER', 'LONG THROW', 'DRIBBLE STYLE', 'FREE KICK STYLE', 'PK STYLE', 'DROP KICK STYLE', 'SKIN COLOR', 'FACE TYPE', 'PRESET FACE NUMBER', 'HEAD WIDTH', 'NECK LENGTH', 'NECK WIDTH', 'SHOULDER HEIGHT', 'SHOULDER WIDTH', 'CHEST MEASUREMENT', 'WAIST CIRCUMFERENCE', 'ARM CIRCUMFERENCE', 'LEG CIRCUMFERENCE', 'CALF CIRCUMFERENCE', 'LEG LENGTH', 'INTERNATIONAL NUMBER', 'CLASSIC NUMBER', 'CLUB NUMBER']:
                # Numeric columns - fill with 0
                df_output[col] = df_output[col].fillna(0).astype(int)
            else:
                # Other columns - fill with empty string
                df_output[col] = df_output[col].fillna('').astype(str)

        # Fix character encoding issues in player names
        def fix_encoding(text):
            if pd.isna(text) or text == '':
                return text
            # Convert to string and handle Unicode properly
            text = str(text)

            # Try to normalize any problematic characters
            try:
                import unicodedata
                text = unicodedata.normalize('NFC', text)
            except ImportError:
                pass

            # Fix common UTF-8 encoding issues - comprehensive mapping
            encoding_fixes = {
                # Common Latin characters
                'ï¿½': 'á', 'ï¿½': 'à', 'ï¿½': 'â', 'ï¿½': 'ä', 'ï¿½': 'ã', 'ï¿½': 'å', 'ï¿½': 'æ',
                'ï¿½': 'é', 'ï¿½': 'è', 'ï¿½': 'ê', 'ï¿½': 'ë', 'ï¿½': 'í', 'ï¿½': 'ì', 'ï¿½': 'î', 'ï¿½': 'ï',
                'ï¿½': 'ó', 'ï¿½': 'ò', 'ï¿½': 'ô', 'ï¿½': 'ö', 'ï¿½': 'õ', 'ï¿½': 'ø', 'ï¿½': 'œ',
                'ï¿½': 'ú', 'ï¿½': 'ù', 'ï¿½': 'û', 'ï¿½': 'ü', 'ï¿½': 'ý', 'ï¿½': 'ÿ',
                'ï¿½': 'ñ', 'ï¿½': 'ç', 'ï¿½': 'ß', 'ï¿½': 'Ð', 'ï¿½': 'Þ',
                # Uppercase versions
                'ï¿½': 'Á', 'ï¿½': 'À', 'ï¿½': 'Â', 'ï¿½': 'Ä', 'ï¿½': 'Ã', 'ï¿½': 'Å', 'ï¿½': 'Æ',
                'ï¿½': 'É', 'ï¿½': 'È', 'ï¿½': 'Ê', 'ï¿½': 'Ë', 'ï¿½': 'Í', 'ï¿½': 'Ì', 'ï¿½': 'Î', 'ï¿½': 'Ï',
                'ï¿½': 'Ó', 'ï¿½': 'Ò', 'ï¿½': 'Ô', 'ï¿½': 'Ö', 'ï¿½': 'Õ', 'ï¿½': 'Ø', 'ï¿½': 'Œ',
                'ï¿½': 'Ú', 'ï¿½': 'Ù', 'ï¿½': 'Û', 'ï¿½': 'Ü', 'ï¿½': 'Ý', 'ï¿½': 'Ÿ',
                'ï¿½': 'Ñ', 'ï¿½': 'Ç', 'ï¿½': 'Ð', 'ï¿½': 'Þ',
                # Symbols and currency
                'ï¿½': '€', 'ï¿½': '£', 'ï¿½': '¥', 'ï¿½': '¢', 'ï¿½': '§', 'ï¿½': '©', 'ï¿½': '®', 'ï¿½': '™',
                'ï¿½': '°', 'ï¿½': '±', 'ï¿½': '×', 'ï¿½': '÷', 'ï¿½': '≠', 'ï¿½': '≤', 'ï¿½': '≥', 'ï¿½': '∞',
                'ï¿½': '≈', 'ï¿½': '∑', 'ï¿½': '∏', 'ï¿½': '∂', 'ï¿½': '∫', 'ï¿½': '∆', 'ï¿½': '∇',
                'ï¿½': '∈', 'ï¿½': '∉', 'ï¿½': '⊂', 'ï¿½': '⊃', 'ï¿½': '∪', 'ï¿½': '∩', 'ï¿½': '∅',
                'ï¿½': '√', 'ï¿½': '∝', 'ï¿½': 'α', 'ï¿½': 'β', 'ï¿½': 'γ', 'ï¿½': 'δ', 'ï¿½': 'ε',
                'ï¿½': 'ζ', 'ï¿½': 'η', 'ï¿½': 'θ', 'ï¿½': 'ι', 'ï¿½': 'κ', 'ï¿½': 'λ', 'ï¿½': 'μ',
                'ï¿½': 'ν', 'ï¿½': 'ξ', 'ï¿½': 'ο', 'ï¿½': 'π', 'ï¿½': 'ρ', 'ï¿½': 'σ', 'ï¿½': 'τ',
                'ï¿½': 'υ', 'ï¿½': 'φ', 'ï¿½': 'χ', 'ï¿½': 'ψ', 'ï¿½': 'ω'
            }

            for bad_char, good_char in encoding_fixes.items():
                text = text.replace(bad_char, good_char)

            return text

        # Apply encoding fixes to text columns
        for col in ['NAME', 'SHIRT_NAME', 'NATIONALITY']:
            if col in df_output.columns:
                df_output[col] = df_output[col].apply(fix_encoding)

        # Additional fix for any remaining problematic characters
        def clean_text(text):
            if pd.isna(text) or text == '':
                return text

            # Convert to string if not already
            text = str(text)

            # Normalize Unicode characters and remove combining characters
            import unicodedata
            text = unicodedata.normalize('NFD', text)

            # Remove all combining characters (like \u0308 - combining diaeresis)
            text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')

            # Replace problematic characters with latin-1 compatible equivalents
            replacements = {
                'ź': 'z', 'ż': 'z', 'ń': 'n', 'ć': 'c', 'ś': 's', 'ą': 'a', 'ę': 'e', 'ł': 'l', 'ó': 'o',
                'Ź': 'Z', 'Ż': 'Z', 'Ń': 'N', 'Ć': 'C', 'Ś': 'S', 'Ą': 'A', 'Ę': 'E', 'Ł': 'L', 'Ó': 'O',
                'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ý': 'y',
                'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U', 'Ý': 'Y',
                'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u',
                'À': 'A', 'È': 'E', 'Ì': 'I', 'Ò': 'O', 'Ù': 'U',
                'â': 'a', 'ê': 'e', 'î': 'i', 'ô': 'o', 'û': 'u',
                'Â': 'A', 'Ê': 'E', 'Î': 'I', 'Ô': 'O', 'Û': 'U',
                'ä': 'a', 'ë': 'e', 'ï': 'i', 'ö': 'o', 'ü': 'u', 'ÿ': 'y',
                'Ä': 'A', 'Ë': 'E', 'Ï': 'I', 'Ö': 'O', 'Ü': 'U', 'Ÿ': 'Y',
                'ç': 'c', 'Ç': 'C',
                'ñ': 'n', 'Ñ': 'N',
                'ß': 'ss',
                'ı': 'i', 'İ': 'I',  # Turkish dotless i and dotted I
                'ğ': 'g', 'Ğ': 'G',  # Turkish g with breve
                'ş': 's', 'Ş': 'S',  # Turkish s with cedilla
                'ü': 'u', 'Ü': 'U',  # Turkish u with diaeresis
                'ö': 'o', 'Ö': 'O',  # Turkish o with diaeresis
                'æ': 'ae', 'Æ': 'AE',  # Latin ligatures
                'œ': 'oe', 'Œ': 'OE',
                'Đ': 'D', 'đ': 'd',  # Latin D with stroke (Croatian/Serbian)
                'Ð': 'D', 'ð': 'd',  # Latin D with stroke (Icelandic)
                'Þ': 'Th', 'þ': 'th',  # Latin Thorn (Icelandic)
                'Œ': 'OE', 'œ': 'oe',  # Latin ligatures
                'Ÿ': 'Y', 'ÿ': 'y',  # Latin Y with diaeresis
                'Ź': 'Z', 'ź': 'z',  # Latin Z with acute
                'Ż': 'Z', 'ż': 'z',  # Latin Z with dot above
                'Ž': 'Z', 'ž': 'z',  # Latin Z with caron
                'Š': 'S', 'š': 's',  # Latin S with caron
                'Č': 'C', 'č': 'c',  # Latin C with caron
                'Ć': 'C', 'ć': 'c',  # Latin C with acute
                'Đ': 'D', 'đ': 'd',  # Latin D with stroke
                'Ň': 'N', 'ň': 'n',  # Latin N with caron
                'Ř': 'R', 'ř': 'r',  # Latin R with caron
                'Ť': 'T', 'ť': 't',  # Latin T with caron
                'Ů': 'U', 'ů': 'u',  # Latin U with ring above
                'Ý': 'Y', 'ý': 'y',  # Latin Y with acute
                'Á': 'A', 'á': 'a',  # Latin A with acute
                'É': 'E', 'é': 'e',  # Latin E with acute
                'Í': 'I', 'í': 'i',  # Latin I with acute
                'Ó': 'O', 'ó': 'o',  # Latin O with acute
                'Ú': 'U', 'ú': 'u',  # Latin U with acute
                'Ý': 'Y', 'ý': 'y',  # Latin Y with acute
                'À': 'A', 'à': 'a',  # Latin A with grave
                'È': 'E', 'è': 'e',  # Latin E with grave
                'Ì': 'I', 'ì': 'i',  # Latin I with grave
                'Ò': 'O', 'ò': 'o',  # Latin O with grave
                'Ù': 'U', 'ù': 'u',  # Latin U with grave
                'Â': 'A', 'â': 'a',  # Latin A with circumflex
                'Ê': 'E', 'ê': 'e',  # Latin E with circumflex
                'Î': 'I', 'î': 'i',  # Latin I with circumflex
                'Ô': 'O', 'ô': 'o',  # Latin O with circumflex
                'Û': 'U', 'û': 'u',  # Latin U with circumflex
                'Ä': 'A', 'ä': 'a',  # Latin A with diaeresis
                'Ë': 'E', 'ë': 'e',  # Latin E with diaeresis
                'Ï': 'I', 'ï': 'i',  # Latin I with diaeresis
                'Ö': 'O', 'ö': 'o',  # Latin O with diaeresis
                'Ü': 'U', 'ü': 'u',  # Latin U with diaeresis
                'Ÿ': 'Y', 'ÿ': 'y'   # Latin Y with diaeresis
            }

            for old_char, new_char in replacements.items():
                text = text.replace(old_char, new_char)

            # Remove any remaining problematic characters
            text = text.replace('\x00', '')  # Remove null bytes
            text = text.replace('\ufffd', '?')  # Replace replacement characters

            return text

        # Apply to all text columns
        for col in df_output.columns:
            if df_output[col].dtype == 'object':  # Text columns
                df_output[col] = df_output[col].apply(clean_text)

        # Export with the original header
        output_filename = 'pe6_player_data_updated.csv'
        output_filepath = os.path.join(DOWNLOAD_FOLDER, output_filename)

        # Write the CSV with latin-1 encoding for PES6 compatibility
        df_output.to_csv(output_filepath, index=False, encoding='latin-1')

        return send_from_directory(DOWNLOAD_FOLDER, output_filename, as_attachment=True)

    except Exception as e:
        flash(f"Error generating or downloading CSV: {e}", "danger")
        app.logger.error(f"Error in download_updated_csv: {e}", exc_info=True)
        return redirect(url_for('tools'))

# --- NEW ROUTE FOR ADMIN FINANCIAL SUMMARY ---
# This route is being removed as per user request
# @app.route('/admin/financial_summary')
# @login_required
# def admin_financial_summary():
#     TOTAL_LEAGUE_BUDGET = 450000000
#

#     cur.execute("SELECT SUM(salary) FROM players")
#     total_player_salaries = cur.fetchone()[0]
#     cur.close()
#
#     total_player_salaries = total_player_salaries if total_player_salaries is not None else 0
#     available_budget = TOTAL_LEAGUE_BUDGET - total_player_salaries
#
#     return render_template('admin_financial_summary.html',
#                            total_budget=TOTAL_LEAGUE_BUDGET,
#                            total_player_salaries=total_player_salaries,
#                            available_budget=available_budget)

@app.route('/inbox')
@login_required
def inbox():
    cur = db_helper.get_cursor()
    cur.execute("""
        SELECT m.*, u.username AS sender_username
        FROM messages m
        LEFT JOIN users u ON m.sender_id = u.id
        WHERE m.receiver_id = ?
        ORDER BY m.created_at DESC
    """, (current_user.id,))
    messages = cur.fetchall()

    # Convert messages to dict and handle datetime
    messages = [dict(msg) for msg in messages]
    for msg in messages:
        # Convert created_at string to datetime object for template
        if msg['created_at']:
            from datetime import datetime
            try:
                msg['created_at'] = datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00'))
            except:
                # If parsing fails, keep as string
                pass

    # Fetch offers for this user
    cur.execute("""
        SELECT o.*, u.username AS sender_username
        FROM offers o
        JOIN users u ON o.sender_id = u.id
        WHERE o.receiver_id = ?
        ORDER BY o.created_at DESC
    """, (current_user.id,))
    offers = cur.fetchall()
    # After fetching offers, convert each offer to a dict before mutating
    offers = [dict(offer) for offer in offers]
    # Parse JSON fields and fetch player names for template
    for offer in offers:
        if 'offered_players' in offer and 'requested_players' in offer:
            # Defensive: treat None or empty as []
            offered_players_raw = offer['offered_players'] or '[]'
            requested_players_raw = offer['requested_players'] or '[]'
            offer['offered_players'] = json.loads(offered_players_raw)
            offer['requested_players'] = json.loads(requested_players_raw)
            # Fetch player names for both sides
            if offer['offered_players'] and len(offer['offered_players']) > 0:
                placeholders = ','.join(['?' for _ in offer['offered_players']])
                cur.execute("SELECT id, player_name FROM players WHERE id IN ({})".format(placeholders), offer['offered_players'])
                offer['offered_player_names'] = [row['player_name'] for row in cur.fetchall()]
            else:
                offer['offered_player_names'] = []
            if offer['requested_players'] and len(offer['requested_players']) > 0:
                placeholders = ','.join(['?' for _ in offer['requested_players']])
                cur.execute("SELECT id, player_name FROM players WHERE id IN ({})".format(placeholders), offer['requested_players'])
                offer['requested_player_names'] = [row['player_name'] for row in cur.fetchall()]
            else:
                offer['requested_player_names'] = []
            offer['is_cpu_offer'] = (offer['sender_id'] == 1)
            # Determine if it's a buy or sell offer
            if offer['is_cpu_offer']:
                if offer['requested_players'] and len(offer['requested_players']) > 0:
                    placeholders = ','.join(['?' for _ in offer['requested_players']])
                    cur.execute("""
                        SELECT COUNT(*) as count FROM team_players tp
                        JOIN league_teams lt ON tp.team_id = lt.id
                        WHERE tp.player_id IN ({}) AND lt.user_id = ?
                    """.format(placeholders), offer['requested_players'] + [current_user.id])
                    user_players_count = cur.fetchone()['count']
                    offer['is_sell_offer'] = (user_players_count > 0)
                else:
                    offer['is_sell_offer'] = False
            else:
                offer['is_sell_offer'] = False
            # For CPU offers, get the correct CPU team name based on the player(s) involved
            offer['cpu_team_name'] = None
            if offer['is_cpu_offer']:
                player_id = None
                if offer['is_sell_offer'] and offer['offered_players'] and len(offer['offered_players']) > 0:
                    player_id = offer['offered_players'][0]
                elif not offer['is_sell_offer'] and offer['requested_players'] and len(offer['requested_players']) > 0:
                    player_id = offer['requested_players'][0]
                cpu_team_name = None
                if player_id:
                    cur.execute("""
                        SELECT lt.team_name FROM league_teams lt
                        JOIN team_players tp ON lt.id = tp.team_id
                        WHERE lt.user_id = 1 AND tp.player_id = ?
                        LIMIT 1
                    """, (player_id,))
                    cpu_team = cur.fetchone()
                    if cpu_team:
                        cpu_team_name = cpu_team['team_name']
                # If not found, try to get the team name from the offer's data
                if not cpu_team_name and offer['is_sell_offer'] and offer['offered_players'] and len(offer['offered_players']) > 0:
                    # Try to get the team name from the player's club
                    cur.execute("SELECT club_id FROM players WHERE id = ?", (offer['offered_players'][0],))
                    club_row = cur.fetchone()
                    if club_row and club_row['club_id']:
                        cur.execute("SELECT team_name FROM league_teams WHERE user_id = 1 AND team_name = (SELECT club_name FROM teams WHERE id = ?)", (club_row['club_id'],))
                        cpu_team = cur.fetchone()
                        if cpu_team:
                            cpu_team_name = cpu_team['team_name']
                offer['cpu_team_name'] = cpu_team_name if cpu_team_name else 'CPU Team'
        else:
            # Minimal CPU offer: just show player_id and offer_amount
            offer['offered_player_names'] = []
            offer['requested_player_names'] = []
            offer['is_cpu_offer'] = (offer['sender_id'] == 1)
            offer['offered_money'] = 0
            offer['requested_money'] = 0
            offer['is_sell_offer'] = False
            offer['cpu_team_name'] = None
            if 'player_id' in offer:
                cur.execute("SELECT player_name, club_id FROM players WHERE id = ?", (offer['player_id'],))
                player_row = cur.fetchone()
                if player_row:
                    offer['requested_player_names'] = [player_row['player_name']]
                    offer['is_sell_offer'] = (offer['receiver_id'] == current_user.id)
                    offer['offered_money'] = offer.get('offer_amount', 0) if offer['is_sell_offer'] else 0
                    offer['requested_money'] = 0 if offer['is_sell_offer'] else offer.get('offer_amount', 0)
                    # Get CPU team name
                    if player_row['club_id']:
                        cur.execute("SELECT club_name FROM teams WHERE id = ?", (player_row['club_id'],))
                        club = cur.fetchone()
                        if club:
                            offer['cpu_team_name'] = club['club_name']
            # For buy offers, show offered_money as requested_money and vice versa
            if not offer['is_sell_offer']:
                offer['offered_money'], offer['requested_money'] = offer['requested_money'], offer['offered_money']
    cur.close()
    return render_template('inbox.html', messages=messages, offers=offers)

@app.route('/inbox/<int:msg_id>')
@login_required
def view_message(msg_id):
    cur = db_helper.get_cursor()
    cur.execute("SELECT * FROM messages WHERE id = ? AND receiver_id = ?", (msg_id, current_user.id))
    message = cur.fetchone()
    if not message:
        cur.close()
        abort(404)

    # Convert message to dict and handle datetime
    message = dict(message)
    if message['created_at']:
        from datetime import datetime
        try:
            message['created_at'] = datetime.fromisoformat(message['created_at'].replace('Z', '+00:00'))
        except:
            # If parsing fails, keep as string
            pass

    sender_username = None
    if message['sender_id']:
        cur.execute("SELECT username FROM users WHERE id = ?", (message['sender_id'],))
        sender = cur.fetchone()
        if sender:
            sender_username = sender['username']
    cur.close()
    return render_template('view_message.html', message=message, sender_username=sender_username)

@app.route('/inbox/<int:msg_id>/delete', methods=['POST'])
@login_required
def delete_message(msg_id):
    """Delete a message."""
    cur = db_helper.get_cursor()

    # First, verify the message belongs to the current user
    cur.execute("SELECT id FROM messages WHERE id = ? AND receiver_id = ?", (msg_id, current_user.id))
    message = cur.fetchone()

    if not message:
        cur.close()
        return jsonify({'success': False, 'error': 'Message not found or you do not have permission to delete it.'}), 404

    try:
        # Delete the message
        cur.execute("DELETE FROM messages WHERE id = ? AND receiver_id = ?", (msg_id, current_user.id))
        db_helper.commit()
        cur.close()
        return jsonify({'success': True, 'message': 'Message deleted successfully.'})
    except Exception as e:
        db_helper.get_connection().rollback()
        cur.close()
        app.logger.error(f"Error deleting message {msg_id}: {e}")
        return jsonify({'success': False, 'error': 'Database error occurred while deleting message.'}), 500

@app.route('/inbox/send', methods=['GET', 'POST'])
@login_required
def send_message():
    cur = db_helper.get_cursor()
    cur.execute("SELECT id, username FROM users WHERE id != ? ORDER BY username ASC", (current_user.id,))
    users = cur.fetchall()
    cur.close()
    subject = ''
    body = ''
    selected_recipient_id = None
    reply_to = request.args.get('reply_to')
    # If replying, pre-fill subject/body
    if reply_to:
        cur = db_helper.get_cursor()
        cur.execute("SELECT * FROM messages WHERE id = ? AND receiver_id = ?", (reply_to, current_user.id))
        orig = cur.fetchone()
        cur.close()
        if orig:
            subject = 'Re: ' + orig['subject']
            selected_recipient_id = orig['sender_id']
    if request.method == 'POST':
        receiver_id = request.form['recipient_id']
        subject = request.form['subject']
        body = request.form['body']
        if not receiver_id or not subject or not body:
            flash('All fields are required.', 'danger')
        else:
            cur = db_helper.get_cursor()
            cur.execute("INSERT INTO messages (sender_id, receiver_id, subject, content) VALUES (?, ?, ?, ?)",
                        (current_user.id, receiver_id, subject, body))
            db_helper.commit()
            cur.close()
            flash('Message sent!', 'success')
            return redirect(url_for('inbox'))
    return render_template('send_message.html', users=users, subject=subject, body=body, selected_recipient_id=selected_recipient_id)

@app.route('/send_offer', methods=['GET', 'POST'])
@login_required
def send_offer():
    cur = db_helper.get_cursor()
    # Exclude CPU users (user_id = 1) and current user from the list
    cur.execute("SELECT id, username FROM users WHERE id != ? AND id != 1 ORDER BY username ASC", (current_user.id,))
    users = cur.fetchall()

    # Get current user's team players
    cur.execute("""
        SELECT p.id, p.player_name, p.registered_position, p.market_value FROM players p
        JOIN teams t ON p.club_id = t.id
        JOIN league_teams lt ON t.club_name = lt.team_name
        WHERE lt.user_id = ?
        ORDER BY p.player_name ASC
    """, (current_user.id,))
    my_players = cur.fetchall()

    recipient_players = []
    selected_receiver_id = request.form.get('receiver_id') if request.method == 'POST' else request.args.get('receiver_id')

    if selected_receiver_id:
        try:
            selected_receiver_id_int = int(selected_receiver_id)
            # Get recipient's team players
            cur.execute("""
                SELECT p.id, p.player_name, p.registered_position, p.market_value FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.club_name = lt.team_name
                WHERE lt.user_id = ?
                ORDER BY p.player_name ASC
            """, (selected_receiver_id_int,))
            recipient_players = cur.fetchall()
        except ValueError:
            recipient_players = []

    cur.close()

    if request.method == 'POST':
        receiver_id = request.form['receiver_id']
        offered_players = request.form.getlist('offered_players')
        offered_money = int(request.form.get('offered_money', 0) or 0)
        requested_players = request.form.getlist('requested_players')
        requested_money = int(request.form.get('requested_money', 0) or 0)

        # Validate that at least one side has something to offer
        if not offered_players and offered_money == 0 and not requested_players and requested_money == 0:
            flash('You must offer something or request something!', 'danger')
            return render_template('send_offer.html', users=users, my_players=my_players, recipient_players=recipient_players, selected_receiver_id=selected_receiver_id)

        cur = db_helper.get_cursor()
        # For user-to-user offers, we need to provide a player_id (use the first offered player or a default)
        default_player_id = offered_players[0] if offered_players else requested_players[0] if requested_players else None

        if default_player_id:
            cur.execute("""
                INSERT INTO offers (sender_id, receiver_id, player_id, offer_amount, offered_players, offered_money, requested_players, requested_money, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (current_user.id, receiver_id, default_player_id, offered_money, json.dumps(offered_players), offered_money, json.dumps(requested_players), requested_money, 'pending'))
        else:
            # If no players involved, we can't create an offer with the current schema
            flash('You must include at least one player in the offer!', 'danger')
            return render_template('send_offer.html', users=users, my_players=my_players, recipient_players=recipient_players, selected_receiver_id=selected_receiver_id)
        db_helper.commit()
        cur.close()
        flash('Offer sent!', 'success')
        return redirect(url_for('inbox'))

    return render_template('send_offer.html', users=users, my_players=my_players, recipient_players=recipient_players, selected_receiver_id=selected_receiver_id)

@app.route('/offer/<int:offer_id>/accept', methods=['POST'])
@login_required
def accept_offer(offer_id):
    cur = db_helper.get_cursor()
    # Get offer details
    cur.execute("SELECT * FROM offers WHERE id = ? AND receiver_id = ? AND status = 'pending'", (offer_id, current_user.id))
    offer = cur.fetchone()
    if not offer:
        cur.close()
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Offer not found or already handled.'}), 404
        flash('Offer not found or already handled.', 'danger')
        return redirect(url_for('inbox'))

    # Check if this is a salary bill transfer (CPU sender with money only)
    if offer['sender_id'] == 1 and offer['offered_money'] > 0:
        # Check if this is a money-only transfer (salary bill)
        offered_players = json.loads(offer['offered_players']) if offer['offered_players'] else []
        requested_players = json.loads(offer['requested_players']) if offer['requested_players'] else []

        if len(offered_players) == 0 and len(requested_players) == 0:
            print(f"🔍 Detected salary bill transfer for {current_user.username}")  # Debug line
            # This is a salary bill transfer - user pays the salary amount
            salary_amount = offer['offered_money']
            print(f"💰 Salary amount: €{salary_amount:,}")  # Debug line

        # Get top 3 highest paid players for the blog post
        cur.execute("""
            SELECT p.player_name, p.salary, lt.team_name
            FROM players p
            JOIN team_players tp ON p.id = tp.player_id
            JOIN league_teams lt ON tp.team_id = lt.id
            WHERE lt.user_id = ?
            ORDER BY p.salary DESC
            LIMIT 3
        """, (current_user.id,))
        top_players = cur.fetchall()
        print(f"📊 Found {len(top_players)} top players")  # Debug line

        # Get total number of players
        cur.execute("""
            SELECT COUNT(*) as player_count
            FROM players p
            JOIN team_players tp ON p.id = tp.player_id
            JOIN league_teams lt ON tp.team_id = lt.id
            WHERE lt.user_id = ?
        """, (current_user.id,))
        player_count = cur.fetchone()['player_count']
        print(f"👥 Total players: {player_count}")  # Debug line

        # Update user's unified budget (negative amount = user pays)
        add_user_movement(current_user.id, 'Salary Bill Payment',
                         f'Paid salary bill for all your players: €{salary_amount:,}',
                         -salary_amount)

        # Mark offer as accepted
        cur.execute("UPDATE offers SET status = 'accepted' WHERE id = ?", (offer_id,))

        # Create enhanced blog post about the club's finances being in order
        blog_title = f"💰 {current_user.username}'s Club Finances Settled"
        print(f"📝 Creating blog post: {blog_title}")  # Debug line

        top_players_html = ""
        if top_players:
            top_players_html = "<p><strong>Top 3 Player Wages:</strong></p><ul>"
            for player in top_players:
                top_players_html += f"<li>{player['player_name']} ({player['team_name']}): €{player['salary']:,}</li>"
            top_players_html += "</ul>"

        blog_content = f"""
        <p><strong>🏦 Processing Bank Payments</strong></p>
        <p><strong>{current_user.username}</strong> has successfully processed their club's salary bill of <strong>€{salary_amount:,}</strong>.</p>
        <p>The payment covers <strong>{player_count} players</strong> across all managed teams.</p>
        {top_players_html}
        <p><strong>✅ Financial Status:</strong> All player wages have been settled and the club's finances are now in order.</p>
        <p>This ensures continued team stability and player satisfaction in the league.</p>
        """
        post_transfer_news(blog_title, blog_content, user_id=1)

        db_helper.commit()
        cur.close()

        flash(f'Salary bill paid! €{salary_amount:,} deducted from your budget. Blog post created.', 'success')
        return redirect(url_for('inbox'))

    # Check if this is a salary bill transfer (CPU sender with money only) - Alternative detection
    if offer['sender_id'] == 1 and offer['offered_money'] > 0 and offer['requested_money'] == 0:
        print(f"🔍 Alternative detection: CPU offer with money only")  # Debug line
        # This might be a salary bill transfer - check if it's a money-only transfer
        offered_players = json.loads(offer['offered_players']) if offer['offered_players'] else []
        requested_players = json.loads(offer['requested_players']) if offer['requested_players'] else []

        if len(offered_players) == 0 and len(requested_players) == 0:
            print(f"🔍 Confirmed salary bill transfer for {current_user.username}")  # Debug line
            # This is a salary bill transfer - user pays the salary amount
            salary_amount = offer['offered_money']
            print(f"💰 Salary amount: €{salary_amount:,}")  # Debug line

            # Get top 3 highest paid players for the blog post
            cur.execute("""
                SELECT p.player_name, p.salary, lt.team_name
                FROM players p
                JOIN team_players tp ON p.id = tp.player_id
                JOIN league_teams lt ON tp.team_id = lt.id
                WHERE lt.user_id = ?
                ORDER BY p.salary DESC
                LIMIT 3
            """, (current_user.id,))
            top_players = cur.fetchall()
            print(f"📊 Found {len(top_players)} top players")  # Debug line

            # Get total number of players
            cur.execute("""
                SELECT COUNT(*) as player_count
                FROM players p
                JOIN team_players tp ON p.id = tp.player_id
                JOIN league_teams lt ON tp.team_id = lt.id
                WHERE lt.user_id = ?
            """, (current_user.id,))
            player_count = cur.fetchone()['player_count']
            print(f"👥 Total players: {player_count}")  # Debug line

            # Update user's unified budget (negative amount = user pays)
            add_user_movement(current_user.id, 'Salary Bill Payment',
                             f'Paid salary bill for all your players: €{salary_amount:,}',
                             -salary_amount)

            # Mark offer as accepted
            cur.execute("UPDATE offers SET status = 'accepted' WHERE id = ?", (offer_id,))

            # Create enhanced blog post about the club's finances being in order
            blog_title = f"💰 {current_user.username}'s Club Finances Settled"
            print(f"📝 Creating blog post: {blog_title}")  # Debug line

            top_players_html = ""
            if top_players:
                top_players_html = "<p><strong>Top 3 Player Wages:</strong></p><ul>"
                for player in top_players:
                    top_players_html += f"<li>{player['player_name']} ({player['team_name']}): €{player['salary']:,}</li>"
                top_players_html += "</ul>"

            blog_content = f"""
            <p><strong>🏦 Processing Bank Payments</strong></p>
            <p><strong>{current_user.username}</strong> has successfully processed their club's salary bill of <strong>€{salary_amount:,}</strong>.</p>
            <p>The payment covers <strong>{player_count} players</strong> across all managed teams.</p>
            {top_players_html}
            <p><strong>✅ Financial Status:</strong> All player wages have been settled and the club's finances are now in order.</p>
            <p>This ensures continued team stability and player satisfaction in the league.</p>
            """
            post_transfer_news(blog_title, blog_content, user_id=1)

            db_helper.commit()
            cur.close()

            flash(f'Salary bill paid! €{salary_amount:,} deducted from your budget. Blog post created.', 'success')
            return redirect(url_for('inbox'))

    # Get team information from the offer
    sender_team_id = offer['sender_team_id']
    receiver_team_id = offer['receiver_team_id']

    # Verify that the sender and receiver teams exist and belong to the correct users
    cur.execute("SELECT * FROM league_teams WHERE id = ? AND user_id = ?", (sender_team_id, offer['sender_id']))
    sender_team = cur.fetchone()

    cur.execute("SELECT * FROM league_teams WHERE id = ? AND user_id = ?", (receiver_team_id, offer['receiver_id']))
    receiver_team = cur.fetchone()

    if not sender_team or not receiver_team:
        cur.close()
        flash('Teams not found for one of the users.', 'danger')
        return redirect(url_for('inbox'))

    # Transfer players: offered_players to recipient, requested_players to sender
    offered_players = json.loads(offer['offered_players'])
    requested_players = json.loads(offer['requested_players'])

    # Transfer offered_players from sender to receiver
    for pid in offered_players:
        # Remove from sender team
        cur.execute("DELETE FROM team_players WHERE team_id = ? AND player_id = ?", (sender_team_id, pid))
        # Add to receiver team
        cur.execute("INSERT INTO team_players (team_id, player_id) VALUES (?, ?)", (receiver_team_id, pid))

        # Update player's club_id to match receiver team
        cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", (receiver_team_id,))
        receiver_club = cur.fetchone()
        if receiver_club:
            cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (receiver_club['id'], pid))
            app.logger.info(f"Updated player {pid} club_id to {receiver_club['id']} for receiver team {receiver_team_id}")
        else:
            app.logger.warning(f"Could not find PES6 team for league team {receiver_team_id}")

    # Transfer requested_players from receiver to sender
    for pid in requested_players:
        # Remove from receiver team
        cur.execute("DELETE FROM team_players WHERE team_id = ? AND player_id = ?", (receiver_team_id, pid))
        # Add to sender team
        cur.execute("INSERT INTO team_players (team_id, player_id) VALUES (?, ?)", (sender_team_id, pid))

        # Update player's club_id to match sender team
        cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", (sender_team_id,))
        sender_club = cur.fetchone()
        if sender_club:
            cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (sender_club['id'], pid))
            app.logger.info(f"Updated player {pid} club_id to {sender_club['id']} for sender team {sender_team_id}")
        else:
            app.logger.warning(f"Could not find PES6 team for league team {sender_team_id}")
    # Get usernames for news post
    cur.execute("SELECT username FROM users WHERE id = ?", (offer['sender_id'],))
    sender_user = cur.fetchone()
    cur.execute("SELECT username FROM users WHERE id = ?", (offer['receiver_id'],))
    receiver_user = cur.fetchone()

    # Get player names for news post
    offered_player_names = []
    requested_player_names = []

    if offered_players:
        placeholders = ','.join(['?' for _ in offered_players])
        cur.execute(f"SELECT player_name FROM players WHERE id IN ({placeholders})", offered_players)
        offered_player_names = [row['player_name'] for row in cur.fetchall()]

    if requested_players:
        placeholders = ','.join(['?' for _ in requested_players])
        cur.execute(f"SELECT player_name FROM players WHERE id IN ({placeholders})", requested_players)
        requested_player_names = [row['player_name'] for row in cur.fetchall()]

    # Update budgets using unified budget system

    # Update sender's unified budget
    if offer['offered_money'] > 0:
        add_user_movement(offer['sender_id'], 'User Deal',
                         f'Transfer to {receiver_user["username"]}: {", ".join(offered_player_names) if offered_player_names else "Cash"}',
                         -offer['offered_money'])

    if offer['requested_money'] > 0:
        add_user_movement(offer['sender_id'], 'User Deal',
                         f'Transfer from {receiver_user["username"]}: {", ".join(requested_player_names) if requested_player_names else "Cash"}',
                         offer['requested_money'])

    # Update recipient's unified budget
    if offer['offered_money'] > 0:
        add_user_movement(offer['receiver_id'], 'User Deal',
                         f'Transfer from {sender_user["username"]}: {", ".join(offered_player_names) if offered_player_names else "Cash"}',
                         offer['offered_money'])

    if offer['requested_money'] > 0:
        add_user_movement(offer['receiver_id'], 'User Deal',
                         f'Transfer to {sender_user["username"]}: {", ".join(requested_player_names) if requested_player_names else "Cash"}',
                         -offer['requested_money'])

    # Mark offer as accepted
    cur.execute("UPDATE offers SET status = 'accepted' WHERE id = ?", (offer_id,))

    db_helper.commit()
    cur.close()

    # Post news about the transfer
    if sender_user and receiver_user:
        sender_name = sender_user['username']
        receiver_name = receiver_user['username']

        # Create news content
        news_title = f"Transfer Deal Completed: {sender_name} ↔ {receiver_name}"
        news_content = f"""
        <h3>Transfer Deal Completed!</h3>
        <p><strong>{sender_name}</strong> and <strong>{receiver_name}</strong> have completed a transfer deal.</p>

        <h4>Deal Details:</h4>
        <ul>
        """

        if offered_player_names:
            news_content += f"<li><strong>{sender_name}</strong> sent: {', '.join(offered_player_names)}</li>"
        if offer['offered_money'] and offer['offered_money'] > 0:
            news_content += f"<li><strong>{sender_name}</strong> paid: €{offer['offered_money']:,}</li>"
        if requested_player_names:
            news_content += f"<li><strong>{receiver_name}</strong> sent: {', '.join(requested_player_names)}</li>"
        if offer['requested_money'] and offer['requested_money'] > 0:
            news_content += f"<li><strong>{receiver_name}</strong> paid: €{offer['requested_money']:,}</li>"

        news_content += "</ul>"

        post_transfer_news(news_title, news_content)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'updated_budget': get_user_budget(current_user.id), 'message': 'Offer accepted and transfer completed!'})
    flash('Offer accepted and transfer completed!', 'success')
    return redirect(url_for('inbox'))

@app.route('/offer/<int:offer_id>/reject', methods=['POST'])
@login_required
def reject_offer(offer_id):
    cur = db_helper.get_cursor()

    # Get offer details before rejecting
    cur.execute("SELECT * FROM offers WHERE id = ? AND receiver_id = ? AND status = 'pending'", (offer_id, current_user.id))
    offer = cur.fetchone()

    if not offer:
        cur.close()
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Offer not found or already handled.'}), 404
        flash('Offer not found or already handled.', 'danger')
        return redirect(url_for('inbox'))

    # Get sender username for news post
    cur.execute("SELECT username FROM users WHERE id = ?", (offer['sender_id'],))
    sender_user = cur.fetchone()

    # Update offer status
    cur.execute("UPDATE offers SET status = 'rejected' WHERE id = ? AND receiver_id = ?", (offer_id, current_user.id))
    db_helper.commit()
    cur.close()

    # Post news about the rejected offer
    if sender_user:
        sender_name = sender_user['username']
        receiver_name = current_user.username

        news_title = f"Transfer Offer Rejected: {sender_name} → {receiver_name}"
        news_content = f"""
        <h3>Transfer Offer Rejected</h3>
        <p><strong>{receiver_name}</strong> has rejected a transfer offer from <strong>{sender_name}</strong>.</p>
        <p>The deal has been called off and no transfers will take place.</p>
        """

        post_transfer_news(news_title, news_content)

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Offer rejected.'})

    flash('Offer rejected.', 'info')
    return redirect(url_for('inbox'))

@app.route('/negotiate_with_cpu/<int:player_id>', methods=['GET', 'POST'])
def negotiate_with_cpu(player_id):
    app.logger.info(f"=== NEGOTIATE ROUTE STARTED ===")
    app.logger.info(f"Player ID: {player_id}")
    app.logger.info(f"Request method: {request.method}")
    app.logger.info(f"Request headers: {dict(request.headers)}")

    # Handle GET request - show negotiation form
    if request.method == 'GET':
        app.logger.info("Handling GET request - showing negotiation form")
        try:
            cur = db_helper.get_cursor()
            cur.execute("""
                SELECT p.player_name, p.market_value, t.club_name, t.id as team_id
                FROM players p
                JOIN teams t ON p.club_id = t.id
                WHERE p.id = ?
            """, (player_id,))
            player_data = cur.fetchone()

            if not player_data:
                cur.close()
                flash('Player not found.', 'danger')
                return redirect(url_for('team_management'))

            player_name, market_value, club_name, team_id = player_data

            # Check if the team belongs to a user (not CPU)
            cur.execute("""
                SELECT lt.user_id, u.username
                FROM league_teams lt
                JOIN users u ON lt.user_id = u.id
                WHERE lt.id = ? AND lt.user_id != 1
            """, (team_id,))
            user_team_data = cur.fetchone()
            cur.close()

            if user_team_data:
                # This team belongs to a user, not CPU
                flash('Please use the dashboard to negotiate with another user.', 'warning')
                return redirect(url_for('team_management'))

            # Team is CPU-owned, proceed with negotiation
            buy_now_price = max(5000000, market_value * 3)

            return render_template('negotiate_form.html',
                                 player_id=player_id,
                                 player_name=player_name,
                                 market_value=market_value,
                                 club_name=club_name,
                                 buy_now_price=buy_now_price)
        except Exception as e:
            app.logger.error(f"Error in GET request: {e}")
            flash('Error loading player information.', 'danger')
            return redirect(url_for('team_management'))

    # Handle POST request - process negotiation
    try:
        app.logger.info("Checking authentication...")
        # Check authentication manually for better error handling
        if not current_user.is_authenticated:
            app.logger.warning(f"Unauthenticated negotiate request for player {player_id}")
            return jsonify({'error': 'Authentication required. Please log in.'}), 401

        app.logger.info("Authentication OK, parsing request data...")

        # Check if the team belongs to a user (not CPU) - same check as GET request
        cur = db_helper.get_cursor()
        cur.execute("""
            SELECT t.id as team_id
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE p.id = ?
        """, (player_id,))
        player_team_data = cur.fetchone()

        if player_team_data:
            team_id = player_team_data['team_id']
            cur.execute("""
                SELECT lt.user_id, u.username
                FROM league_teams lt
                JOIN users u ON lt.user_id = u.id
                WHERE lt.id = ? AND lt.user_id != 1
            """, (team_id,))
            user_team_data = cur.fetchone()
            cur.close()

            if user_team_data:
                # This team belongs to a user, not CPU
                return jsonify({'error': 'Please use the dashboard to negotiate with another user.'}), 403

        cur.close()

        # Handle both JSON (AJAX) and form data
        if request.is_json:
            data = request.get_json()
            app.logger.info(f"JSON data received: {data}")
            action = data.get('action')
            offer_amount = data.get('offer_amount', 0)
        else:
            # Form data
            action = request.form.get('action')
            offer_amount = int(request.form.get('offer_amount', 0))
            app.logger.info(f"Form data received: action={action}, offer_amount={offer_amount}")

        app.logger.info(f"Negotiate request: player_id={player_id}, action={action}, user={current_user.id}")

        # Check if player is blacklisted for this user
        if is_blacklisted(current_user.id, player_id):
            return jsonify({'error': 'This player is no longer available for negotiation with you.'}), 403

        # Fetch player info from DB
        cur = db_helper.get_cursor()
        app.logger.info("Database cursor obtained")

        cur.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        player = cur.fetchone()
        if not player:
            cur.close()
            return jsonify({'error': 'Player not found'}), 404

        app.logger.info(f"Player found: {player['player_name']}")

        market_value = player['market_value'] or 0
        player_name = player['player_name']
        selling_club_id = player['club_id']

        # Get selling club name
        cur.execute("SELECT club_name FROM teams WHERE id = ?", (selling_club_id,))
        club_row = cur.fetchone()
        club_name = club_row['club_name'] if club_row else 'Unknown Club'

        app.logger.info(f"Club name: {club_name}")

        # Get user's active team
        cur.execute("SELECT id FROM league_teams WHERE user_id = ? ORDER BY id LIMIT 1", (current_user.id,))
        user_team_row = cur.fetchone()
        if not user_team_row:
            cur.close()
            return jsonify({'error': 'You do not manage a team.'}), 400
        user_league_team_id = user_team_row['id']

        app.logger.info(f"User team ID: {user_league_team_id}")

        if action == 'buy_now':
            # Buy now option: 3x market value, minimum €5M
            buy_now_price = max(5000000, market_value * 3)

            # Transfer player (no budget check - user can buy even without sufficient budget)
            cur.execute("UPDATE players SET club_id = (SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)) WHERE id = ?",
                       (user_league_team_id, player_id))

            # Update unified budget
            add_user_movement(current_user.id, 'CPU Purchase',
                             f"Bought {player_name} from {club_name} (Buy Now)",
                             -buy_now_price)

            # Update CPU team budget (for CPU teams)
            cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?", (buy_now_price, selling_club_id))

            # Blacklist player
            add_to_blacklist(current_user.id, player_id)

            # Create blog post about the buy now purchase
            blog_title = f"Breaking: {current_user.username} Signs {player_name}"
            blog_content = f"{current_user.username} has completed a surprise signing, acquiring {player_name} from {club_name} for €{buy_now_price:,} in a buy-now deal!"
            post_transfer_news(blog_title, blog_content)

            # Send inbox message to user
            send_inbox_message(current_user.id, f"Transfer Completed: {player_name}",
                              f"Your buy-now purchase of {player_name} from {club_name} for €{buy_now_price:,} has been completed successfully!")

            db_helper.commit()
            cur.close()

            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': f'Successfully bought {player_name} for €{buy_now_price:,}!',
                    'action': 'buy_now',
                    'price': buy_now_price
                })
            else:
                flash(f'Successfully bought {player_name} for €{buy_now_price:,}!', 'success')
                return redirect(url_for('team_management'))

        elif action == 'submit_offer':
            # Submit offer option
            if offer_amount <= 0:
                cur.close()
                return jsonify({'error': 'Offer amount must be positive.'}), 400

            # Create offer in user_cpu_offers table
            cur.execute("""
                INSERT INTO user_cpu_offers (buyer_team_id, seller_team_id, player_id, offered_price, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)
            """, (user_league_team_id, selling_club_id, player_id, offer_amount))

            offer_id = cur.lastrowid

            # Create blog post about the offer with 3-tier disclosure system
            import random
            leak_chance = random.random()

            if leak_chance < 0.3:  # 30% chance: Reveal player and team
                blog_title = f"Transfer Rumors: {player_name}"
                blog_content = f"{current_user.username} is reportedly interested in signing {player_name} from {club_name}."
                post_transfer_news(blog_title, blog_content)
            elif leak_chance < 0.6:  # 30% chance: Reveal only team
                blog_title = f"Transfer Rumors: {club_name}"
                blog_content = f"{current_user.username} is reportedly interested in signing a player from {club_name}."
                post_transfer_news(blog_title, blog_content)
            # 40% chance: No leak (no blog post)

            db_helper.commit()
            cur.close()

            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': f'Offer of €{offer_amount:,} submitted for {player_name}. The CPU will consider it during their next market activity.',
                    'action': 'offer_submitted',
                    'offer_id': offer_id
                })
            else:
                flash(f'Offer of €{offer_amount:,} submitted for {player_name}. The CPU will consider it during their next market activity.', 'success')
                return redirect(url_for('team_management'))

        else:
            # Initial negotiation - return player info and options
            app.logger.info("Returning initial negotiation data")
            buy_now_price = max(5000000, market_value * 3)
            cur.close()

            return jsonify({
                'player_name': player_name,
                'market_value': market_value,
                'club_name': club_name,
                'buy_now_price': buy_now_price,
                'step': 'initial'
            })

    except Exception as e:
        app.logger.error(f"Error in negotiate_with_cpu: {e}")
        if 'cur' in locals():
            cur.close()
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/get_team_players_full/<int:user_id>')
@login_required
def get_team_players_full(user_id):
    cur = db_helper.get_cursor()
    cur.execute("""
        SELECT p.id, p.player_name AS NAME, p.market_value AS `Market Value`, p.registered_position
        FROM players p
        JOIN teams t ON p.club_id = t.id
        JOIN league_teams lt ON t.club_name = lt.team_name
        WHERE lt.user_id = ?
        ORDER BY p.player_name ASC
    """, (user_id,))
    players = cur.fetchall()
    cur.close()
    return jsonify([dict(row) for row in players])

@app.route('/get_player_details/<int:player_id>')
@login_required
def get_player_details(player_id):
    """Get player details for hover functionality."""
    cur = db_helper.get_cursor()
    cur.execute("""
        SELECT id, player_name, age, salary, contract_years_remaining,
               attack_rating, defense_rating, physical_rating, power_rating, technique_rating, goalkeeping_rating,
               game_position
        FROM players WHERE id = ?
    """, (player_id,))
    player = cur.fetchone()
    cur.close()

    if not player:
        return jsonify({'error': 'Player not found'}), 404

    return jsonify({
        'id': player['id'],
        'name': player['player_name'],
        'age': player['age'],
        'salary': player['salary'],
        'contract_years': player['contract_years_remaining'],
        'game_position': player['game_position'],
        'bundled_skills': {
            'Attack': player['attack_rating'],
            'Defense': player['defense_rating'],
            'Physical': player['physical_rating'],
            'Power': player['power_rating'],
            'Technique': player['technique_rating'],
            'Goalkeeping': player['goalkeeping_rating']
        }
    })

@app.route('/select_team', methods=['GET', 'POST'])
@login_required
def select_team():
    # Only allow if user has no team
    cur = db_helper.get_cursor()
    cur.execute("SELECT COUNT(*) as count FROM league_teams WHERE user_id = ?", (current_user.id,))
    if cur.fetchone()['count'] > 0:
        cur.close()
        flash('You already manage a team.', 'warning')
        return redirect(url_for('team_management'))
    # Get available teams (not already assigned)
    cur.execute("SELECT t.id, t.club_name FROM teams t LEFT JOIN league_teams lt ON t.club_name = lt.team_name WHERE lt.id IS NULL ORDER BY t.club_name ASC")
    available_teams = cur.fetchall()
    if request.method == 'POST':
        selected_team_id = request.form.get('selected_team')
        if not selected_team_id:
            flash('Please select a team.', 'danger')
            return render_template('team_management.html', managed_teams=[], available_teams=available_teams, coach_username=current_user.username, total_budget_display=450000000, total_salaries_user_teams=0, free_cap_user_teams=450000000)
        # Assign team to user
        cur.execute("SELECT club_name FROM teams WHERE id = ?", (selected_team_id,))
        team_row = cur.fetchone()
        if not team_row:
            flash('Selected team not found.', 'danger')
            return render_template('team_management.html', managed_teams=[], available_teams=available_teams, coach_username=current_user.username, total_budget_display=450000000, total_salaries_user_teams=0, free_cap_user_teams=450000000)
        team_name = team_row['club_name']
        cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (?, ?)", (current_user.id, team_name))
        db_helper.commit()
        new_league_team_id = cur.lastrowid
        # Populate roster
        cur.execute("SELECT id FROM players WHERE club_id = ?", (selected_team_id,))
        players_in_team = cur.fetchall()
        if players_in_team:
            player_team_data = [(new_league_team_id, player['id']) for player in players_in_team]
            cur.executemany("INSERT INTO team_players (team_id, player_id) VALUES (?, ?)", player_team_data)
            db_helper.commit()
        cur.close()
        flash('Team selected and roster assigned!','success')
        return redirect(url_for('team_management'))
    cur.close()
    return render_template('team_management.html', managed_teams=[], available_teams=available_teams, coach_username=current_user.username, total_budget_display=450000000, total_salaries_user_teams=0, free_cap_user_teams=450000000)

@app.route('/confirm_transfer_with_cpu/<int:player_id>', methods=['POST'])
@login_required
def confirm_transfer_with_cpu(player_id):
    data = request.get_json()
    current_deal = data.get('current_deal')

    app.logger.info(f"Confirming transfer for player {player_id} with deal: {current_deal}")

    try:
        cur = db_helper.get_cursor()

        # Check if player is blacklisted
        if is_blacklisted(current_user.id, player_id):
            return jsonify({'error': 'This player is no longer available for transfer.'}), 403

        # Get user's team
        cur.execute("SELECT id FROM league_teams WHERE user_id = ?", (current_user.id,))
        user_league_team = cur.fetchone()
        if not user_league_team:
            cur.close()
            return jsonify({'error': 'You do not manage a team.'}), 400
        user_league_team_id = user_league_team['id']

        # Get the CPU team from the deal data - this is the team that should receive your player
        club_name = current_deal.get('club_name')
        if not club_name:
            cur.close()
            return jsonify({'error': 'CPU team not found in deal data'}), 400

        # Get the CPU league team for this club
        cpu_league_team_id = None
        cur.execute("SELECT id FROM league_teams WHERE team_name = ? AND user_id = 1", (club_name,))
        cpu_league_team = cur.fetchone()
        if cpu_league_team:
            cpu_league_team_id = cpu_league_team['id']
        else:
            # Create CPU league team if it doesn't exist
            cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (?, ?)", (1, club_name))
            db_helper.commit()
            cpu_league_team_id = cur.lastrowid

        # Verify we found a CPU team
        if not cpu_league_team_id:
            cur.close()
            return jsonify({'error': 'No CPU team found'}), 400

        # Build offered/requested player lists
        offered_players = [player_id]  # CPU's player(s) to user
        requested_players = []         # User's player(s) to CPU
        player_given = current_deal.get('player_given')
        if player_given and player_given.get('id'):
            requested_players.append(player_given['id'])
        cpu_player_given = current_deal.get('cpu_player_given')
        if cpu_player_given and cpu_player_given.get('id'):
            offered_players.append(cpu_player_given['id'])

        # Transfer offered_players to user
        cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", (user_league_team_id,))
        user_club = cur.fetchone()
        for pid in offered_players:
            if user_club and user_club['id']:
                cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (user_club['id'], pid))
            cur.execute("DELETE FROM team_players WHERE player_id = ?", (pid,))
            cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (user_league_team_id, pid))

        # Transfer requested_players to CPU
        cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", (cpu_league_team_id,))
        cpu_club = cur.fetchone()
        for pid in requested_players:
            if cpu_club and cpu_club['id']:
                cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (cpu_club['id'], pid))
            else:
                # Fallback: if club_id lookup fails, just update team_players
                # The player will still appear on the correct team in the league
                pass
            # Always update team_players to ensure the player goes to the correct CPU team
            cur.execute("DELETE FROM team_players WHERE player_id = ?", (pid,))
            cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (cpu_league_team_id, pid))

        # Compose a clear confirmation message
        def get_player_name(pid):
            cur.execute("SELECT player_name FROM players WHERE id = ?", (pid,))
            row = cur.fetchone()
            return row['player_name'] if row else f'Player {pid}'

        offered_names = ', '.join(get_player_name(pid) for pid in offered_players)
        requested_names = ', '.join(get_player_name(pid) for pid in requested_players)
        cur.execute("SELECT team_name FROM league_teams WHERE id = ?", (user_league_team_id,))
        user_team_name = cur.fetchone()['team_name']
        cur.execute("SELECT team_name FROM league_teams WHERE id = ?", (cpu_league_team_id,))
        cpu_team_name = cur.fetchone()['team_name']

        # Update budgets using unified budget system
        cash_paid = current_deal.get('cash_paid', 0)
        if cash_paid != 0:
            # Update user's unified budget
            add_user_movement(current_user.id, 'CPU Negotiation',
                            f'Transfer with {cpu_team_name}: {offered_names} for {requested_names}',
                            -cash_paid)

            # Update CPU team budget (legacy system for CPU teams)
            cur.execute("SELECT budget FROM league_teams WHERE id = ?", (cpu_league_team_id,))
            cpu_budget = cur.fetchone()['budget']
            new_cpu_budget = cpu_budget + cash_paid
            cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_cpu_budget, cpu_league_team_id))

        summary = f"Transfer complete! {offered_names} joined {user_team_name}."
        if requested_players:
            summary += f" {requested_names} joined {cpu_team_name}."
        if cash_paid > 0:
            summary += f" €{cash_paid:,} transferred."

        # Post transfer news to blog
        news_title = f"Transfer News: {offered_names} → {user_team_name}"
        news_content = f"""
        <h3>Transfer News</h3>
        <p><strong>{offered_names}</strong> has been transferred to <strong>{user_team_name}</strong>.</p>
        """
        if requested_players:
            news_content += f"<p><strong>{user_team_name}</strong> sends <strong>{requested_names}</strong> to <strong>{cpu_team_name}</strong> in exchange.</p>"
        if cash_paid > 0:
            news_content += f"<p><strong>{user_team_name}</strong> pays <strong>€{cash_paid:,}</strong> to <strong>{cpu_team_name}</strong>.</p>"
        news_content += "<p>The transfer has been completed.</p>"

        post_transfer_news(news_title, news_content)

        db_helper.commit()
        cur.close()
        return jsonify({
            'success': True,
            'message': summary,
            'updated_budget': get_user_budget(current_user.id) if cash_paid != 0 else None
        })

    except Exception as e:
        app.logger.error(f"Error in confirm_transfer_with_cpu: {str(e)}")
        db_helper.get_connection().rollback()
        cur.close()
        return jsonify({'error': f'Error confirming transfer: {str(e)}'}), 500

@app.route('/sell_player/<int:player_id>', methods=['POST'])
@login_required
def sell_player(player_id):
    # Check if player is blacklisted for this user
    if is_blacklisted(current_user.id, player_id):
        return jsonify({'error': 'This player is no longer available for sale negotiations.'}), 403
    # Blacklist the player as soon as the user requests offers
    add_to_blacklist(current_user.id, player_id)

    # Fetch player info
    cur = db_helper.get_cursor()
    cur.execute("SELECT * FROM players WHERE id = ?", (player_id,))
    player = cur.fetchone()
    if not player:
        cur.close()
        return jsonify({'error': 'Player not found'}), 404
    player_name = player['player_name']
    market_value = player['market_value']
    salary = player['salary']
    age = player['age']
    # Get user's team
    cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = ?", (current_user.id,))
    user_team = cur.fetchone()
    if not user_team:
        cur.close()
        return jsonify({'error': 'You do not manage a team.'}), 400
    user_team_id = user_team['id']
    user_team_name = user_team['team_name']
    # Get all possible CPU clubs (not user-managed)
    cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = 1 AND team_name != ? AND id != 141", (user_team_name,))
    cpu_clubs = cur.fetchall()
    if not cpu_clubs:
        cur.close()
        return jsonify({'error': 'No CPU clubs available.'}), 400
    # Determine number of offers (1-7) based on value/age/salary
    n_offers = 1
    if market_value >= 20000000 and age <= 25 and salary < 5000000:
        n_offers = 7
    elif market_value >= 10000000 and age <= 28 and salary < 8000000:
        n_offers = 5
    elif market_value >= 5000000 and age <= 30:
        n_offers = 3
    elif market_value >= 2000000:
        n_offers = 2
    n_offers = min(n_offers, len(cpu_clubs))
    import random
    offer_teams = random.sample(cpu_clubs, n_offers)
    proposals = []
    for idx, cpu_team in enumerate(offer_teams):
        cpu_team_id = cpu_team['id']
        cpu_team_name = cpu_team['team_name']
        # Fetch the club_id for this CPU team
        cur.execute("SELECT id FROM teams WHERE club_name = ?", (cpu_team_name,))
        team_row = cur.fetchone()
        club_id = team_row['id'] if team_row else None
        # Generate initial offer (cash or swap)
        bidding_club_squad = []
        if club_id:
            cur.execute("SELECT id, player_name, market_value FROM players WHERE club_id = ?", (club_id,))
            bidding_club_squad = [dict(row) for row in cur.fetchall()]
        target_offer_value = int(market_value * random.uniform(0.25, 0.65))
        offer = {'proposal_id': idx+1, 'cpu_team': cpu_team_name, 'cash': target_offer_value, 'player_swap': None}
        # 30% chance of player swap if squad available
        if bidding_club_squad and random.random() < 0.3:
            # Allow swaps for players up to 120% of the offer value
            suitable = [p for p in bidding_club_squad if p['market_value'] <= int(target_offer_value * 1.2)]
            if suitable:
                exchange_player = random.choice(suitable)
                # If the swap player is worth more than the offer value, demand compensation from the user
                if exchange_player['market_value'] > target_offer_value:
                    compensation = exchange_player['market_value'] - target_offer_value
                    offer['cash'] = -compensation  # Negative means user must pay
                else:
                    offer['cash'] = target_offer_value - exchange_player['market_value']
                offer['player_swap'] = {'id': exchange_player['id'], 'NAME': exchange_player['player_name'], 'Market Value': exchange_player['market_value']}
        proposals.append(offer)
    cur.close()
    return jsonify({'success': True, 'proposals': proposals, 'player_name': player_name})

@app.route('/sell_player/<int:player_id>/counter', methods=['POST'])
@login_required
def sell_player_counter(player_id):
    data = request.get_json()
    proposal = data.get('proposal')
    if not proposal:
        return jsonify({'error': 'No proposal provided.'}), 400
    cpu_team_name = proposal.get('cpu_team')
    cash = proposal.get('cash', 0)
    player_swap = proposal.get('player_swap')

    # Calculate the total value of the current offer (cash + player market value)
    current_total_value = cash
    if player_swap:
        current_total_value += player_swap.get('Market Value', 0)

    # Find the CPU team id
    cur = db_helper.get_cursor()
    cur.execute("SELECT id FROM league_teams WHERE team_name = ? AND user_id = 1", (cpu_team_name,))
    cpu_team = cur.fetchone()
    if not cpu_team:
        cur.close()
        return jsonify({'error': 'CPU team not found.'}), 404
    cpu_team_id = cpu_team['id']
    # Get the squad for that club
    cur.execute("SELECT p.id, p.player_name, p.market_value FROM players p JOIN team_players tp ON p.id = tp.player_id WHERE tp.team_id = ?", (cpu_team_id,))
    bidding_club_squad = [dict(row) for row in cur.fetchall()]

    # If no players found in team_players, try to get players directly from the club
    if not bidding_club_squad:
        cur.execute("SELECT p.id, p.player_name, p.market_value FROM players p JOIN teams t ON p.club_id = t.id WHERE t.club_name = ?", (cpu_team_name,))
        bidding_club_squad = [dict(row) for row in cur.fetchall()]

    # 35% chance the team quits negotiation
    if random.random() < 0.35:
        cur.close()
        return jsonify({'quit': True, 'message': f'{cpu_team_name} has quit negotiations.'})

    # Improve the total offer value by 5-15%
    new_total_value = int(current_total_value * random.uniform(1.05, 1.15))
    new_cash = new_total_value
    new_player_swap = None

    # 30% chance to offer a swap (either keep existing swap, improve it, or offer a new one)
    if bidding_club_squad and random.random() < 0.3:
        suitable = [p for p in bidding_club_squad if p['market_value'] <= int(new_total_value * 1.2)]
        if suitable:
            exchange_player = random.choice(suitable)
            # Calculate new cash based on the new total value minus the swap player's value
            new_cash = new_total_value - exchange_player['market_value']
            new_player_swap = {'id': exchange_player['id'], 'NAME': exchange_player['player_name'], 'Market Value': exchange_player['market_value']}

    # If no swap was offered above, still try to offer a swap (40% chance)
    if not new_player_swap and bidding_club_squad and random.random() < 0.4:
        suitable = [p for p in bidding_club_squad if p['market_value'] <= int(new_total_value * 1.2)]
        if suitable:
            exchange_player = random.choice(suitable)
            new_cash = new_total_value - exchange_player['market_value']
            new_player_swap = {'id': exchange_player['id'], 'NAME': exchange_player['player_name'], 'Market Value': exchange_player['market_value']}

    cur.close()
    return jsonify({'quit': False, 'proposal': {
        'proposal_id': proposal.get('proposal_id'),
        'cpu_team': cpu_team_name,
        'cash': new_cash,
        'player_swap': new_player_swap
    }})

@app.route('/download_my_team_csv/<int:team_id>')
@login_required
def download_my_team_csv(team_id):
    cur = db_helper.get_cursor()
    # Ensure the team belongs to the current user
    cur.execute("SELECT id FROM league_teams WHERE id = ? AND user_id = ?", (team_id, current_user.id))
    team_check = cur.fetchone()
    if not team_check:
        cur.close()
        return abort(403)
    # Fetch all players for this team
    cur.execute("""
        SELECT p.id, p.player_name, p.registered_position, p.age, p.nationality, p.salary, p.contract_years_remaining, p.market_value
        FROM players p
        JOIN team_players tp ON p.id = tp.player_id
        WHERE tp.team_id = ?
        ORDER BY p.player_name ASC
    """, (team_id,))
    players = cur.fetchall()
    cur.close()

    # Generate CSV with latin-1 encoding for PES6 compatibility
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID', 'Player Name', 'Position', 'Age', 'Nationality', 'Salary', 'Contract Years', 'Market Value'])
    for p in players:
        writer.writerow([
            p['id'], p['player_name'], p['registered_position'], p['age'], p['nationality'], p['salary'], p['contract_years_remaining'], p['market_value']
        ])
    output = si.getvalue()
    si.close()

    # Encode output to latin-1 for PES6 compatibility
    output_bytes = output.encode('latin-1')

    return Response(
        output_bytes,
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment;filename=my_team_{team_id}.csv"}
    )

@app.route('/sell_player/<int:player_id>/accept', methods=['POST'])
@login_required
def accept_sell_offer(player_id):
    data = request.get_json()
    proposal = data.get('proposal')
    if not proposal:
        return jsonify({'error': 'No proposal provided.'}), 400

    cpu_team_name = proposal.get('cpu_team')
    cash = proposal.get('cash', 0)
    player_swap = proposal.get('player_swap')

    try:
        cur = db_helper.get_cursor()

        # Check if player is blacklisted
        if is_blacklisted(current_user.id, player_id):
            return jsonify({'error': 'This player is no longer available for transfer.'}), 403

        # Find the CPU team id
        cur.execute("SELECT id FROM league_teams WHERE team_name = ? AND user_id = 1", (cpu_team_name,))
        cpu_team = cur.fetchone()
        if not cpu_team:
            cur.close()
            return jsonify({'error': 'CPU team not found.'}), 404
        cpu_team_id = cpu_team['id']

        # Get user's team
        cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = ?", (current_user.id,))
        user_team = cur.fetchone()
        if not user_team:
            cur.close()
            return jsonify({'error': 'You do not manage a team.'}), 400
        user_team_id = user_team['id']
        user_team_name = user_team['team_name']

        # Build player lists for transfer
        offered_players = []  # CPU players to user
        requested_players = [player_id]  # User's player to CPU

        if player_swap:
            offered_players.append(player_swap['id'])

        # Track asset changes for response
        asset_changes = []

        # Transfer offered_players to user
        cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", (user_team_id,))
        user_club = cur.fetchone()
        for pid in offered_players:
            cur.execute("SELECT player_name FROM players WHERE id = ?", (pid,))
            player_name = cur.fetchone()['player_name']
            if user_club and user_club['id']:
                cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (user_club['id'], pid))
            cur.execute("DELETE FROM team_players WHERE player_id = ?", (pid,))
            cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (user_team_id, pid))
            asset_changes.append(f"✅ {player_name} transferred to your team")

        # Transfer requested_players to CPU
        cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", (cpu_team_id,))
        cpu_club = cur.fetchone()
        for pid in requested_players:
            cur.execute("SELECT player_name FROM players WHERE id = ?", (pid,))
            player_name = cur.fetchone()['player_name']
            if cpu_club and cpu_club['id']:
                cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (cpu_club['id'], pid))
            cur.execute("DELETE FROM team_players WHERE player_id = ?", (pid,))
            cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (cpu_team_id, pid))
            asset_changes.append(f"❌ {player_name} transferred to {cpu_team_name}")

        # Update budgets using unified budget system
        if cash != 0:
            # Update user's unified budget
            add_user_movement(current_user.id, 'CPU Negotiation',
                            f'Sell to CPU: Received €{cash:,}',
                            cash)

            # Update CPU team budget (legacy system for CPU teams)
            cur.execute("SELECT budget FROM league_teams WHERE id = ?", (cpu_team_id,))
            cpu_budget = cur.fetchone()['budget']
            new_cpu_budget = cpu_budget - cash
            cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_cpu_budget, cpu_team_id))

            if cash > 0:
                asset_changes.append(f"✅ €{cash:,} received")
            else:
                asset_changes.append(f"❌ €{abs(cash):,} paid")

        # Compose summary message
        offered_names = ', '.join([get_player_name(pid) for pid in offered_players]) if offered_players else 'No players'
        requested_names = ', '.join([get_player_name(pid) for pid in requested_players])

        summary = f"Transfer complete! {requested_names} joined {cpu_team_name}."
        if offered_players:
            summary += f" {offered_names} joined {user_team_name}."
        if cash != 0:
            summary += f" €{cash:,} transferred."

        # Create blog post
        cur.execute("SELECT player_name FROM players WHERE id = ?", (player_id,))
        player_name = cur.fetchone()['player_name']

        news_title = f"Daily Mail Transfer: {player_name} → {cpu_team_name}"
        news_content = f"""
        <h3>Daily Mail Transfer News</h3>
        <p><strong>{player_name}</strong> has been sold by <strong>{user_team_name}</strong> to <strong>{cpu_team_name}</strong> for €{cash:,.0f}.</p>
        """
        if player_swap:
            news_content += f"<p><strong>{cpu_team_name}</strong> sends <strong>{player_swap['NAME']}</strong> in exchange.</p>"
        news_content += "<p>The transfer has been completed.</p>"

        post_transfer_news(news_title, news_content)

        db_helper.commit()
        cur.close()

        return jsonify({
            'success': True,
            'message': summary,
            'updated_budget': get_user_budget(current_user.id) if cash != 0 else None,
            'asset_changes': asset_changes
        })

    except Exception as e:
        app.logger.error(f"Error in accept_sell_offer: {str(e)}")
        db_helper.get_connection().rollback()
        cur.close()
        return jsonify({'error': f'Error completing transfer: {str(e)}'}), 500

def get_player_name(pid):
    cur = db_helper.get_cursor()
    cur.execute("SELECT player_name FROM players WHERE id = ?", (pid,))
    row = cur.fetchone()
    cur.close()
    return row['player_name'] if row else f'Player {pid}'

@app.route('/offer/<int:offer_id>/confirm_sell', methods=['POST'])
@login_required
def confirm_sell_offer(offer_id):
    cur = db_helper.get_cursor()
    cur.execute("SELECT * FROM offers WHERE id = ? AND receiver_id = ? AND status = 'pending'", (offer_id, current_user.id))
    offer = cur.fetchone()
    if not offer:
        cur.close()
        return jsonify({'error': 'Offer not found or already handled.'}), 404

    # Handle both legacy (user-to-user) and CPU offers
    if 'offered_players' in offer and 'requested_players' in offer:
        offered_players = json.loads(offer['offered_players'])      # "Their Offer" (should go to user)
        requested_players = json.loads(offer['requested_players'])  # "Your Side" (should go to CPU)
    else:
        # CPU offer: player_id is the player being sold, offer_amount is the money
        offered_players = []
        requested_players = [offer['player_id']]
        offered_money = offer['offer_amount']

    # Get your team ID
    cur.execute("SELECT id FROM league_teams WHERE user_id = ?", (current_user.id,))
    user_team = cur.fetchone()
    if not user_team:
        cur.close()
        return jsonify({'error': 'User team not found.'}), 400
    user_team_id = user_team['id']

    # Get the CPU team from the offer (using the team name shown in the email)
    cpu_team_id = None
    cpu_team_name = None
    if offered_players:
        cur.execute("SELECT club_id FROM players WHERE id = ?", (offered_players[0],))
        club_row = cur.fetchone()
        if club_row and club_row['club_id']:
            cur.execute("SELECT team_name, id FROM league_teams WHERE user_id = 1 AND team_name = (SELECT club_name FROM teams WHERE id = ?)", (club_row['club_id'],))
            cpu_team = cur.fetchone()
            if cpu_team:
                cpu_team_name = cpu_team['team_name']
                cpu_team_id = cpu_team['id']
    if not cpu_team_id:
        cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = 1 LIMIT 1")
        cpu_team = cur.fetchone()
        if cpu_team:
            cpu_team_id = cpu_team['id']
            cpu_team_name = cpu_team['team_name']

    # Track asset changes for response
    asset_changes = []

    # Transfer "Their Offer" to user - update club_id to user's team
    for pid in offered_players:
        cur.execute("SELECT player_name FROM players WHERE id = ?", (pid,))
        player_name = cur.fetchone()['player_name']
        cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", (user_team_id,))
        user_club = cur.fetchone()
        if user_club and user_club['id']:
            cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (user_club['id'], pid))
            cur.execute("DELETE FROM team_players WHERE player_id = ?", (pid,))
            cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (user_team_id, pid))
            asset_changes.append(f"✅ {player_name} transferred to your team")

    # Transfer "Your Side" to CPU - update club_id to CPU's team
    for pid in requested_players:
        cur.execute("SELECT player_name FROM players WHERE id = ?", (pid,))
        player_name = cur.fetchone()['player_name']
        cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", (cpu_team_id,))
        cpu_club = cur.fetchone()
        if cpu_club and cpu_club['id']:
            cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (cpu_club['id'], pid))
            cur.execute("DELETE FROM team_players WHERE player_id = ?", (pid,))
            cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (cpu_team_id, pid))
            asset_changes.append(f"❌ {player_name} transferred to {cpu_team_name}")
        else:
            cur.execute("DELETE FROM team_players WHERE player_id = ?", (pid,))
            cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (cpu_team_id, pid))
            asset_changes.append(f"❌ {player_name} transferred to {cpu_team_name}")

    # Fetch CPU team name robustly
    cur.execute("SELECT team_name FROM league_teams WHERE id = ?", (cpu_team_id,))
    cpu_team_row = cur.fetchone()
    cpu_team_name = cpu_team_row['team_name'] if cpu_team_row else 'CPU team'

    # Update budgets using unified budget system
    if 'offered_money' in offer and 'requested_money' in offer:
        # User-to-user deal
        if offer['offered_money'] > 0:
            add_user_movement(current_user.id, 'User Deal',
                            f'Sell offer: Received €{offer["offered_money"]:,}',
                            offer['offered_money'])
            asset_changes.append(f"✅ €{offer['offered_money']:,} received")
        if offer['requested_money'] > 0:
            add_user_movement(current_user.id, 'User Deal',
                            f'Sell offer: Paid €{offer["requested_money"]:,}',
                            -offer['requested_money'])
            asset_changes.append(f"❌ €{offer['requested_money']:,} paid")
    else:
        # CPU offer: user gets offer_amount
        add_user_movement(current_user.id, 'CPU Negotiation',
                        f'Sell to CPU: Received €{offer["offer_amount"]:,}',
                        offer['offer_amount'])
        asset_changes.append(f"✅ €{offer['offer_amount']:,} received")

    # Update CPU team budget (legacy system for CPU teams)
    cur.execute("SELECT budget FROM league_teams WHERE id = ?", (cpu_team_id,))
    cpu_budget = cur.fetchone()['budget']
    if 'offered_money' in offer and 'requested_money' in offer:
        new_cpu_budget = cpu_budget - offer['offered_money'] + offer['requested_money']
    else:
        new_cpu_budget = cpu_budget - offer['offer_amount']
    cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_cpu_budget, cpu_team_id))
    cur.execute("UPDATE offers SET status = 'accepted' WHERE id = ?", (offer_id,))

    # Post news about the CPU transfer
    if offered_players or requested_players:
        offered_names = ', '.join([get_player_name(pid) for pid in offered_players]) if offered_players else 'No players'
        requested_names = ', '.join([get_player_name(pid) for pid in requested_players]) if requested_players else 'No players'

        news_title = f"CPU Transfer Deal: {current_user.username} ↔ {cpu_team_name}"
        news_content = f"""
        <h3>CPU Transfer Deal Completed</h3>
        <p><strong>{current_user.username}</strong> and <strong>{cpu_team_name}</strong> have completed a transfer deal.</p>

        <h4>Deal Details:</h4>
        <ul>
        """

        if offered_players:
            news_content += f"<li><strong>{cpu_team_name}</strong> sent: {offered_names}</li>"
        if offer['offered_money'] and offer['offered_money'] > 0:
            news_content += f"<li><strong>{cpu_team_name}</strong> paid: €{offer['offered_money']:,}</li>"
        if requested_players:
            news_content += f"<li><strong>{current_user.username}</strong> sent: {requested_names}</li>"
        if offer['requested_money'] and offer['requested_money'] > 0:
            news_content += f"<li><strong>{current_user.username}</strong> paid: €{offer['requested_money']:,}</li>"

        news_content += "</ul>"

        post_transfer_news(news_title, news_content)

    db_helper.commit()
    cur.close()

    return jsonify({
        'success': True,
        'message': 'Sale confirmed and transfer completed!',
        'updated_budget': get_user_budget(current_user.id),
        'asset_changes': asset_changes
    })

@app.route('/offer/<int:offer_id>/confirm_buy', methods=['POST'])
@login_required
def confirm_buy_offer(offer_id):
    cur = db_helper.get_cursor()
    cur.execute("SELECT * FROM offers WHERE id = ? AND receiver_id = ? AND status = 'pending'", (offer_id, current_user.id))
    offer = cur.fetchone()
    if not offer:
        cur.close()
        return jsonify({'error': 'Offer not found or already handled.'}), 404

    # Handle both legacy (user-to-user) and CPU offers
    if 'offered_players' in offer and 'requested_players' in offer:
        offered_players = json.loads(offer['offered_players'])      # CPU players being offered
        requested_players = json.loads(offer['requested_players'])  # Your players being requested
    else:
        # CPU offer: player_id is the player being bought, offer_amount is the money
        offered_players = [offer['player_id']]
        requested_players = []
        offered_money = offer['offer_amount']

    # Get your team ID
    cur.execute("SELECT id FROM league_teams WHERE user_id = ?", (current_user.id,))
    user_team = cur.fetchone()
    if not user_team:
        cur.close()
        return jsonify({'error': 'User team not found.'}), 400
    user_team_id = user_team['id']

    # Find the CPU team by checking where the offered player currently belongs
    cpu_team_id = None
    cpu_team_name = None
    if offered_players:
        cur.execute("SELECT club_id FROM players WHERE id = ?", (offered_players[0],))
        club_row = cur.fetchone()
        if club_row and club_row['club_id']:
            cur.execute("SELECT team_name, id FROM league_teams WHERE user_id = 1 AND team_name = (SELECT club_name FROM teams WHERE id = ?)", (club_row['club_id'],))
            cpu_team = cur.fetchone()
            if cpu_team:
                cpu_team_id = cpu_team['id']
                cpu_team_name = cpu_team['team_name']
    if not cpu_team_id:
        cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = 1 LIMIT 1")
        cpu_team = cur.fetchone()
        if cpu_team:
            cpu_team_id = cpu_team['id']
            cpu_team_name = cpu_team['team_name']

    # Track asset changes for response
    asset_changes = []

    # Transfer offered_players to user
    cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", (user_team_id,))
    user_club = cur.fetchone()
    for pid in offered_players:
        cur.execute("SELECT player_name FROM players WHERE id = ?", (pid,))
        player_name = cur.fetchone()['player_name']
        if user_club and user_club['id']:
            cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (user_club['id'], pid))
        cur.execute("DELETE FROM team_players WHERE player_id = ?", (pid,))
        cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (user_team_id, pid))
        asset_changes.append(f"✅ {player_name} transferred to your team")

    # Transfer requested_players to CPU
    cur.execute("SELECT id FROM teams WHERE club_name = (SELECT team_name FROM league_teams WHERE id = ?)", (cpu_team_id,))
    cpu_club = cur.fetchone()
    for pid in requested_players:
        cur.execute("SELECT player_name FROM players WHERE id = ?", (pid,))
        player_name = cur.fetchone()['player_name']
        if cpu_club and cpu_club['id']:
            cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (cpu_club['id'], pid))
        cur.execute("DELETE FROM team_players WHERE player_id = ?", (pid,))
        cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (cpu_team_id, pid))
        asset_changes.append(f"❌ {player_name} transferred to {cpu_team_name}")

    # Update budgets using unified budget system
    if 'offered_money' in offer and 'requested_money' in offer:
        # User-to-user deal
        if offer['offered_money'] > 0:
            add_user_movement(current_user.id, 'User Deal',
                            f'Buy offer: Paid €{offer["offered_money"]:,}',
                            -offer['offered_money'])
            asset_changes.append(f"❌ €{offer['offered_money']:,} paid")
        if offer['requested_money'] > 0:
            add_user_movement(current_user.id, 'User Deal',
                            f'Buy offer: Received €{offer["requested_money"]:,}',
                            offer['requested_money'])
            asset_changes.append(f"✅ €{offer['requested_money']:,} received")
    else:
        # CPU offer: user pays offer_amount
        add_user_movement(current_user.id, 'CPU Negotiation',
                        f'Buy from CPU: Paid €{offer["offer_amount"]:,}',
                        -offer['offer_amount'])
        asset_changes.append(f"❌ €{offer['offer_amount']:,} paid")

    # Update CPU team budget (legacy system for CPU teams)
    cur.execute("SELECT budget FROM league_teams WHERE id = ?", (cpu_team_id,))
    cpu_budget = cur.fetchone()['budget']
    if 'offered_money' in offer and 'requested_money' in offer:
        new_cpu_budget = cpu_budget + offer['offered_money'] - offer['requested_money']
    else:
        new_cpu_budget = cpu_budget + offer['offer_amount']
    cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_cpu_budget, cpu_team_id))
    cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_cpu_budget, cpu_team_id))
    cur.execute("UPDATE offers SET status = 'accepted' WHERE id = ?", (offer_id,))
    db_helper.commit()
    cur.close()

    return jsonify({
        'success': True,
        'message': 'Purchase confirmed and transfer completed!',
        'updated_budget': get_user_budget(current_user.id),
        'asset_changes': asset_changes
    })

# --- Change Player Team Tool ---
@app.route('/change_player_team', methods=['GET', 'POST'])
def change_player_team():
    cur = db_helper.get_cursor()
    message = None
    if request.method == 'POST':
        player_id = request.form.get('player_id')
        new_team_id = request.form.get('team_id')
        if player_id and new_team_id:
            cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (new_team_id, player_id))
            db_helper.commit()
            message = 'Player team updated!'
    # Fetch all players and teams for the dropdowns
    cur.execute("SELECT id, player_name FROM players ORDER BY player_name ASC")
    players = cur.fetchall()
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    teams = cur.fetchall()
    cur.close()
    # Render tools.html with extra context for the form
    return render_template('tools.html', players=players, teams=teams, message=message)

@app.route('/allocate_trophy', methods=['GET', 'POST'])
@login_required
def allocate_trophy():
    """Allocate trophy to a team and update player statistics"""
    cur = db_helper.get_cursor()
    message = None

    if request.method == 'POST':
        team_id = request.form.get('team_id')
        trophy_type = request.form.get('trophy_type')
        trophy_name = request.form.get('trophy_name')

        if not all([team_id, trophy_type, trophy_name]):
            message = '❌ All fields are required!'
        else:
            try:
                # Get team name
                cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
                team_result = cur.fetchone()
                if not team_result:
                    message = '❌ Team not found!'
                else:
                    team_name = team_result[0]

                    # Get all players from the team
                    cur.execute("SELECT id, player_name FROM players WHERE club_id = ?", (team_id,))
                    players = cur.fetchall()

                    if not players:
                        message = f'❌ No players found in {team_name}!'
                    else:
                        # Update player statistics based on trophy type
                        if trophy_type == 'championship':
                            cur.execute("UPDATE players SET championships_won = championships_won + 1 WHERE club_id = ?", (team_id,))
                            column_name = 'championships_won'
                            trophy_emoji = '🏆'
                        elif trophy_type == 'cup':
                            cur.execute("UPDATE players SET cups_won = cups_won + 1 WHERE club_id = ?", (team_id,))
                            column_name = 'cups_won'
                            trophy_emoji = '🥇'
                        else:
                            message = '❌ Invalid trophy type!'
                            cur.close()
                            return render_template('tools.html', teams=get_all_teams(), trophy_message=message)

                        updated_count = cur.rowcount

                        # Create blog post
                        blog_title = f"{trophy_emoji} {trophy_name} - {team_name} Champions!"
                        blog_content = f"""
                        <p><strong>{trophy_emoji} Trophy Allocation Announcement</strong></p>
                        <p><strong>{team_name}</strong> has been awarded the <strong>{trophy_name}</strong>!</p>
                        <p>All {updated_count} players from {team_name} have had their {trophy_type} count increased by 1.</p>
                        <p><strong>🏆 Trophy Details:</strong></p>
                        <ul>
                            <li><strong>Trophy:</strong> {trophy_name}</li>
                            <li><strong>Type:</strong> {trophy_type.title()}</li>
                            <li><strong>Team:</strong> {team_name}</li>
                            <li><strong>Players Updated:</strong> {updated_count}</li>
                        </ul>
                        <p><strong>✅ Trophy allocation completed successfully!</strong></p>
                        """
                        post_transfer_news(blog_title, blog_content, user_id=1)

                        db_helper.commit()
                        message = f'✅ Successfully allocated {trophy_name} to {team_name}! Updated {updated_count} players.'

            except Exception as e:
                message = f'❌ Error allocating trophy: {str(e)}'
                app.logger.error(f"Error in allocate_trophy: {e}")
                db_helper.get_connection().rollback()

    # Get all teams for the dropdown
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    teams = cur.fetchall()
    cur.close()

    return render_template('tools.html', teams=teams, trophy_message=message)

def get_all_teams():
    """Helper function to get all teams"""
    cur = db_helper.get_cursor()
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    teams = cur.fetchall()
    cur.close()
    return teams

@app.route('/change_player_salary', methods=['GET', 'POST'])
def change_player_salary():
    cur = db_helper.get_cursor()
    message = None
    if request.method == 'POST':
        player_id = request.form.get('player_id')
        new_salary = request.form.get('salary')
        new_contract_years = request.form.get('contract_years')
        new_yearly_wage_rise = request.form.get('yearly_wage_rise')

        if player_id:
            try:
                updates = []
                params = []

                if new_salary:
                    new_salary = int(new_salary)
                    updates.append("salary = ?")
                    params.append(new_salary)

                if new_contract_years:
                    new_contract_years = int(new_contract_years)
                    updates.append("contract_years_remaining = ?")
                    params.append(new_contract_years)

                if new_yearly_wage_rise:
                    new_yearly_wage_rise = float(new_yearly_wage_rise)
                    updates.append("yearly_wage_rise = ?")
                    params.append(new_yearly_wage_rise)

                if updates:
                    params.append(player_id)
                    query = f"UPDATE players SET {', '.join(updates)} WHERE id = ?"
                    cur.execute(query, params)
                    db_helper.commit()

                    updated_fields = []
                    if new_salary:
                        updated_fields.append(f"salary to €{new_salary:,}")
                    if new_contract_years:
                        updated_fields.append(f"contract years to {new_contract_years}")
                    if new_yearly_wage_rise:
                        updated_fields.append(f"yearly wage rise to {new_yearly_wage_rise:.1%}")

                    message = f'Player updated: {", ".join(updated_fields)}!'
                else:
                    message = 'No fields to update. Please provide at least one field.'
            except ValueError as e:
                message = f'Invalid value. Please enter valid numbers. Error: {str(e)}'
    # Fetch all players for the dropdown with their current values
    cur.execute("SELECT id, player_name, salary, contract_years_remaining, yearly_wage_rise FROM players ORDER BY player_name ASC")
    players = cur.fetchall()
    cur.close()
    # Render tools.html with extra context for the form
    return render_template('tools.html', players=players, salary_message=message)

@app.route('/update_team_stats', methods=['GET', 'POST'])
@login_required
def update_team_stats():
    """Update current year team stats for players"""
    cur = db_helper.get_cursor()
    message = None

    if request.method == 'POST':
        team_id = request.form.get('team_id')
        if team_id:
            try:
                # Get all players for the selected team
                cur.execute("""
                    SELECT id, player_name, games_played, goals, assists
                    FROM players
                    WHERE club_id = ?
                    ORDER BY player_name ASC
                """, (team_id,))
                players = cur.fetchall()

                updated_count = 0
                for player in players:
                    player_id = player[0]
                    player_name = player[1]

                    # Get form data for this player
                    games = request.form.get(f'games_{player_id}')
                    goals = request.form.get(f'goals_{player_id}')
                    assists = request.form.get(f'assists_{player_id}')

                    updates = []
                    params = []

                    if games and games.strip():
                        games = int(games)
                        updates.append("games_played = ?")
                        params.append(games)

                    if goals and goals.strip():
                        goals = int(goals)
                        updates.append("goals = ?")
                        params.append(goals)

                    if assists and assists.strip():
                        assists = int(assists)
                        updates.append("assists = ?")
                        params.append(assists)

                    if updates:
                        params.append(player_id)
                        query = f"UPDATE players SET {', '.join(updates)} WHERE id = ?"
                        cur.execute(query, params)
                        updated_count += 1

                db_helper.commit()
                message = f'Updated stats for {updated_count} players!'

            except ValueError as e:
                message = f'Invalid value. Please enter valid numbers. Error: {str(e)}'
                db_helper.get_connection().rollback()
            except Exception as e:
                message = f'Error updating stats: {str(e)}'
                db_helper.get_connection().rollback()

    # Get all teams for selection
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    teams = cur.fetchall()

    # Get players for selected team if team_id is provided
    players = []
    selected_team_id = None
    if request.method == 'POST' and request.form.get('team_id'):
        selected_team_id = request.form.get('team_id')
        cur.execute("""
            SELECT id, player_name, games_played, goals, assists
            FROM players
            WHERE club_id = ?
            ORDER BY player_name ASC
        """, (selected_team_id,))
        players = cur.fetchall()

    cur.close()
    return render_template('tools.html', teams=teams, team_players=players, selected_team_id=selected_team_id, team_stats_message=message)

# --- Clear Blacklist Tool ---
@app.route('/clear_blacklist', methods=['POST'])
def clear_blacklist_route():
    clear_blacklist()
    flash('Blacklist cleared successfully!', 'success')
    return redirect(url_for('tools'))

# --- Team Historical Data Management ---
@app.route('/manage_team_historical_data', methods=['GET', 'POST'])
@login_required
def manage_team_historical_data():
    """Add or update team historical data (season, competition, place)"""
    from datetime import datetime
    
    cur = db_helper.get_cursor()
    
    if request.method == 'POST':
        team_id = request.form.get('team_id')
        season = request.form.get('season')
        competition = request.form.get('competition')
        place = request.form.get('place')
        
        if not all([team_id, season, competition, place]):
            flash('All fields are required!', 'danger')
            cur.close()
            return redirect(url_for('manage_team_historical_data'))
        
        try:
            # Check if record exists
            cur.execute("""
                SELECT id FROM team_historical_data 
                WHERE team_id = ? AND season = ? AND competition = ?
            """, (team_id, season, competition))
            existing = cur.fetchone()
            
            now = datetime.now().isoformat()
            if existing:
                # Update existing record
                cur.execute("""
                    UPDATE team_historical_data 
                    SET place = ?, updated_at = ?
                    WHERE id = ?
                """, (place, now, existing['id']))
                flash(f'Updated historical data for season {season}!', 'success')
            else:
                # Insert new record
                cur.execute("""
                    INSERT INTO team_historical_data (team_id, season, competition, place, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (team_id, season, competition, place, now, now))
                flash(f'Added historical data for season {season}!', 'success')
            
            db_helper.commit()
        except Exception as e:
            db_helper.get_connection().rollback()
            flash(f'Error saving historical data: {str(e)}', 'danger')
        finally:
            cur.close()
        
        return redirect(url_for('manage_team_historical_data'))
    
    # GET request - show form
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    teams = cur.fetchall()
    cur.close()
    
    return render_template('tools.html', teams_historical=teams, historical_message=None)

@app.route('/delete_team_historical_data/<int:record_id>', methods=['POST'])
@login_required
def delete_team_historical_data(record_id):
    """Delete a team historical data record"""
    cur = db_helper.get_cursor()
    try:
        cur.execute("DELETE FROM team_historical_data WHERE id = ?", (record_id,))
        db_helper.commit()
        flash('Historical data deleted successfully!', 'success')
    except Exception as e:
        db_helper.get_connection().rollback()
        flash(f'Error deleting historical data: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('manage_team_historical_data'))

# --- Blacklist Helper Functions ---
def add_to_blacklist(user_id, player_id):
    """Add a player to general blacklist (affects all users and CPU)"""
    cur = db_helper.get_cursor()
    try:
        # Use user_id = 1 (CPU user) for general blacklist (affects everyone)
        cur.execute("INSERT INTO blacklist (user_id, player_id) VALUES (1, ?)", (player_id,))
        db_helper.commit()
        return True
    except Exception as e:
        # Player already blacklisted (UNIQUE constraint)
        return False
    finally:
        cur.close()

def is_blacklisted(user_id, player_id):
    """Check if a player is blacklisted (general blacklist affects everyone)"""
    cur = db_helper.get_cursor()
    # Check general blacklist (user_id = 1) which affects everyone
    cur.execute("SELECT 1 FROM blacklist WHERE user_id = 1 AND player_id = ?", (player_id,))
    result = cur.fetchone()
    cur.close()
    return result is not None

def should_blacklist_player(player_id):
    """Check if a player should be blacklisted (not if they're already on loan)"""
    cur = db_helper.get_cursor()
    cur.execute("SELECT loaned_by FROM players WHERE id = ?", (player_id,))
    result = cur.fetchone()
    cur.close()

    if result and result[0] and result[0] != '':
        return False  # Player is on loan, don't blacklist
    return True  # Player is not on loan, can be blacklisted

def clear_blacklist():
    """Clear all blacklist entries except for loaned players and draftees"""
    cur = db_helper.get_cursor()

    # Count total blacklist entries
    cur.execute("SELECT COUNT(*) FROM blacklist")
    total_blacklisted = cur.fetchone()[0]

    # Count loaned players and draftees that are blacklisted
    cur.execute("""
        SELECT COUNT(*) FROM blacklist bl
        JOIN players p ON bl.player_id = p.id
        WHERE (p.loaned_by IS NOT NULL AND p.loaned_by != '') OR p.draftee = 1
    """)
    preserved_count = cur.fetchone()[0]

    # Clear blacklist entries for non-loaned, non-draftee players only
    cur.execute("""
        DELETE FROM blacklist
        WHERE player_id NOT IN (
            SELECT id FROM players
            WHERE (loaned_by IS NOT NULL AND loaned_by != '') OR draftee = 1
        )
    """)

    cleared_count = cur.rowcount
    db_helper.commit()
    cur.close()

    print(f"✅ Cleared {cleared_count} blacklist entries (preserved {preserved_count} loaned/draftee players)")
    return cleared_count, preserved_count

def get_unread_count(user_id):
    """
    Get the count of unread messages and pending offers for a user.
    """
    cur = db_helper.get_cursor()
    try:
        # Count all messages (since there's no read status column)
        cur.execute("SELECT COUNT(*) as count FROM messages WHERE receiver_id = ?", (user_id,))
        message_count = cur.fetchone()['count']

        # Count pending offers
        cur.execute("SELECT COUNT(*) as count FROM offers WHERE receiver_id = ? AND status = 'pending'", (user_id,))
        offer_count = cur.fetchone()['count']

        return message_count + offer_count
    except Exception as e:
        app.logger.error(f"Error getting unread count: {e}")
        return 0
    finally:
        cur.close()

@app.context_processor
def inject_unread_count():
    """Make unread count available to all templates."""
    if current_user.is_authenticated:
        return {'get_unread_count': get_unread_count}
    return {'get_unread_count': lambda x: 0}

def get_user_budget(user_id):
    """Get user's unified budget.
    Prefer cached snapshot in user_budgets if present; otherwise fallback to base + SUM(movements).
    """
    cur = db_helper.get_cursor()
    try:
        # Prefer cached snapshot
        cur.execute("SELECT budget FROM user_budgets WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row and row['budget'] is not None:
            return row['budget']

        # Fallback: compute from movements
        cur.execute("SELECT COALESCE(SUM(amount), 0) as total_movements FROM user_movements WHERE user_id = ?", (user_id,))
        movements_result = cur.fetchone()
        total_movements = movements_result['total_movements'] if movements_result else 0
        return 450000000 + total_movements
    finally:
        cur.close()

def update_user_budget(user_id, new_budget):
    """Update user's unified budget"""
    cur = db_helper.get_cursor()
    cur.execute("""
        INSERT OR REPLACE INTO user_budgets (user_id, budget, updated_at)
        VALUES (?, ?, ?)
    """, (user_id, new_budget, datetime.now().isoformat()))
    db_helper.commit()
    cur.close()

def add_user_movement(user_id, movement_type, description, amount):
    """Add a financial movement to user's transaction history"""
    cur = db_helper.get_cursor()

    # Get current budget
    current_budget = get_user_budget(user_id)
    new_budget = current_budget + amount

    # Update budget
    update_user_budget(user_id, new_budget)

    # Add movement record
    cur.execute("""
        INSERT INTO user_movements (user_id, type, description, amount, balance_after)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, movement_type, description, amount, new_budget))
    db_helper.commit()
    cur.close()

def send_inbox_message(receiver_id, subject, content, sender_id=1):
    """Send a message to a user's inbox"""
    cur = db_helper.get_cursor()
    try:
        cur.execute("""
            INSERT INTO messages (sender_id, receiver_id, subject, content, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (sender_id, receiver_id, subject, content))
        db_helper.commit()
        return True
    except Exception as e:
        app.logger.error(f"Error sending inbox message: {e}")
        return False
    finally:
        cur.close()



def post_transfer_news(title, content, user_id=1):
    """
    Post transfer news to the blog.
    user_id=1 is the CPU user, used for system-generated news.
    """
    cur = db_helper.get_cursor()
    try:
        cur.execute("INSERT INTO posts (user_id, title, content, media_type, media_path, created_at) VALUES (?, ?, ?, 'none', NULL, ?)",
                    (user_id, title, content, datetime.now().isoformat()))
        db_helper.commit()
        app.logger.info(f"Transfer news posted: {title}")
        print(f"✅ Blog post created: {title}")  # Debug line
    except Exception as e:
        db_helper.get_connection().rollback()
        app.logger.error(f"Error posting transfer news: {e}")
        print(f"❌ Error creating blog post: {e}")  # Debug line
    finally:
        cur.close()

@app.route('/offer/<int:offer_id>/details')
@login_required
def get_offer_details(offer_id):
    cur = db_helper.get_cursor()
    cur.execute("""
        SELECT o.*,
               CASE WHEN o.sender_id = 1 THEN 'cpu' ELSE 'user' END as offer_type,
               CASE WHEN o.player_id IS NOT NULL AND o.offered_players IS NULL THEN 'sell' ELSE 'buy' END as deal_type
        FROM offers o
        WHERE o.id = ? AND o.receiver_id = ? AND o.status = 'pending'
    """, (offer_id, current_user.id))
    offer = cur.fetchone()

    if not offer:
        cur.close()
        return jsonify({'error': 'Offer not found or already handled.'}), 404

    # Get player details for offered and requested players
    offered_players = []
    requested_players = []

    if offer['offered_players']:
        offered_player_ids = json.loads(offer['offered_players'])
        if offered_player_ids:
            placeholders = ','.join(['?' for _ in offered_player_ids])
            cur.execute(f"SELECT id, player_name, registered_position FROM players WHERE id IN ({placeholders})", offered_player_ids)
            offered_players = cur.fetchall()

    if offer['requested_players']:
        requested_player_ids = json.loads(offer['requested_players'])
        if requested_player_ids:
            placeholders = ','.join(['?' for _ in requested_player_ids])
            cur.execute(f"SELECT id, player_name, registered_position FROM players WHERE id IN ({placeholders})", requested_player_ids)
            requested_players = cur.fetchall()

    # Handle legacy offers
    if not offer['offered_players'] and offer['player_id']:
        if offer['deal_type'] == 'sell':
            # User selling to CPU
            cur.execute("SELECT id, player_name, registered_position FROM players WHERE id = ?", (offer['player_id'],))
            requested_players = cur.fetchall()
        else:
            # User buying from CPU
            cur.execute("SELECT id, player_name, registered_position FROM players WHERE id = ?", (offer['player_id'],))
            offered_players = cur.fetchall()

    cur.close()

    return jsonify({
        'offer_id': offer_id,
        'deal_type': offer['deal_type'],
        'offered_money': offer['offered_money'] if offer['offered_money'] else 0,
        'requested_money': offer['requested_money'] if offer['requested_money'] else 0,
        'offered_players': offered_players,
        'requested_players': requested_players,
        'is_cpu_offer': offer['offer_type'] == 'cpu'
    })

@app.route('/free_agency')
@login_required
def free_agency():
    # Check for expired offers first - comprehensive check
    processed_count = 0
    try:
        cur = db_helper.get_cursor()

        # Get expired offers using proper datetime comparison
        from datetime import datetime
        current_time = datetime.now()

        # Debug: Check what offers exist
        cur.execute("SELECT COUNT(*) as total FROM free_agent_offers WHERE status = 'active'")
        total_active = cur.fetchone()['total']

        # Get expired offers using simple comparison
        current_time_iso = current_time.isoformat()
        cur.execute("""
            SELECT fao.id, fao.player_id, fao.user_id, fao.offered_salary, fao.offered_contract_years,
                   fao.expires_at, p.player_name, p.age, u.username
            FROM free_agent_offers fao
            JOIN players p ON fao.player_id = p.id
            JOIN users u ON fao.user_id = u.id
            WHERE fao.status = 'active' AND fao.expires_at <= ?
        """, (current_time_iso,))
        expired_offers = cur.fetchall()

        for offer in expired_offers:
            try:
                # Mark offer as completed
                cur.execute("UPDATE free_agent_offers SET status = 'completed' WHERE id = ?", (offer['id'],))

                # Get user's active team
                cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = ? ORDER BY id LIMIT 1", (offer['user_id'],))
                user_team = cur.fetchone()

                if user_team:
                    active_team_id = user_team['id']
                    team_name = user_team['team_name']

                    # Find the corresponding PES6 team ID
                    cur.execute("SELECT id FROM teams WHERE club_name = ?", (team_name,))
                    pes6_team_result = cur.fetchone()

                    if pes6_team_result:
                        pes6_team_id = pes6_team_result['id']

                        # Calculate signing bonus and yearly wage rise
                        import random

                        # Calculate signing bonus (25-50% of base salary, higher for younger players)
                        player_age = offer['age']
                        if player_age <= 22:
                            signing_bonus_percentage = random.uniform(0.40, 0.50)  # 40-50% for very young players
                        elif player_age <= 25:
                            signing_bonus_percentage = random.uniform(0.35, 0.45)  # 35-45% for young players
                        elif player_age <= 28:
                            signing_bonus_percentage = random.uniform(0.30, 0.40)  # 30-40% for mid-age players
                        else:
                            signing_bonus_percentage = random.uniform(0.25, 0.35)  # 25-35% for older players

                        signing_bonus = int(offer['offered_salary'] * signing_bonus_percentage)

                        # Calculate yearly wage rise (same logic as contract renewal)
                        if player_age <= 22:
                            yearly_wage_rise = random.uniform(0.15, 0.25)  # 15-25% for very young players
                        elif player_age <= 25:
                            yearly_wage_rise = random.uniform(0.10, 0.20)  # 10-20% for young players
                        elif player_age <= 28:
                            yearly_wage_rise = random.uniform(0.05, 0.15)  # 5-15% for mid-age players
                        else:
                            yearly_wage_rise = random.uniform(0.01, 0.10)  # 1-10% for older players

                        # Update player's salary, contract, yearly wage rise, and club_id
                        cur.execute("""
                            UPDATE players
                            SET salary = ?, contract_years_remaining = ?, yearly_wage_rise = ?, club_id = ?
                            WHERE id = ?
                        """, (offer['offered_salary'], offer['offered_contract_years'], yearly_wage_rise, pes6_team_id, offer['player_id']))

                        # Deduct signing bonus from team budget
                        cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", (signing_bonus, pes6_team_id))

                        # Record signing bonus transaction in finances
                        add_user_movement(offer['user_id'], 'Signing Bonus',
                                        f"Signing bonus for {offer['player_name']} (Free Agency)", -signing_bonus)

                        # Add player to team_players table
                        cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)",
                                   (active_team_id, offer['player_id']))

                        # Post transfer news with signing bonus info
                        title = f"Free Agent Transfer: {offer['player_name']}"
                        content = f"{offer['player_name']} has signed with {offer['username']}'s team for €{offer['offered_salary']:,} per year for {offer['offered_contract_years']} years. Signing bonus: €{signing_bonus:,} ({(signing_bonus_percentage*100):.1f}% of salary). Yearly wage rise: {(yearly_wage_rise*100):.1f}%."
                        post_transfer_news(title, content, offer['user_id'])

                        processed_count += 1

            except Exception as e:
                app.logger.error(f"Error processing expired offer {offer['id']}: {e}")

        if processed_count > 0:
            db_helper.commit()
            flash(f'Processed {processed_count} expired free agent offers.', 'info')

        cur.close()

    except Exception as e:
        app.logger.error(f"Error in expired offers check: {e}")

    # Now continue with normal free agency page logic
    cur = db_helper.get_cursor()

    # Get filter parameters
    min_salary = request.args.get('min_salary')
    max_salary = request.args.get('max_salary')
    position = request.args.get('position')
    player_name = request.args.get('player_name')

    # Build the query with filters (exclude draftees)
    query = """
        SELECT id, player_name, age, game_position, strong_foot, salary, contract_years_remaining, market_value,
               attack_rating, defense_rating, physical_rating, power_rating, technique_rating, goalkeeping_rating
        FROM players
        WHERE club_id = 141 AND (draftee = 0 OR draftee IS NULL)
    """
    params = []

    if min_salary:
        query += " AND salary >= ?"
        params.append(int(min_salary))

    if max_salary:
        query += " AND salary <= ?"
        params.append(int(max_salary))

    if position:
        query += " AND game_position = ?"
        params.append(position)

    if player_name:
        query += " AND player_name LIKE ?"
        params.append(f"%{player_name}%")

    query += " ORDER BY salary DESC"

    cur.execute(query, params)
    free_agents = cur.fetchall()

    # Get current offers
    cur.execute("""
        SELECT fao.id, fao.player_id, fao.user_id, fao.offered_salary, fao.offered_contract_years,
               fao.created_at, fao.expires_at, fao.status,
               p.player_name, p.salary, p.contract_years_remaining, p.age,
               u.username
        FROM free_agent_offers fao
        JOIN players p ON fao.player_id = p.id
        JOIN users u ON fao.user_id = u.id
        WHERE fao.status = 'active'
        ORDER BY fao.expires_at ASC
    """)
    current_offers = cur.fetchall()

    cur.close()

    return render_template('free_agency.html',
                         free_agents=free_agents,
                         current_offers=current_offers)

@app.route('/free_agency/make_offer', methods=['POST'])
@login_required
def make_free_agent_offer():
    player_id = request.form.get('player_id')
    offered_salary = int(float(request.form.get('offered_salary')))
    offered_contract_years = int(request.form.get('offered_contract_years'))

    # Check if user has an active team
    active_team_id = session.get('active_team_id')
    if not active_team_id:
        flash('You need an active team to make offers.', 'danger')
        return redirect(url_for('free_agency'))

    cur = db_helper.get_cursor()

    # Check if player is still a free agent
    cur.execute("SELECT id FROM players WHERE id = ? AND club_id = 141", (player_id,))
    if not cur.fetchone():
        flash('Player is no longer available.', 'danger')
        cur.close()
        return redirect(url_for('free_agency'))

    # Check if there's already an active offer for this player
    cur.execute("SELECT id FROM free_agent_offers WHERE player_id = ? AND status = 'active'", (player_id,))
    existing_offer = cur.fetchone()

    if existing_offer:
        flash('This player already has an active offer.', 'danger')
        cur.close()
        return redirect(url_for('free_agency'))

    # Create new offer (2 minutes for testing)
    from datetime import datetime, timedelta
    expires_at = datetime.now() + timedelta(minutes=500)

    try:
        # Create the offer (store team_id so CPU teams can outbid each other correctly)
        cur.execute("""
            INSERT INTO free_agent_offers (player_id, user_id, offered_salary, offered_contract_years, expires_at, team_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (player_id, current_user.id, offered_salary, offered_contract_years, expires_at.isoformat(), active_team_id))
        
        # Do not update players.salary on offer creation; keep as free-agency basis
        
        db_helper.commit()
        flash('Offer made successfully!', 'success')

        # Trigger immediate check for expired offers to process any that should be completed
        check_expired_offers()

    except Exception as e:
        db_helper.get_connection().rollback()
        flash(f'Error making offer: {e}', 'danger')
    finally:
        cur.close()

    return redirect(url_for('free_agency'))

@app.route('/free_agency/raise_offer/<int:offer_id>', methods=['POST'])
@login_required
def raise_free_agent_offer(offer_id):
    cur = db_helper.get_cursor()

    # Get current offer
    cur.execute("""
        SELECT id, player_id, user_id, offered_salary, offered_contract_years, expires_at
        FROM free_agent_offers WHERE id = ? AND status = 'active'
    """, (offer_id,))
    offer = cur.fetchone()

    if not offer:
        flash('Offer not found or already expired.', 'danger')
        cur.close()
        return redirect(url_for('free_agency'))

    # Check if user has an active team
    active_team_id = session.get('active_team_id')
    if not active_team_id:
        flash('You need an active team to make offers.', 'danger')
        cur.close()
        return redirect(url_for('free_agency'))

    # Raise offer by 250,000€ and reset timer
    new_salary = offer['offered_salary'] + 250000
    from datetime import datetime, timedelta
    new_expires_at = datetime.now() + timedelta(minutes=500)  # 5 minutes like initial offers

    try:
        # Update the offer
        cur.execute("""
            UPDATE free_agent_offers
            SET user_id = ?, offered_salary = ?, expires_at = ?, team_id = ?
            WHERE id = ?
        """, (current_user.id, new_salary, new_expires_at.isoformat(), active_team_id, offer_id))
        
        # Do not update players.salary on raises; keep as free-agency basis
        db_helper.commit()
        flash('Offer raised successfully!', 'success')

        # Trigger immediate check for expired offers to process any that should be completed
        check_expired_offers()

    except Exception as e:
        db_helper.get_connection().rollback()
        flash(f'Error raising offer: {e}', 'danger')
    finally:
        cur.close()

    return redirect(url_for('free_agency'))

def check_expired_offers():
    """Helper function to check and process expired offers"""
    cur = db_helper.get_cursor()

    # Get expired offers using proper datetime comparison
    from datetime import datetime
    current_time = datetime.now().isoformat()

    cur.execute("""
        SELECT fao.id, fao.player_id, fao.user_id, fao.offered_salary, fao.offered_contract_years,
               p.player_name, u.username
        FROM free_agent_offers fao
        JOIN players p ON fao.player_id = p.id
        JOIN users u ON fao.user_id = u.id
        WHERE fao.status = 'active' AND fao.expires_at <= ?
    """, (current_time,))
    expired_offers = cur.fetchall()

    processed_count = 0
    for offer in expired_offers:
        try:
            # Mark offer as completed
            cur.execute("UPDATE free_agent_offers SET status = 'completed' WHERE id = ?", (offer['id'],))

            # Handle CPU teams (user_id = 1) differently from regular users
            if offer['user_id'] == 1:  # CPU team
                # For CPU teams, we need to find which specific CPU team made the offer
                # This requires storing the team_id in the offer or finding it another way
                # For now, we'll need to get the team_id from the CPU offer details
                # Since we don't store team_id in free_agent_offers, we'll need to find the CPU team that needs this player
                
                from cpu_ai import CPUAI
                cpu_ai = CPUAI()
                
                # Get player details
                cur.execute("SELECT registered_position, overall FROM players WHERE id = ?", (offer['player_id'],))
                player_info = cur.fetchone()
                
                if player_info:
                    # Find CPU teams that need this position
                    cur.execute("""
                        SELECT t.id, t.club_name
                        FROM teams t
                        WHERE t.id != 141
                        AND t.club_name IN (SELECT lt.team_name FROM league_teams lt WHERE lt.user_id = 1)
                        ORDER BY RANDOM()
                        LIMIT 10
                    """)
                    
                    cpu_teams = cur.fetchall()
                    winning_team = None
                    
                    # Find a CPU team that actually needs this player
                    for team in cpu_teams:
                        analysis = cpu_ai.analyze_team_composition(team['id'])
                        if analysis and analysis['total_players'] < 32:
                            needed_positions = cpu_ai.get_team_position_needs(team['id'])
                            if player_info['registered_position'] in needed_positions:
                                winning_team = team
                                break
                    
                    # If no team specifically needs this position, assign to first available team
                    if not winning_team and cpu_teams:
                        for team in cpu_teams:
                            analysis = cpu_ai.analyze_team_composition(team['id'])
                            if analysis and analysis['total_players'] < 32:
                                winning_team = team
                                break
                    
                    if winning_team:
                        pes6_team_id = winning_team['id']
                        
                        # Get player age for signing bonus calculation
                        cur.execute("SELECT age FROM players WHERE id = ?", (offer['player_id'],))
                        player_age_result = cur.fetchone()
                        player_age = player_age_result['age'] if player_age_result else 25

                        # Calculate signing bonus and yearly wage rise (same logic as user teams)
                        import random
                        if player_age <= 22:
                            signing_bonus_percentage = random.uniform(0.40, 0.50)
                            yearly_wage_rise = random.uniform(0.15, 0.25)
                        elif player_age <= 25:
                            signing_bonus_percentage = random.uniform(0.35, 0.45)
                            yearly_wage_rise = random.uniform(0.10, 0.20)
                        elif player_age <= 28:
                            signing_bonus_percentage = random.uniform(0.30, 0.40)
                            yearly_wage_rise = random.uniform(0.05, 0.15)
                        else:
                            signing_bonus_percentage = random.uniform(0.25, 0.35)
                            yearly_wage_rise = random.uniform(0.01, 0.10)

                        signing_bonus = int(offer['offered_salary'] * signing_bonus_percentage)

                        # Update player to CPU team
                        cur.execute("""
                            UPDATE players
                            SET salary = ?, contract_years_remaining = ?, yearly_wage_rise = ?, club_id = ?
                            WHERE id = ?
                        """, (offer['offered_salary'], offer['offered_contract_years'], yearly_wage_rise, pes6_team_id, offer['player_id']))

                        # Deduct signing bonus from CPU team budget
                        cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", (signing_bonus, pes6_team_id))

                        # Add signing bonus to player's career earnings
                        cur.execute("UPDATE players SET career_earnings = career_earnings + ? WHERE id = ?", (signing_bonus, offer['player_id']))

                        # Blacklist the player for CPU (user_id = 1) after CPU wins free agency auction
                        # This prevents other CPU teams from making offers for this player
                        try:
                            cur.execute("INSERT OR IGNORE INTO blacklist (user_id, player_id) VALUES (1, ?)", (offer['player_id'],))
                            app.logger.info(f"Blacklisted player {offer['player_name']} (ID: {offer['player_id']}) after CPU team {winning_team['club_name']} won free agency auction")
                        except Exception as blacklist_error:
                            app.logger.error(f"Error blacklisting player after CPU free agency win: {blacklist_error}")

                        # Post transfer news
                        title = f"Free Agent Signing: {offer['player_name']}"
                        content = f"{offer['player_name']} has signed with {winning_team['club_name']} (CPU) for €{offer['offered_salary']:,} per year for {offer['offered_contract_years']} years. Signing bonus: €{signing_bonus:,} ({(signing_bonus_percentage*100):.1f}% of salary). Yearly wage rise: {(yearly_wage_rise*100):.1f}%."
                        post_transfer_news(title, content, 1)  # user_id = 1 for CPU news

                        processed_count += 1
                        print(f"CPU team {winning_team['club_name']} signed free agent {offer['player_name']} for €{offer['offered_salary']:,}")
                        
            else:  # Regular user team
                # Get user's active team (handle multiple teams)
                cur.execute("SELECT id FROM league_teams WHERE user_id = ? ORDER BY id LIMIT 1", (offer['user_id'],))
                user_team = cur.fetchone()

                if user_team:
                    active_team_id = user_team['id']  # Use first team as active

                    # Add player to team (using consistent database approach)
                    cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)",
                               (active_team_id, offer['player_id']))

                    # Get the PES6 team ID for this league team
                    cur.execute("SELECT team_name FROM league_teams WHERE id = ?", (active_team_id,))
                    league_team_name = cur.fetchone()['team_name']

                    # Find the corresponding PES6 team ID
                    cur.execute("SELECT id FROM teams WHERE club_name = ?", (league_team_name,))
                    pes6_team_result = cur.fetchone()

                    if pes6_team_result:
                        pes6_team_id = pes6_team_result['id']

                        # Get player age for signing bonus calculation
                        cur.execute("SELECT age FROM players WHERE id = ?", (offer['player_id'],))
                        player_age_result = cur.fetchone()
                        player_age = player_age_result['age'] if player_age_result else 25

                        # Calculate signing bonus (25-50% of base salary, higher for younger players)
                        import random
                        if player_age <= 22:
                            signing_bonus_percentage = random.uniform(0.40, 0.50)  # 40-50% for very young players
                        elif player_age <= 25:
                            signing_bonus_percentage = random.uniform(0.35, 0.45)  # 35-45% for young players
                        elif player_age <= 28:
                            signing_bonus_percentage = random.uniform(0.30, 0.40)  # 30-40% for mid-age players
                        else:
                            signing_bonus_percentage = random.uniform(0.25, 0.35)  # 25-35% for older players

                        signing_bonus = int(offer['offered_salary'] * signing_bonus_percentage)

                        # Calculate yearly wage rise
                        if player_age <= 22:
                            yearly_wage_rise = random.uniform(0.15, 0.25)  # 15-25% for very young players
                        elif player_age <= 25:
                            yearly_wage_rise = random.uniform(0.10, 0.20)  # 10-20% for young players
                        elif player_age <= 28:
                            yearly_wage_rise = random.uniform(0.05, 0.15)  # 5-15% for mid-age players
                        else:
                            yearly_wage_rise = random.uniform(0.01, 0.10)  # 1-10% for older players

                        # Update player's salary, contract, yearly wage rise, and club_id to the PES6 team
                        cur.execute("""
                            UPDATE players
                            SET salary = ?, contract_years_remaining = ?, yearly_wage_rise = ?, club_id = ?
                            WHERE id = ?
                        """, (offer['offered_salary'], offer['offered_contract_years'], yearly_wage_rise, pes6_team_id, offer['player_id']))

                        # Deduct signing bonus from team budget
                        cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", (signing_bonus, pes6_team_id))

                        # Record signing bonus transaction in finances
                        add_user_movement(offer['user_id'], 'Signing Bonus',
                                        f"Signing bonus for {offer['player_name']} (Free Agency)", -signing_bonus)

                        # Add signing bonus to player's career earnings
                        cur.execute("UPDATE players SET career_earnings = career_earnings + ? WHERE id = ?", (signing_bonus, offer['player_id']))

                        app.logger.info(f"Updated player {offer['player_name']} club_id to PES6 team {pes6_team_id} ({league_team_name}) with signing bonus €{signing_bonus:,}")
                    else:
                        # Fallback: just update salary and contract if PES6 team not found
                        cur.execute("""
                            UPDATE players
                            SET salary = ?, contract_years_remaining = ?
                            WHERE id = ?
                        """, (offer['offered_salary'], offer['offered_contract_years'], offer['player_id']))

                        app.logger.warning(f"PES6 team not found for league team: {league_team_name}")

                    # Post transfer news to blog
                    title = f"Free Agent Transfer: {offer['player_name']}"
                    if pes6_team_result:
                        # Get the actual team name instead of using username
                        cur.execute("SELECT club_name FROM teams WHERE id = ?", (pes6_team_id,))
                        team_name_result = cur.fetchone()
                        actual_team_name = team_name_result['club_name'] if team_name_result else f"Team {pes6_team_id}"
                        
                        content = f"{offer['player_name']} has signed with {actual_team_name} for €{offer['offered_salary']:,} per year for {offer['offered_contract_years']} years. Signing bonus: €{signing_bonus:,} ({(signing_bonus_percentage*100):.1f}% of salary). Yearly wage rise: {(yearly_wage_rise*100):.1f}%."
                    else:
                        content = f"{offer['player_name']} has signed with {offer['username']}'s team for €{offer['offered_salary']:,} per year for {offer['offered_contract_years']} years."
                    post_transfer_news(title, content, offer['user_id'])

                    processed_count += 1
                    app.logger.info(f"Processed expired offer: {offer['player_name']} -> {offer['username']}")
        except Exception as e:
            app.logger.error(f"Error processing expired offer {offer['id']}: {e}")

    db_helper.commit()
    cur.close()

    return processed_count

@app.route('/free_agency/check_expired_offers')
def check_expired_offers_route():
    """Background task route to check and process expired offers"""
    processed_count = check_expired_offers()
    return jsonify({'processed': processed_count})

@app.route('/free_agency/force_check_expired')
@login_required
def force_check_expired():
    """Manual trigger to check expired offers (for testing)"""
    processed_count = check_expired_offers()
    return jsonify({'processed': processed_count})



@app.route('/free_agency/process_expired_manual', methods=['POST'])
@login_required
def process_expired_offers_manual():
    """Manual button to process expired offers from the free agency page"""
    try:
        # Use the same logic as in the free agency page load
        cur = db_helper.get_cursor()

        # Get expired offers using proper datetime comparison
        from datetime import datetime
        current_time = datetime.now()

        # Debug: Check what offers exist
        cur.execute("SELECT COUNT(*) as total FROM free_agent_offers WHERE status = 'active'")
        total_active = cur.fetchone()['total']

        # Use a more robust comparison - get all active offers and check in Python
        cur.execute("""
            SELECT fao.id, fao.player_id, fao.user_id, fao.offered_salary, fao.offered_contract_years,
                   fao.expires_at, p.player_name, u.username
            FROM free_agent_offers fao
            JOIN players p ON fao.player_id = p.id
            JOIN users u ON fao.user_id = u.id
            WHERE fao.status = 'active'
        """)
        all_active_offers = cur.fetchall()

        # Filter expired offers in Python for better control
        expired_offers = []
        for offer in all_active_offers:
            try:
                expires_at_str = offer['expires_at']
                expires_at = None

                # Try different parsing methods
                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                except:
                    try:
                        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                    except:
                        # String comparison fallback
                        if expires_at_str <= current_time.isoformat():
                            expires_at = datetime.min

                if expires_at and current_time > expires_at:
                    expired_offers.append(offer)

            except Exception as e:
                app.logger.error(f"Error parsing expiration time for offer {offer['id']}: {e}")

        processed_count = 0
        for offer in expired_offers:
            try:
                app.logger.info(f"Manually processing expired offer: {offer['player_name']} -> {offer['username']} (expired at {offer['expires_at']})")

                # Mark offer as completed
                cur.execute("UPDATE free_agent_offers SET status = 'completed' WHERE id = ?", (offer['id'],))

                # Get user's active team (handle multiple teams)
                cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = ? ORDER BY id LIMIT 1", (offer['user_id'],))
                user_team = cur.fetchone()

                if user_team:
                    active_team_id = user_team['id']
                    team_name = user_team['team_name']

                    # Find the corresponding PES6 team ID
                    cur.execute("SELECT id FROM teams WHERE club_name = ?", (team_name,))
                    pes6_team_result = cur.fetchone()

                    if pes6_team_result:
                        pes6_team_id = pes6_team_result['id']

                        # Update player's salary, contract, and club_id to the PES6 team
                        cur.execute("""
                            UPDATE players
                            SET salary = ?, contract_years_remaining = ?, club_id = ?
                            WHERE id = ?
                        """, (offer['offered_salary'], offer['offered_contract_years'], pes6_team_id, offer['player_id']))

                        # Add player to team_players table for compatibility
                        cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)",
                                   (active_team_id, offer['player_id']))

                        # Post transfer news to blog
                        title = f"Free Agent Transfer: {offer['player_name']}"
                        content = f"{offer['player_name']} has signed with {offer['username']}'s team for €{offer['offered_salary']:,} per year for {offer['offered_contract_years']} years."
                        post_transfer_news(title, content, offer['user_id'])

                        processed_count += 1
                        app.logger.info(f"Successfully processed expired offer: {offer['player_name']} -> {offer['username']}")

                    else:
                        app.logger.error(f"PES6 team not found for league team: {team_name}")
                else:
                    app.logger.error(f"No team found for user {offer['user_id']} ({offer['username']})")

            except Exception as e:
                app.logger.error(f"Error processing expired offer {offer['id']}: {e}")

        if processed_count > 0:
            db_helper.commit()
            flash(f'✅ Successfully processed {processed_count} expired free agent offers!', 'success')
        else:
            flash('ℹ️ No expired offers found to process.', 'info')

        cur.close()

    except Exception as e:
        app.logger.error(f"Error in manual expired offers processing: {e}")
        flash(f'❌ Error processing expired offers: {e}', 'danger')

    return redirect(url_for('free_agency'))

@app.route('/free_agency/sign_player/<int:offer_id>', methods=['POST'])
@login_required
def sign_expired_player(offer_id):
    """Sign a player from an expired offer"""
    cur = db_helper.get_cursor()

    try:
        # Get the offer details with player data for calculations
        cur.execute("""
            SELECT fao.id, fao.player_id, fao.user_id, fao.offered_salary, fao.offered_contract_years,
                   fao.expires_at, fao.status, p.player_name, p.age, u.username, t.budget
            FROM free_agent_offers fao
            JOIN players p ON fao.player_id = p.id
            JOIN users u ON fao.user_id = u.id
            JOIN league_teams lt ON lt.user_id = u.id
            WHERE fao.id = ? AND fao.status = 'active'
        """, (offer_id,))
        offer = cur.fetchone()

        if not offer:
            flash('Offer not found or already processed.', 'danger')
            return redirect(url_for('free_agency'))

        # Check if offer belongs to current user
        if offer['user_id'] != current_user.id:
            flash('You can only sign players from your own offers.', 'danger')
            return redirect(url_for('free_agency'))

        # Check if offer is expired (frontend should handle this, but double-check)
        from datetime import datetime
        current_time = datetime.now()
        try:
            expires_at = datetime.fromisoformat(offer['expires_at'])
            if current_time <= expires_at:
                flash('This offer has not expired yet.', 'warning')
                return redirect(url_for('free_agency'))
        except:
            # If we can't parse the date, proceed (assume it's expired)
            pass

        # Calculate signing bonus and yearly wage rise
        import random
        from contract_renewal import ContractRenewalManager

        # Calculate signing bonus (25-50% of base salary, higher for younger players)
        player_age = offer['age']
        if player_age <= 22:
            signing_bonus_percentage = random.uniform(0.40, 0.50)  # 40-50% for very young players
        elif player_age <= 25:
            signing_bonus_percentage = random.uniform(0.35, 0.45)  # 35-45% for young players
        elif player_age <= 28:
            signing_bonus_percentage = random.uniform(0.30, 0.40)  # 30-40% for mid-age players
        else:
            signing_bonus_percentage = random.uniform(0.25, 0.35)  # 25-35% for older players

        signing_bonus = int(offer['offered_salary'] * signing_bonus_percentage)

        # Calculate yearly wage rise (same logic as contract renewal)
        if player_age <= 22:
            yearly_wage_rise = random.uniform(0.15, 0.25)  # 15-25% for very young players
        elif player_age <= 25:
            yearly_wage_rise = random.uniform(0.10, 0.20)  # 10-20% for young players
        elif player_age <= 28:
            yearly_wage_rise = random.uniform(0.05, 0.15)  # 5-15% for mid-age players
        else:
            yearly_wage_rise = random.uniform(0.01, 0.10)  # 1-10% for older players

        # Process the signing
        cur.execute("UPDATE free_agent_offers SET status = 'completed' WHERE id = ?", (offer_id,))

        # Get user's active team
        cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = ? ORDER BY id LIMIT 1", (current_user.id,))
        user_team = cur.fetchone()

        if user_team:
            active_team_id = user_team['id']
            team_name = user_team['team_name']

            # Find the corresponding PES6 team ID
            cur.execute("SELECT id FROM teams WHERE club_name = ?", (team_name,))
            pes6_team_result = cur.fetchone()

            if pes6_team_result:
                pes6_team_id = pes6_team_result['id']

                # Update player with new salary, contract years, yearly wage rise, and club
                cur.execute("""
                    UPDATE players
                    SET salary = ?, contract_years_remaining = ?, yearly_wage_rise = ?, club_id = ?
                    WHERE id = ?
                """, (offer['offered_salary'], offer['offered_contract_years'], yearly_wage_rise, pes6_team_id, offer['player_id']))

                # Deduct signing bonus from team budget
                cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", (signing_bonus, pes6_team_id))

                # Record signing bonus transaction in finances
                add_user_movement(current_user.id, 'Signing Bonus',
                                f"Signing bonus for {offer['player_name']} (Free Agency)", -signing_bonus)

                # Add to team_players
                cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)",
                           (active_team_id, offer['player_id']))

                # Post transfer news with signing bonus info
                title = f"Free Agent Transfer: {offer['player_name']}"
                content = f"{offer['player_name']} has signed with {offer['username']}'s team for €{offer['offered_salary']:,} per year for {offer['offered_contract_years']} years. Signing bonus: €{signing_bonus:,} ({(signing_bonus_percentage*100):.1f}% of salary). Yearly wage rise: {(yearly_wage_rise*100):.1f}%."
                post_transfer_news(title, content, current_user.id)

                db_helper.commit()
                flash(f'✅ Successfully signed {offer["player_name"]} to your team! Signing bonus: €{signing_bonus:,} deducted from budget.', 'success')
            else:
                flash('Error: Could not find your team in the database.', 'danger')
        else:
            flash('Error: You do not have a team assigned.', 'danger')

    except Exception as e:
        db_helper.get_connection().rollback()
        flash(f'Error signing player: {e}', 'danger')
    finally:
        cur.close()

    return redirect(url_for('free_agency'))

@app.route('/market_bazaar')
@login_required
def market_bazaar():
    """Market bazaar page showing transfer list and CPU offers"""
    cur = db_helper.get_cursor()

    try:
        # Light cleanup only - move heavy processing to separate route
        # Remove offers for completed/expired listings
        cur.execute("""
            UPDATE market_bazaar_offers
            SET status = 'expired'
            WHERE status = 'active'
            AND listing_id IN (
                SELECT id FROM market_bazaar_listings
                WHERE status != 'active' OR expires_at < datetime('now')
            )
        """)

        # Mark expired listings as expired
        cur.execute("""
            UPDATE market_bazaar_listings
            SET status = 'expired'
            WHERE status = 'active'
            AND expires_at < datetime('now')
        """)

        db_helper.commit()
    except Exception as e:
        app.logger.error(f"Error in light cleanup: {e}")
        db_helper.get_connection().rollback()

    try:
        # Table 1: All transfer listed players (both user and CPU) - "Transfer List"
        cur.execute("""
            SELECT p.*, t.club_name, mbl.asking_price, mbl.expires_at, mbl.id as listing_id,
                   mbl.listing_type, mbl.team_id, mbl.salary_support_percentage,
                   CASE
                       WHEN mbl.team_id IN (SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?)
                       THEN 'own_user'
                       WHEN mbl.team_id IN (SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id != 1 AND lt.user_id != ?)
                       THEN 'other_user'
                       ELSE 'cpu'
                   END as owner_type
            FROM market_bazaar_listings mbl
            JOIN players p ON mbl.player_id = p.id
            JOIN teams t ON p.club_id = t.id
            WHERE mbl.status = 'active'
            AND mbl.listing_type IN ('user_sale', 'cpu_sale', 'user_loan', 'cpu_loan')
            AND p.loaned_by IS NULL  -- Exclude loaned players from transfer listings
            ORDER BY p.registered_position, p.market_value DESC
        """, (current_user.id, current_user.id))

        transfer_listed_players = cur.fetchall()

        # Table 2: CPU offers for user UNLISTED players only (cpu_user_offer type)
        cur.execute("""
            SELECT mbo.*, p.id as player_id, p.player_name, p.registered_position, p.age, p.market_value,
                   cpu_t.club_name as buyer_team_name, mbl.asking_price,
                   'unlisted' as offer_type
            FROM market_bazaar_offers mbo
            JOIN market_bazaar_listings mbl ON mbo.listing_id = mbl.id
            JOIN players p ON mbl.player_id = p.id
            JOIN teams cpu_t ON mbo.buyer_team_id = cpu_t.id
            JOIN league_teams cpu_lt ON cpu_t.id = cpu_lt.id
            WHERE mbo.status = 'active'
            AND mbl.listing_type = 'cpu_user_offer'  -- Only unlisted player offers (exclude user_sale to avoid errors)
            AND mbl.team_id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?
            )
            AND cpu_lt.user_id = 1  -- Only CPU teams as buyers
            AND p.loaned_by IS NULL  -- Exclude loaned players from negotiations
        """, (current_user.id,))

        cpu_offers_for_user_listed = cur.fetchall()

        # Table 3: User offers to CPU players
        cur.execute("""
            SELECT uco.*, p.player_name, p.registered_position, p.age, p.market_value,
                   cpu_t.club_name as seller_team_name, uco.created_at as offer_date
            FROM user_cpu_offers uco
            JOIN players p ON uco.player_id = p.id
            JOIN teams cpu_t ON uco.seller_team_id = cpu_t.id
            WHERE uco.buyer_team_id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?
            )
            ORDER BY uco.created_at DESC
        """, (current_user.id,))

        user_offers_to_cpu = cur.fetchall()

        # Table 4: Empty (no separate table needed - already covered above)
        cpu_interest_unlisted = []

        # Table 4: User players (for listing) - exclude blacklisted players
        cur.execute("""
            SELECT p.*, t.club_name, 'user_players' as table_type
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE t.id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?
            )
            AND p.id NOT IN (
                SELECT player_id FROM blacklist WHERE user_id = 1
            )
            ORDER BY p.registered_position, p.market_value DESC
        """, (current_user.id,))

        user_players = cur.fetchall()

        # Get or set next market activity time
        from datetime import datetime, timedelta

        # Check if we have a stored next market activity time
        cur.execute("SELECT value FROM app_settings WHERE key = 'next_market_activity'")
        stored_time = cur.fetchone()

        if stored_time:
            next_market_activity = stored_time['value']
        else:
            # First time - set it to 4 hours from now (for production)
            next_market_activity = get_next_market_activity_time()
            cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('next_market_activity', ?)",
                       (next_market_activity,))
            db_helper.commit()

        return render_template('market_bazaar.html',
                             transfer_listed_players=transfer_listed_players,
                             cpu_offers_for_user_listed=cpu_offers_for_user_listed,
                             user_offers_to_cpu=user_offers_to_cpu,
                             cpu_interest_unlisted=cpu_interest_unlisted,
                             user_players=user_players,
                             next_market_activity=next_market_activity)

    except Exception as e:
        app.logger.error(f"Error in market_bazaar: {str(e)}")
        # Get or set next market activity time for error case
        from datetime import datetime, timedelta

        # Check if we have a stored next market activity time
        cur.execute("SELECT value FROM app_settings WHERE key = 'next_market_activity'")
        stored_time = cur.fetchone()

        if stored_time:
            next_market_activity = stored_time['value']
            # Check if the stored time is in the past
            stored_datetime = datetime.fromisoformat(next_market_activity)
            if stored_datetime <= datetime.now():
                # Reset to 4 hours from now if the stored time is in the past
                next_market_activity = get_next_market_activity_time()
                cur.execute("UPDATE app_settings SET value = ? WHERE key = 'next_market_activity'",
                           (next_market_activity,))
                db_helper.commit()
        else:
            # First time - set it to 4 hours from now (for production)
            next_market_activity = get_next_market_activity_time()
            cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('next_market_activity', ?)",
                       (next_market_activity,))
            db_helper.commit()

        return render_template('market_bazaar.html',
                             transfer_listed_players=[],
                             cpu_offers_for_user_listed=[],
                             user_offers_to_cpu=[],
                             cpu_interest_unlisted=[],
                             user_players=[],
                             next_market_activity=next_market_activity,
                             error=str(e))
    finally:
        cur.close()

@app.route('/market_bazaar/mendes_sell', methods=['POST'])
@login_required
def mendes_sell():
    """Jorge Mendes quick sell - generate offers from 50 clubs"""
    try:
        data = request.get_json()
        player_id = data.get('player_id')

        if not player_id:
            return jsonify({'success': False, 'message': 'Player ID is required'})

        cur = db_helper.get_cursor()

        # Get player details
        cur.execute("""
            SELECT p.*, t.club_name, t.budget, t.id as team_id
            FROM players p
            JOIN teams t ON p.club_id = t.id
            JOIN league_teams lt ON t.id = lt.id
            WHERE p.id = ? AND lt.user_id = ?
        """, (player_id, current_user.id))

        player = cur.fetchone()
        if not player:
            return jsonify({'success': False, 'message': 'Player not found or not owned by user'})

        # Convert to dict
        player = dict(player)

        # Note: Jorge Mendes direct sale doesn't create listings, so no need to check for existing listings

        # Get player's market value from database (don't recalculate)
        market_value = player.get('market_value', 0) or 0
        
        # Only calculate fair_salary for toxicity calculation
        player_data = {
            'overall': player['overall'],
            'registered_position': player['registered_position'],
            'age': player['age'],
            'club_id': player['club_id']
        }

        # Add skill data if available
        skill_columns = [
            'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
            'response', 'agility', 'dribble_accuracy', 'dribble_speed',
            'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
            'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
            'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
            'team_work', 'condition_fitness'
        ]

        for skill in skill_columns:
            if skill in player:
                player_data[skill] = player[skill]
            else:
                player_data[skill] = 50  # Default value

        # Calculate fair salary using the same method as contract_renewal.py
        # This ensures consistency across the system
        import pandas as pd
        player_row = pd.Series(player_data)
        pos_avg_df = game_mechanics.get_cached_position_averages('pes6_league_db.sqlite')
        
        skills = ['attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                 'response', 'agility', 'dribble_accuracy', 'dribble_speed',
                 'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
                 'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy', 'swerve',
                 'heading', 'jump', 'technique', 'aggression', 'mentality', 'goal_keeping',
                 'team_work', 'consistency', 'condition_fitness']
        
        binaries = ['dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking',
                   'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 'middle_shooting',
                   'side', 'centre', 'penalties', 'one_touch_pass', 'outside', 'marking', 'sliding',
                   'covering', 'd_line_control', 'penalty_stopper', 'one_on_one_stopper', 'long_throw']
        
        # Calculate base salary
        base_salary = game_mechanics.calculate_player_salary_base(player_row, pos_avg_df, skills, binaries)
        
        # Apply defensive position boost (same as contract_renewal.py)
        registered_position = player.get('registered_position')
        try:
            if isinstance(registered_position, str):
                pos_int = int(registered_position.strip())
            else:
                pos_int = int(registered_position)
            
            if pos_int in [0, 2, 3, 4]:
                base_salary = int(base_salary * 1.75)
        except (ValueError, TypeError):
            pass
        
        # Apply random adjustment (market variation ±15%)
        fair_salary = game_mechanics.apply_random_salary_adjustment(base_salary)
        
        # Calculate toxicity based on contract overpayment
        current_salary = player.get('salary', 0) or 0
        contract_years = player.get('contract_years_remaining', 1) or 1
        yearly_wage_raise = 0.03  # 3% annual increase
        
        # Toxicity: positive if overpaid (bad contract), negative if underpaid (good contract)
        # Overpaid = current_salary > fair_salary (reduces sale price)
        # Underpaid = current_salary < fair_salary (increases sale price)
        toxicity = (current_salary - fair_salary) * contract_years * (1 + yearly_wage_raise)
        
        # Calculate sale price: 50-75% of market value, adjusted by toxicity
        import random
        base_percentage = random.uniform(0.50, 0.75)
        sale_price = int((market_value * base_percentage) - toxicity)
        
        # No minimum cap - toxic contracts can result in negative prices (user pays to offload)
        
        # Apply 25% commission - always positive, calculated on absolute value
        commission = int(abs(sale_price) * 0.25)
        
        # Net amount calculation:
        # If sale_price >= 0: user receives (sale_price - commission)
        # If sale_price < 0: user pays (abs(sale_price) + commission)
        if sale_price >= 0:
            net_amount = sale_price - commission
        else:
            net_amount = sale_price - commission  # Both negative, so total cost increases
        
        # Find CPU team with least players in this position
        cur.execute("""
            SELECT t.id, t.club_name, t.budget,
                   COUNT(CASE WHEN p.registered_position = ? THEN 1 END) as position_count,
                   COUNT(p.id) as total_players
            FROM teams t
            LEFT JOIN players p ON t.id = p.club_id
            WHERE t.club_name IN (SELECT team_name FROM league_teams WHERE user_id = 1)
            AND t.budget >= ?
            GROUP BY t.id, t.club_name, t.budget
            HAVING total_players < 32
            ORDER BY position_count ASC, RANDOM()
            LIMIT 1
        """, (player['registered_position'], sale_price))

        buyer_team = cur.fetchone()
        
        if not buyer_team:
            return jsonify({
                'success': False, 
                'message': 'No CPU teams available with sufficient budget or roster space'
            })
        
        buyer_team_id = buyer_team['id']
        buyer_team_name = buyer_team['club_name']
        seller_team_id = player['team_id']
        
        # Execute the transfer
        # 1. Transfer player to new club
        cur.execute("""
            UPDATE players 
            SET club_id = ?
            WHERE id = ?
        """, (buyer_team_id, player_id))
        
        # 2. Update buyer team budget and salaries
        # Note: if sale_price is negative, buyer actually receives money to take the player
        cur.execute("""
            UPDATE teams 
            SET budget = budget - ?,
                total_salaries = total_salaries + ?,
                available_cap = available_cap - ?
            WHERE id = ?
        """, (sale_price, current_salary, current_salary, buyer_team_id))
        
        # 3. Update seller team (user's team) budget and salaries
        cur.execute("""
            UPDATE teams
            SET budget = budget + ?,
                total_salaries = total_salaries - ?,
                available_cap = available_cap + ?
            WHERE id = ?
        """, (net_amount, current_salary, current_salary, seller_team_id))
        
        # 4. Register movement in user_movements for financial tracking
        # Get current user budget to calculate balance_after
        cur.execute("SELECT budget FROM teams WHERE id = ?", (seller_team_id,))
        current_budget_result = cur.fetchone()
        balance_after = current_budget_result['budget'] if current_budget_result else net_amount
        
        # Use the standard add_user_movement function
        movement_type = 'Transfer In' if net_amount >= 0 else 'Transfer Out'
        add_user_movement(
            current_user.id,
            movement_type,
            f"Jorge Mendes sale: {player['player_name']} to {buyer_team_name}",
            net_amount
        )
        
        # 5. Create blog post announcing the sale
        from datetime import datetime
        
        # Simple blog post with just the essential information
        if sale_price >= 0:
            blog_title = f"Transfer: {player['player_name']} to {buyer_team_name}"
            blog_content = f"""
<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; color: white;">
    <h3>🎯 Transfer Completed</h3>
    <p><strong>{player['player_name']}</strong> has joined <strong>{buyer_team_name}</strong> from <strong>{player['club_name']}</strong>.</p>
    <p><strong>Fee:</strong> €{sale_price:,}</p>
    <p style="margin-top: 10px; font-size: 0.9em; opacity: 0.9;">Agent: Jorge Mendes | Commission: €{commission:,}</p>
</div>
"""
        else:
            blog_title = f"Transfer: {player['player_name']} to {buyer_team_name}"
            blog_content = f"""
<div style="background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); padding: 20px; border-radius: 10px; color: white;">
    <h3>⚠️ Compensation Transfer</h3>
    <p><strong>{player['player_name']}</strong> has joined <strong>{buyer_team_name}</strong> from <strong>{player['club_name']}</strong>.</p>
    <p><strong>Compensation Paid:</strong> €{abs(sale_price):,}</p>
    <p><strong>Total Cost:</strong> €{abs(net_amount):,} (includes €{commission:,} agent commission)</p>
    <p style="margin-top: 10px; font-size: 0.9em; opacity: 0.9;">Agent: Jorge Mendes</p>
</div>
"""
        
        # Post to blog using correct function
        post_transfer_news(blog_title, blog_content, user_id=current_user.id)
        
        db_helper.commit()
        
        return jsonify({
            'success': True,
            'buyer_team': buyer_team_name,
            'best_offer': sale_price,
            'commission': commission,
            'net_amount': net_amount,
            'toxicity': int(toxicity),
            'market_value': market_value,
            'message': f'Jorge Mendes sold {player["player_name"]} to {buyer_team_name}!'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        if hasattr(db_helper, 'get_connection'):
            db_helper.get_connection().rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

# OLD IMPLEMENTATION REMOVED - Jorge Mendes now uses direct sale with toxicity calculation
# The old loop-based offer system has been replaced with instant placement

@app.route('/market_bazaar/process_cpu_offers', methods=['POST'])
@login_required
def process_cpu_offers():
    """Process CPU offers in the background to avoid timeout issues"""
    try:
        cur = db_helper.get_cursor()

        # Remove offers for players who are no longer on the listing team
        cur.execute("""
            UPDATE market_bazaar_listings
            SET status = 'expired'
            WHERE status = 'active'
            AND player_id IN (
                SELECT p.id FROM players p
                WHERE p.club_id != (
                    SELECT mbl.team_id FROM market_bazaar_listings mbl
                    WHERE mbl.player_id = p.id AND mbl.status = 'active'
                )
            )
        """)

        # Auto-complete CPU offers for CPU-listed players (CPU teams accept their own offers)
        cur.execute("""
            SELECT mbo.id, mbo.listing_id, mbo.buyer_team_id, mbo.offered_price,
                   mbl.player_id, mbl.team_id as seller_team_id, p.player_name
            FROM market_bazaar_offers mbo
            JOIN market_bazaar_listings mbl ON mbo.listing_id = mbl.id
            JOIN players p ON mbl.player_id = p.id
            WHERE mbo.status = 'active'
            AND mbl.status = 'active'
            AND mbl.listing_type = 'cpu_sale'
            AND mbo.buyer_team_id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = 1
            )
        """)

        cpu_offers = cur.fetchall()
        completed_count = 0

        for offer in cpu_offers:
            try:
                # Transfer player
                cur.execute("UPDATE players SET club_id = ? WHERE id = ?",
                           (offer['buyer_team_id'], offer['player_id']))

                # Update budgets
                cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?",
                           (offer['offered_price'], offer['seller_team_id']))
                cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?",
                           (offer['offered_price'], offer['buyer_team_id']))

                # Mark offer and listing as completed
                cur.execute("UPDATE market_bazaar_offers SET status = 'completed' WHERE id = ?", (offer['id'],))
                cur.execute("UPDATE market_bazaar_listings SET status = 'completed' WHERE id = ?", (offer['listing_id'],))

                # Add player to blacklist (ignore if already exists)
                cur.execute("INSERT OR IGNORE INTO blacklist (user_id, player_id) VALUES (1, ?)", (offer['player_id'],))

                app.logger.info(f"Auto-completed CPU deal: {offer['player_name']} transferred for €{offer['offered_price']:,}")
                completed_count += 1

            except Exception as e:
                app.logger.error(f"Error auto-completing CPU offer {offer['id']}: {e}")

        db_helper.commit()
        cur.close()

        return jsonify({
            'success': True,
            'message': f'Processed {completed_count} CPU offers',
            'completed_count': completed_count
        })

    except Exception as e:
        app.logger.error(f"Error processing CPU offers: {e}")
        db_helper.get_connection().rollback()
        if cur:
            cur.close()
        return jsonify({'error': f'Error processing CPU offers: {str(e)}'}), 500

@app.route('/market_bazaar/get_player_salary/<int:player_id>')
@login_required
def get_player_salary(player_id):
    """Get player's current salary for loan listing preview"""
    try:
        cur = db_helper.get_cursor()
        cur.execute("SELECT salary FROM players WHERE id = ?", (player_id,))
        player = cur.fetchone()
        cur.close()
        
        if player:
            return jsonify({'salary': player['salary'] or 0})
        else:
            return jsonify({'error': 'Player not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/market_bazaar/list_player', methods=['POST'])
@login_required
def list_player_for_sale():
    """List a player for sale in the market bazaar"""
    try:
        player_id = request.form.get('player_id')
        asking_price_str = request.form.get('asking_price', '0')
        asking_price = int(asking_price_str) if asking_price_str else 0
        listing_type = request.form.get('listing_type', 'user_sale')  # user_sale or user_loan
        salary_support_percentage_str = request.form.get('salary_support_percentage', '0')
        salary_support_percentage = float(salary_support_percentage_str) if salary_support_percentage_str else 0.0

        cur = db_helper.get_cursor()

        # Check if player is blacklisted
        if is_blacklisted(current_user.id, player_id):
            return jsonify({'error': 'This player is no longer available for listing.'}), 403

        # Verify player belongs to user
        cur.execute("""
            SELECT p.*, t.club_name
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE p.id = ? AND t.id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?
            )
        """, (player_id, current_user.id))

        player = cur.fetchone()
        if not player:
            return jsonify({'error': 'Player not found or not owned by you'}), 404

        # Check if player is on loan (loaned_by field)
        if player['loaned_by']:
            return jsonify({'error': 'Cannot list loaned players for sale/loan'}), 403

        # Check if player is already listed
        cur.execute("""
            SELECT id FROM market_bazaar_listings
            WHERE player_id = ? AND status = 'active'
        """, (player_id,))

        if cur.fetchone():
            return jsonify({'error': 'Player is already listed'}), 400

        # For loans: Calculate subsidy amount (negative asking_price)
        # The asking_price will be negative to represent the subsidy
        if listing_type == 'user_loan' and salary_support_percentage > 0:
            player_salary = player['salary'] or 0
            subsidy_amount = int(player_salary * (salary_support_percentage / 100))
            # Store as negative value to show it's a subsidy
            asking_price = -subsidy_amount
        elif listing_type == 'user_loan':
            # Loan fee (optional, positive value)
            asking_price = asking_price
            salary_support_percentage = 0.0

        # Create listing
        from datetime import datetime, timedelta
        expires_at = datetime.now() + timedelta(days=14)  # 2 weeks

        cur.execute("""
            INSERT INTO market_bazaar_listings (player_id, team_id, asking_price, expires_at, status, listing_type, salary_support_percentage)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
        """, (player_id, player['club_id'], asking_price, expires_at.isoformat(), listing_type, salary_support_percentage))

        db_helper.commit()
        cur.close()

        action = "loaned" if listing_type == "user_loan" else "sold"
        if listing_type == 'user_loan' and salary_support_percentage > 0:
            subsidy_amount = int((player['salary'] or 0) * (salary_support_percentage / 100))
            message = f'{player["player_name"]} has been listed for loan. You will pay {salary_support_percentage:.0f}% of salary (€{subsidy_amount:,}/year)'
        elif listing_type == 'user_loan':
            message = f'{player["player_name"]} has been listed for loan at €{asking_price:,}'
        else:
            message = f'{player["player_name"]} has been listed for {action} at €{asking_price:,}'
        
        return jsonify({
            'success': True,
            'message': message
        })

    except Exception as e:
        app.logger.error(f"Error listing player: {str(e)}")
        return jsonify({'error': f'Error listing player: {str(e)}'}), 500

@app.route('/market_bazaar/cpu_offer_unlisted/<int:player_id>', methods=['POST'])
@login_required
def cpu_offer_unlisted_player(player_id):
    """Generate CPU offers for user unlisted players"""
    try:
        cur = db_helper.get_cursor()

        # Verify player belongs to user
        cur.execute("""
            SELECT p.*, t.club_name
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE p.id = ? AND t.id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?
            )
        """, (player_id, current_user.id))

        player = cur.fetchone()
        if not player:
            return jsonify({'error': 'Player not found or not owned by you'}), 404

        # Use CPU AI to get interested teams
        from cpu_ai import cpu_ai
        player_dict = dict(player)
        interested_teams = cpu_ai.get_interested_cpu_teams_for_player(player_dict)

        if not interested_teams:
            return jsonify({'error': 'No CPU teams are interested in this player at the moment.'}), 400

        # Generate offers (similar to sell_player route)
        proposals = []
        import random

        for idx, team_data in enumerate(interested_teams[:5]):  # Max 5 offers
            cpu_team_name = team_data['team_name']

            # Fetch the club_id for this CPU team
            cur.execute("SELECT id FROM teams WHERE club_name = ?", (cpu_team_name,))
            team_row = cur.fetchone()
            club_id = team_row['id'] if team_row else None

            # Generate offer based on AI analysis
            if team_data['is_toxic']:
                # For toxic contracts, offer negative value
                base_offer = random.randint(team_data['min_offer'], team_data['max_offer'])
                offer_cash = base_offer
            else:
                # Normal offer range
                offer_cash = random.randint(team_data['min_offer'], team_data['max_offer'])

            proposals.append({
                'proposal_id': idx + 1,
                'cpu_team': cpu_team_name,
                'cash': offer_cash,
                'reason': team_data['reason'],
                'is_toxic': team_data['is_toxic']
            })

        cur.close()
        return jsonify({
            'success': True,
            'proposals': proposals,
            'player_name': player['player_name']
        })

    except Exception as e:
        app.logger.error(f"Error generating CPU offers: {str(e)}")
        return jsonify({'error': f'Error generating offers: {str(e)}'}), 500

@app.route('/market_bazaar/reject_offer/<int:offer_id>', methods=['POST'])
@login_required
def reject_market_offer(offer_id):
    """Reject a market bazaar offer"""
    try:
        cur = db_helper.get_cursor()

        # Get offer details with additional validation
        cur.execute("""
            SELECT mbo.*, mbl.player_id, mbl.team_id, p.player_name, mbl.status as listing_status
            FROM market_bazaar_offers mbo
            JOIN market_bazaar_listings mbl ON mbo.listing_id = mbl.id
            JOIN players p ON mbl.player_id = p.id
            WHERE mbo.id = ? AND mbo.status = 'active' AND mbl.status = 'active'
        """, (int(offer_id),))

        offer = cur.fetchone()
        if not offer:
            return jsonify({'error': 'Offer not found or no longer active'}), 404

        # Additional validation: check if player is still on the listing team
        cur.execute("SELECT club_id FROM players WHERE id = ?", (offer['player_id'],))
        player_team = cur.fetchone()
        if not player_team or player_team['club_id'] != offer['team_id']:
            return jsonify({'error': 'Player is no longer available'}), 404

        # Verify the listing belongs to the user
        cur.execute("""
            SELECT t.id FROM teams t
            WHERE t.id = ? AND t.id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?
            )
        """, (offer['team_id'], current_user.id))

        if not cur.fetchone():
            return jsonify({'error': 'You do not own this player listing'}), 403

        # Mark offer as rejected
        cur.execute("UPDATE market_bazaar_offers SET status = 'rejected' WHERE id = ?", (offer_id,))

        db_helper.commit()
        cur.close()

        return jsonify({'success': True, 'message': f'Offer for {offer["player_name"]} rejected'})

    except Exception as e:
        app.logger.error(f"Error rejecting market offer: {str(e)}")
        db_helper.get_connection().rollback()
        cur.close()
        return jsonify({'error': f'Error rejecting offer: {str(e)}'}), 500

@app.route('/market_bazaar/remove_listing/<int:listing_id>', methods=['POST'])
@login_required
def remove_listing(listing_id):
    """Remove a player listing from the market"""
    try:
        cur = db_helper.get_cursor()

        # Get listing details and verify ownership
        cur.execute("""
            SELECT mbl.*, p.player_name
            FROM market_bazaar_listings mbl
            JOIN players p ON mbl.player_id = p.id
            WHERE mbl.id = ? AND mbl.status = 'active'
        """, (listing_id,))

        listing = cur.fetchone()
        if not listing:
            return jsonify({'error': 'Listing not found or no longer active'}), 404

        # Verify the listing belongs to the user
        cur.execute("""
            SELECT t.id FROM teams t
            WHERE t.id = ? AND t.id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?
            )
        """, (listing['team_id'], current_user.id))

        if not cur.fetchone():
            return jsonify({'error': 'You do not own this listing'}), 403

        # Remove the listing
        cur.execute("UPDATE market_bazaar_listings SET status = 'cancelled' WHERE id = ?", (listing_id,))

        # Cancel any active offers for this listing
        cur.execute("UPDATE market_bazaar_offers SET status = 'cancelled' WHERE listing_id = ? AND status = 'active'", (listing_id,))

        db_helper.commit()
        cur.close()

        return jsonify({'success': True, 'message': f'{listing["player_name"]} removed from transfer list'})

    except Exception as e:
        app.logger.error(f"Error removing listing: {str(e)}")
        db_helper.get_connection().rollback()
        cur.close()
        return jsonify({'error': f'Error removing listing: {str(e)}'}), 500

@app.route('/market_bazaar/accept_cpu_offer_direct', methods=['POST'])
@login_required
def accept_cpu_offer_direct():
    """Accept a direct CPU offer for unlisted user player"""
    cur = None
    try:
        # Validate request data
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        player_id = data.get('player_id')
        offered_price = data.get('offered_price')
        buyer_team_id = data.get('buyer_team_id')

        # Validate required fields
        if not all([player_id, offered_price, buyer_team_id]):
            return jsonify({'error': 'Missing required fields: player_id, offered_price, buyer_team_id'}), 400

        # Validate data types
        try:
            player_id = int(player_id)
            offered_price = int(offered_price)
            buyer_team_id = int(buyer_team_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid data types'}), 400

        # Validate price is positive
        if offered_price <= 0:
            return jsonify({'error': 'Offered price must be positive'}), 400

        cur = db_helper.get_cursor()

        # Verify player ownership
        cur.execute("""
            SELECT p.*, t.club_name
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE p.id = ? AND t.id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?
            )
        """, (player_id, current_user.id))

        player = cur.fetchone()
        if not player:
            return jsonify({'error': 'Player not found or not owned by you'}), 404

        # Check if player is blacklisted
        if is_blacklisted(current_user.id, player_id):
            return jsonify({'error': 'This player is blacklisted and cannot be traded'}), 403

        # Get buyer team name
        cur.execute("SELECT club_name FROM teams WHERE id = ?", (buyer_team_id,))
        buyer_team = cur.fetchone()
        buyer_team_name = buyer_team['club_name'] if buyer_team else 'Unknown Team'

        # Transfer player
        cur.execute("UPDATE players SET club_id = ? WHERE id = ?", (buyer_team_id, player_id))

        # Update unified user budget (not individual team budget)
        add_user_movement(current_user.id, 'CPU Sale',
                         f"Sold {player['player_name']} to {buyer_team_name}",
                         offered_price)

        # Update CPU team budget (buyer pays)
        cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", (offered_price, buyer_team_id))

        # Create blog post for user sale to CPU
        cur.execute("SELECT t.club_name FROM teams t JOIN league_teams lt ON t.id = lt.id WHERE lt.user_id = ?", (current_user.id,))
        user_team = cur.fetchone()
        user_team_name = user_team['club_name'] if user_team else 'Unknown Team'

        cur.execute("SELECT club_name FROM teams WHERE id = ?", (buyer_team_id,))
        buyer_team = cur.fetchone()
        buyer_team_name = buyer_team['club_name'] if buyer_team else 'Unknown Team'

        blog_title = f"Transfer News: {buyer_team_name} Signs {player['player_name']} from {user_team_name}"
        blog_content = f"💰 <strong>{buyer_team_name}</strong> has completed the signing of <strong>{player['player_name']}</strong> from <strong>{user_team_name}</strong> for <strong>€{offered_price:,}</strong>!<br><br>The deal sees {user_team_name} receive a significant fee for their star player, while {buyer_team_name} adds quality to their squad."
        post_transfer_news(blog_title, blog_content, current_user.id)

        # Mark all offers for this player as completed
        cur.execute("""
            UPDATE market_bazaar_offers
            SET status = 'completed'
            WHERE listing_id IN (
                SELECT mbl.id FROM market_bazaar_listings mbl
                WHERE mbl.player_id = ? AND mbl.listing_type = 'cpu_user_offer'
            )
        """, (player_id,))

        # Mark the listing as completed
        cur.execute("""
            UPDATE market_bazaar_listings
            SET status = 'completed'
            WHERE player_id = ? AND listing_type = 'cpu_user_offer'
        """, (player_id,))

        # Add player to blacklist
        add_to_blacklist(current_user.id, player_id)

        db_helper.commit()

        # Prepare response data
        response_data = {
            'success': True,
            'message': f'{player["player_name"]} sold for €{offered_price:,}',
            'player_name': player['player_name'],
            'offered_price': offered_price,
            'buyer_team_name': buyer_team_name
        }

        return jsonify(response_data)

    except Exception as e:
        app.logger.error(f"Error accepting CPU offer direct: {str(e)}")
        if cur:
            try:
                db_helper.get_connection().rollback()
            except Exception as rollback_error:
                app.logger.error(f"Error during rollback: {str(rollback_error)}")
            finally:
                cur.close()

        # Return a safe error response
        return jsonify({'error': 'An error occurred while processing the offer. Please try again.'}), 500

@app.route('/market_bazaar/reject_cpu_offer_direct', methods=['POST'])
@login_required
def reject_cpu_offer_direct():
    """Reject a direct CPU offer for unlisted user player"""
    cur = None
    try:
        # Validate request data
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        player_id = data.get('player_id')

        # Validate required fields
        if not player_id:
            return jsonify({'error': 'Missing required field: player_id'}), 400

        # Validate data types
        try:
            player_id = int(player_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid player_id data type'}), 400

        cur = db_helper.get_cursor()

        # Verify player ownership
        cur.execute("""
            SELECT p.player_name FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE p.id = ? AND t.id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?
            )
        """, (player_id, current_user.id))

        player = cur.fetchone()
        if not player:
            return jsonify({'error': 'Player not found or not owned by you'}), 404

        # Mark all offers for this player as rejected
        cur.execute("""
            UPDATE market_bazaar_offers
            SET status = 'rejected'
            WHERE listing_id IN (
                SELECT mbl.id FROM market_bazaar_listings mbl
                WHERE mbl.player_id = ? AND mbl.listing_type = 'cpu_user_offer'
            )
        """, (player_id,))

        # Mark the listing as rejected
        cur.execute("""
            UPDATE market_bazaar_listings
            SET status = 'rejected'
            WHERE player_id = ? AND listing_type = 'cpu_user_offer'
        """, (player_id,))

        # Do NOT blacklist player when rejecting - just decline the offer

        db_helper.commit()

        # Prepare response data
        response_data = {
            'success': True,
            'message': f'CPU offer for {player["player_name"]} rejected',
            'player_name': player['player_name']
        }

        return jsonify(response_data)

    except Exception as e:
        app.logger.error(f"Error rejecting CPU offer direct: {str(e)}")
        if cur:
            try:
                db_helper.get_connection().rollback()
            except Exception as rollback_error:
                app.logger.error(f"Error during rollback: {str(rollback_error)}")
            finally:
                cur.close()

        # Return a safe error response
        return jsonify({'error': 'An error occurred while processing the rejection. Please try again.'}), 500

@app.route('/market_bazaar/loan_player/<int:listing_id>', methods=['POST'])
@login_required
def loan_player(listing_id):
    """Loan a player from a listing"""
    try:
        cur = db_helper.get_cursor()

        # Get listing details
        cur.execute("""
            SELECT mbl.*, p.player_name, p.club_id as current_club_id, t.club_name as seller_team_name
            FROM market_bazaar_listings mbl
            JOIN players p ON mbl.player_id = p.id
            JOIN teams t ON mbl.team_id = t.id
            WHERE mbl.id = ? AND mbl.status = 'active' AND mbl.listing_type IN ('cpu_loan', 'user_loan')
        """, (listing_id,))

        listing = cur.fetchone()
        if not listing:
            return jsonify({'error': 'Loan listing not found or no longer active'}), 404

        # Check if player is blacklisted
        if is_blacklisted(current_user.id, listing['player_id']):
            return jsonify({'error': 'This player is blacklisted and cannot be loaned'}), 403

        # Get user's team
        cur.execute("SELECT id FROM teams WHERE id IN (SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?)", (current_user.id,))
        user_team = cur.fetchone()
        if not user_team:
            return jsonify({'error': 'User team not found'}), 404

        # Allow negative budget - no budget check needed

        # Transfer player (loan)
        cur.execute("UPDATE players SET club_id = ?, loaned_by = ? WHERE id = ?",
                   (user_team['id'], listing['seller_team_name'], listing['player_id']))

        # Handle loan economics (fee or subsidy) using unified budgets for users
        fee_or_subsidy = listing['asking_price'] or 0
        # Resolve lender user mapping (if any)
        cur.execute("SELECT lt.user_id FROM league_teams lt WHERE lt.id = ?", (listing['team_id'],))
        lender_info = cur.fetchone()
        lender_user_id = lender_info['user_id'] if lender_info and lender_info['user_id'] else None

        if fee_or_subsidy < 0:
            # Subsidy: lender pays user
            subsidy_amount = abs(fee_or_subsidy)

            if lender_user_id and lender_user_id != 1:
                # Lender is a user: debit unified budget
                add_user_movement(
                    lender_user_id,
                    'Loan Salary Support',
                    f"Salary support for {listing['player_name']} on loan to {current_user.username}",
                    -subsidy_amount
                )
            else:
                # Lender is CPU: debit teams table budget
                cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", (subsidy_amount, listing['team_id']))

            # Borrower is current user: credit unified budget
            add_user_movement(
                current_user.id,
                'Loan Salary Support',
                f"Received salary support for {listing['player_name']} from {listing['seller_team_name']}",
                subsidy_amount
            )

        elif fee_or_subsidy > 0:
            # Loan fee: user pays lender
            fee = fee_or_subsidy

            # Borrower is current user: debit unified budget
            add_user_movement(
                current_user.id,
                'Loan Fee',
                f"Loan fee for {listing['player_name']} to {listing['seller_team_name']}",
                -fee
            )

            if lender_user_id and lender_user_id != 1:
                # Lender is a user: credit unified budget
                add_user_movement(
                    lender_user_id,
                    'Loan Fee Received',
                    f"Loan fee received for {listing['player_name']} from {current_user.username}",
                    fee
                )
            else:
                # Lender is CPU: credit teams table budget
                cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?", (fee, listing['team_id']))

        else:
            # Free loan: no money movements
            pass

        # Mark listing as completed
        cur.execute("UPDATE market_bazaar_listings SET status = 'completed' WHERE id = ?", (listing_id,))

        # No additional summary movement; detailed movements already added above

        # Create blog post for user loan
        cur.execute("SELECT t.club_name FROM teams t JOIN league_teams lt ON t.id = lt.id WHERE lt.user_id = ?", (current_user.id,))
        user_team = cur.fetchone()
        user_team_name = user_team['club_name'] if user_team else 'Unknown Team'

        blog_title = f"Loan News: {user_team_name} Loans {listing['player_name']}"
        blog_content = f"🔄 <strong>{user_team_name}</strong> has secured the loan of <strong>{listing['player_name']}</strong> from <strong>{listing['seller_team_name']}</strong>!<br><br>The loan deal allows {user_team_name} to strengthen their squad without a permanent transfer fee. {listing['player_name']} will return to {listing['seller_team_name']} at the end of the season."
        post_transfer_news(blog_title, blog_content, current_user.id)

        # Add player to blacklist
        add_to_blacklist(current_user.id, listing['player_id'])

        db_helper.commit()
        cur.close()

        return jsonify({'success': True, 'message': f'{listing["player_name"]} loaned successfully'})

    except Exception as e:
        app.logger.error(f"Error loaning player: {str(e)}")
        db_helper.get_connection().rollback()
        cur.close()
        return jsonify({'error': f'Error loaning player: {str(e)}'}), 500

@app.route('/market_bazaar/buy_player/<int:listing_id>', methods=['POST'])
@login_required
def buy_player_from_transfer_list(listing_id):
    """Buy a player from the transfer list"""
    try:
        cur = db_helper.get_cursor()

        # Get listing details
        cur.execute("""
            SELECT mbl.*, p.player_name, p.market_value, t.club_name as seller_team_name, mbl.team_id as seller_team_id
            FROM market_bazaar_listings mbl
            JOIN players p ON mbl.player_id = p.id
            JOIN teams t ON mbl.team_id = t.id
            WHERE mbl.id = ? AND mbl.status = 'active'
        """, (listing_id,))

        listing = cur.fetchone()
        if not listing:
            return jsonify({'error': 'Listing not found or no longer active'}), 404

        # Check if player is blacklisted
        if is_blacklisted(current_user.id, listing['player_id']):
            return jsonify({'error': 'This player is blacklisted and cannot be traded'}), 403

        # Check if user has enough budget
        cur.execute("SELECT budget FROM teams WHERE id IN (SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?)", (current_user.id,))
        user_team = cur.fetchone()
        if not user_team:
            return jsonify({'error': 'User team not found'}), 404

        # Allow negative budget - no budget check needed

        # Transfer player
        cur.execute("UPDATE players SET club_id = (SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ? LIMIT 1) WHERE id = ?",
                   (current_user.id, listing['player_id']))

        # Add player to blacklist after transfer
        add_to_blacklist(current_user.id, listing['player_id'])

        # Check if seller is a user team and update their unified budget
        cur.execute("SELECT user_id FROM league_teams WHERE id = ?", (listing['seller_team_id'],))
        seller_team = cur.fetchone()

        if seller_team and seller_team['user_id'] != 1:  # Seller is a user team (not CPU)
            # Update seller's unified budget
            add_user_movement(seller_team['user_id'], 'Transfer Sale',
                            f"Sold {listing['player_name']} to {current_user.username} for €{listing['asking_price']:,}",
                            listing['asking_price'])
        else:
            # Update CPU team budget
            cur.execute("UPDATE teams SET budget = budget + ? WHERE id = ?", (listing['asking_price'], listing['seller_team_id']))

        # User payment handled by unified budget system (already done via add_user_movement below)

        # Mark listing as completed
        cur.execute("UPDATE market_bazaar_listings SET status = 'completed' WHERE id = ?", (listing_id,))

        # Record transaction
        add_user_movement(current_user.id, 'Transfer Purchase',
                        f"Bought {listing['player_name']} from {listing['seller_team_name']} for €{listing['asking_price']:,}",
                        -listing['asking_price'])

        # Create blog post for user purchase
        cur.execute("SELECT t.club_name FROM teams t JOIN league_teams lt ON t.id = lt.id WHERE lt.user_id = ?", (current_user.id,))
        user_team = cur.fetchone()
        user_team_name = user_team['club_name'] if user_team else 'Unknown Team'

        blog_title = f"Transfer News: {user_team_name} Signs {listing['player_name']}"
        blog_content = f"🎉 <strong>{user_team_name}</strong> has completed the signing of <strong>{listing['player_name']}</strong> from <strong>{listing['seller_team_name']}</strong> for <strong>€{listing['asking_price']:,}</strong>!<br><br>The {listing['player_name']} deal represents a significant investment for {user_team_name} as they continue to strengthen their squad."
        post_transfer_news(blog_title, blog_content, current_user.id)

        db_helper.commit()
        cur.close()

        return jsonify({
            'success': True,
            'message': f'{listing["player_name"]} has been bought from {listing["seller_team_name"]} for €{listing["asking_price"]:,}'
        })

    except Exception as e:
        app.logger.error(f"Error buying player: {str(e)}")
        db_helper.get_connection().rollback()
        cur.close()
        return jsonify({'error': f'Error buying player: {str(e)}'}), 500

@app.route('/market_bazaar/accept_offer/<int:offer_id>', methods=['POST'])
@login_required
def accept_market_offer(offer_id):
    """Accept a market bazaar offer"""
    try:
        cur = db_helper.get_cursor()

        # Get offer details with additional validation
        cur.execute("""
            SELECT mbo.*, mbl.player_id, mbl.team_id, mbl.asking_price, p.player_name, mbl.status as listing_status
            FROM market_bazaar_offers mbo
            JOIN market_bazaar_listings mbl ON mbo.listing_id = mbl.id
            JOIN players p ON mbl.player_id = p.id
            WHERE mbo.id = ? AND mbo.status = 'active' AND mbl.status = 'active'
        """, (int(offer_id),))

        offer = cur.fetchone()
        if not offer:
            return jsonify({'error': 'Offer not found or no longer active'}), 404

        # Convert Row to dict for easier access
        offer = dict(offer)

        # Additional validation: check if player is still on the listing team
        cur.execute("SELECT club_id FROM players WHERE id = ?", (offer['player_id'],))
        player_team = cur.fetchone()
        if not player_team or player_team['club_id'] != offer['team_id']:
            return jsonify({'error': 'Player is no longer available'}), 404

        # Check if player is already transfer-listed (allow acceptance but expire the listing)
        cur.execute("""
            SELECT id FROM market_bazaar_listings
            WHERE player_id = ? AND status = 'active' AND id != ?
        """, (offer['player_id'], offer['listing_id']))

        existing_listing = cur.fetchone()
        if existing_listing:
            # Expire the existing listing since we're accepting an offer
            cur.execute("UPDATE market_bazaar_listings SET status = 'completed' WHERE id = ?", (existing_listing['id'],))

        # Verify the listing belongs to the user
        cur.execute("""
            SELECT t.id FROM teams t
            WHERE t.id = ? AND t.id IN (
                SELECT DISTINCT lt.id FROM league_teams lt WHERE lt.user_id = ?
            )
        """, (offer['team_id'], current_user.id))

        if not cur.fetchone():
            return jsonify({'error': 'You do not own this player listing'}), 403

        # Check if this is a Mendes offer (25% commission)
        cur.execute("""
            SELECT listing_type FROM market_bazaar_listings
            WHERE id = ?
        """, (offer['listing_id'],))

        listing_type = cur.fetchone()
        is_mendes_offer = listing_type and listing_type['listing_type'] == 'mendes_offer'

        # Calculate commission and net amount
        if is_mendes_offer:
            commission = int(offer['offered_price'] * 0.25)  # 25% commission
            net_amount = offer['offered_price'] - commission
        else:
            commission = 0
            net_amount = offer['offered_price']

        # Transfer player
        cur.execute("UPDATE players SET club_id = ? WHERE id = ?",
                   (offer['buyer_team_id'], offer['player_id']))

        # Update CPU buyer team budget (only if buyer is CPU team)
        cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?",
                   (offer['offered_price'], offer['buyer_team_id']))

        # Do NOT update seller team budget - use unified budget system instead

        # Mark offer and listing as completed
        cur.execute("UPDATE market_bazaar_offers SET status = 'completed' WHERE id = ?", (offer_id,))
        cur.execute("UPDATE market_bazaar_listings SET status = 'completed' WHERE id = ?", (offer['listing_id']))

        # Record transaction in user_movements and update unified budget
        if is_mendes_offer:
            add_user_movement(current_user.id, 'Transfer In',
                            f"Sold {offer['player_name']} for €{offer['offered_price']:,} (Net: €{net_amount:,} after €{commission:,} commission)",
                            net_amount)
        else:
            add_user_movement(current_user.id, 'Transfer In',
                            f"Sold {offer['player_name']} for €{offer['offered_price']:,}",
                            offer['offered_price'])

        # Create blog post for user sale
        cur.execute("SELECT t.club_name FROM teams t JOIN league_teams lt ON t.id = lt.id WHERE lt.user_id = ?", (current_user.id,))
        user_team = cur.fetchone()
        user_team_name = user_team['club_name'] if user_team else 'Unknown Team'

        cur.execute("SELECT club_name FROM teams WHERE id = ?", (offer['buyer_team_id'],))
        buyer_team = cur.fetchone()
        buyer_team_name = buyer_team['club_name'] if buyer_team else 'Unknown Team'

        if is_mendes_offer:
            blog_title = f"Transfer News: {user_team_name} Sells {offer['player_name']} via Jorge Mendes"
            blog_content = f"💰 <strong>{user_team_name}</strong> has sold <strong>{offer['player_name']}</strong> to <strong>{buyer_team_name}</strong> for <strong>€{offer['offered_price']:,}</strong>!<br><br>"
            blog_content += f"Jorge Mendes took a <strong>€{commission:,}</strong> commission (25%), leaving <strong>{user_team_name}</strong> with <strong>€{net_amount:,}</strong>.<br><br>"
            blog_content += f"The sale provides {user_team_name} with valuable funds to reinvest in their squad."
        else:
            blog_title = f"Transfer News: {user_team_name} Sells {offer['player_name']}"
            blog_content = f"💰 <strong>{user_team_name}</strong> has sold <strong>{offer['player_name']}</strong> to <strong>{buyer_team_name}</strong> for <strong>€{offer['offered_price']:,}</strong>!<br><br>The sale provides {user_team_name} with valuable funds to reinvest in their squad."

        post_transfer_news(blog_title, blog_content, current_user.id)

        db_helper.commit()
        cur.close()

        if is_mendes_offer:
            return jsonify({
                'success': True,
                'message': f'{offer["player_name"]} has been sold for €{offer["offered_price"]:,} (Net: €{net_amount:,} after €{commission:,} commission)'
            })
        else:
            return jsonify({
                'success': True,
                'message': f'{offer["player_name"]} has been sold for €{offer["offered_price"]:,}'
            })

    except Exception as e:
        app.logger.error(f"Error accepting market offer: {str(e)}")
        db_helper.get_connection().rollback()
        cur.close()
        return jsonify({'error': f'Error accepting offer: {str(e)}'}), 500

# =============================================================================
# CPU MARKET ACTIVITY SWITCH - Edit this line to enable/disable CPU activity
# =============================================================================
CPU_MARKET_ACTIVITY_ENABLED = False  # Set to False to disable CPU market activity

# Global variable to track last CPU AI run
last_cpu_ai_run = None

def expire_all_market_offers():
    """Expire all active market bazaar listings and offers"""
    try:
        cur = db_helper.get_cursor()

        # Expire all active listings
        cur.execute("UPDATE market_bazaar_listings SET status = 'expired' WHERE status = 'active'")
        expired_listings = cur.rowcount

        # Expire all active offers
        cur.execute("UPDATE market_bazaar_offers SET status = 'expired' WHERE status = 'active'")
        expired_offers = cur.rowcount

        db_helper.commit()
        cur.close()

        app.logger.info(f"Expired {expired_listings} listings and {expired_offers} offers")
        return {'success': True, 'expired_listings': expired_listings, 'expired_offers': expired_offers}
    except Exception as e:
        app.logger.error(f"Error expiring market offers: {e}")
        return {'success': False, 'error': str(e)}

def auto_trigger_cpu_ai():
    """Auto-trigger CPU AI every 5 minutes (if enabled)"""
    global last_cpu_ai_run
    from datetime import datetime, timedelta

    # Check if CPU market activity is enabled
    if not CPU_MARKET_ACTIVITY_ENABLED:
        return  # CPU market activity is disabled

    now = datetime.now()
    if last_cpu_ai_run is None or (now - last_cpu_ai_run).seconds > 300:  # 5 minutes
        try:
            from cpu_ai import cpu_ai
            result = cpu_ai.process_cpu_ai_actions()

            if result['success'] and result['actions_count'] > 0:
                # Create blog post
                title = f"CPU Market Activity: {result['actions_count']} Actions"
                content = f"The CPU teams have been active in the market bazaar! Here's what happened:<br><br>"

                listings = []
                offers = []

                for action in result['actions_taken']:
                    if action['action'] == 'list_player_for_sale':
                        details = action['details']
                        listings.append(f"• {action['team']} listed {details['player_name']} for €{details['asking_price']:,}")
                    elif action['action'] == 'list_player_for_loan':
                        details = action['details']
                        listings.append(f"• {action['team']} listed {details['player_name']} for loan (€{details.get('loan_fee', 0):,})")
                    elif action['action'] == 'buy_player':
                        details = action['details']
                        offers.append(f"• ✅ DEAL COMPLETED: {action['team']} bought {details['player_name']} for €{details['price_paid']:,} from {details['seller_team']}")
                    elif action['action'] == 'make_user_offer':
                        details = action['details']
                        offers.append(f"• 💰 OFFER TO USER: {action['team']} offered €{details['offered_price']:,} for {details['player_name']} from {details['current_team']}")
                    elif action['action'] == 'loan_player':
                        details = action['details']
                        offers.append(f"• 🔄 LOAN COMPLETED: {action['team']} loaned {details['player_name']} from {details['loaned_from']}")

                if listings:
                    content += "<strong>Players Listed for Sale:</strong><br><br>"
                    content += "<br>".join(listings) + "<br><br>"

                if offers:
                    content += "<strong>Transfer Offers Made:</strong><br><br>"
                    content += "<br>".join(offers) + "<br><br>"

                content += "The market bazaar is buzzing with activity!"
                post_transfer_news(title, content, 1)

            last_cpu_ai_run = now
            app.logger.info(f"Auto-triggered CPU AI: {result['actions_count']} actions")

        except Exception as e:
            app.logger.error(f"Error in auto CPU AI: {e}")

@app.route('/tools/expire_market_offers', methods=['POST'])
@login_required
def expire_market_offers_route():
    """Manually expire all market bazaar offers and listings"""
    try:
        result = expire_all_market_offers()
        if result['success']:
            flash(f'Market cleared! Expired {result["expired_listings"]} listings and {result["expired_offers"]} offers.', 'success')
        else:
            flash(f'Error clearing market: {result["error"]}', 'danger')
    except Exception as e:
        flash(f'Error clearing market: {str(e)}', 'danger')

    return redirect(url_for('tools'))

@app.route('/tools/trigger_cpu_ai', methods=['POST'])
@login_required
def trigger_cpu_ai():
    """Trigger CPU AI actions (market bazaar only)"""

    # Check if CPU market activity is enabled
    if not CPU_MARKET_ACTIVITY_ENABLED:
        flash('CPU market activity is currently disabled. Enable it in the code to use this feature.', 'warning')
        return redirect(url_for('tools'))

    try:
        from cpu_ai import cpu_ai

        # Process CPU AI actions
        result = cpu_ai.process_cpu_ai_actions()

        # Process user offers to CPU players (negotiate_with_cpu)
        user_offers_result = cpu_ai.process_user_offers()

        if result['success']:
            actions_count = result['actions_count']
            actions_taken = result['actions_taken']

            # Add user offers to the actions list
            for offer_result in user_offers_result:
                # Get the actual username for the buyer
                cur = db_helper.get_cursor()
                cur.execute("""
                    SELECT u.username
                    FROM users u
                    JOIN league_teams lt ON u.id = lt.user_id
                    WHERE lt.id = ?
                """, (offer_result['buyer_team_id'],))
                user_result = cur.fetchone()
                username = user_result['username'] if user_result else 'Unknown User'
                cur.close()

                actions_taken.append({
                    'team': f'{username} (User)',
                    'action': offer_result['action'],
                    'details': {
                        'player_name': offer_result['player_name'],
                        'cpu_team_name': offer_result['cpu_team_name'],
                        'offered_price': offer_result['offered_price']
                    }
                })
                actions_count += 1

            # Create blog post about CPU activity and user negotiations
            if actions_count > 0:
                title = f"Market Bazaar Activity: {actions_count} Actions Taken"
                content = f"The market bazaar has been buzzing with activity! Here's what happened:<br><br>"

                # Group actions by type for cleaner presentation
                listings = []
                offers = []

                for action in actions_taken:
                    if action['action'] == 'list_player_for_sale':
                        details = action['details']
                        listings.append(f"• {action['team']} listed {details['player_name']} for €{details['asking_price']:,}")
                    elif action['action'] == 'list_player_for_loan':
                        details = action['details']
                        listings.append(f"• {action['team']} listed {details['player_name']} for loan (€{details.get('loan_fee', 0):,})")
                    elif action['action'] == 'buy_player':
                        details = action['details']
                        offers.append(f"• ✅ DEAL COMPLETED: {action['team']} bought {details['player_name']} for €{details['price_paid']:,} from {details['seller_team']}")
                    elif action['action'] == 'make_user_offer':
                        details = action['details']
                        offers.append(f"• 💰 OFFER TO USER: {action['team']} offered €{details['offered_price']:,} for {details['player_name']} from {details['current_team']}")
                    elif action['action'] == 'loan_player':
                        details = action['details']
                        offers.append(f"• 🔄 LOAN COMPLETED: {action['team']} loaned {details['player_name']} from {details['loaned_from']}")
                    elif action['action'] == 'offer_accepted':
                        details = action['details']
                        offers.append(f"• ✅ NEGOTIATION SUCCESS: User successfully negotiated {details['player_name']} from {details['cpu_team_name']} for €{details['offered_price']:,}")
                    elif action['action'] == 'offer_rejected':
                        details = action['details']
                        offers.append(f"• ❌ NEGOTIATION FAILED: User's offer for {details['player_name']} from {details['cpu_team_name']} (€{details['offered_price']:,}) was rejected")

                # Add listings section
                if listings:
                    content += "<strong>Players Listed for Sale:</strong><br><br>"
                    content += "<br>".join(listings) + "<br><br>"

                # Add deals, offers and negotiations section
                if offers:
                    content += "<strong>Transfer Activity & Negotiations:</strong><br><br>"
                    content += "<br>".join(offers) + "<br><br>"

                content += "The market bazaar is buzzing with activity!"
                post_transfer_news(title, content, 1)  # CPU user ID

            flash(f'Market AI processed {actions_count} actions (including user negotiations) across {result["total_teams_processed"]} teams.', 'success')
            return redirect(url_for('tools'))
        else:
            flash(f'CPU AI error: {result.get("error", "Unknown error")}', 'error')
            return redirect(url_for('tools'))

    except Exception as e:
        flash(f'Error triggering CPU AI: {str(e)}', 'error')
        return redirect(url_for('tools'))

@app.route('/tools/recalculate_player_financials', methods=['POST'])
@login_required
def recalculate_player_financials():
    """Recalculate market values for all players using game mechanics (salaries remain unchanged)"""
    try:
        # Use the game mechanics module to update market values only
        result = game_mechanics.update_player_market_values_only('pes6_league_db.sqlite')

        if result['success']:
            flash(f"✅ Market value recalculation completed! {result['updated_count']} players updated. {result['errors']} errors occurred.", 'success')

            # Create a blog post about the market value recalculation
            blog_title = f"💰 League Market Value Recalculation Complete"

            # Build content with top players by position
            blog_content = f"""
            <p><strong>📊 League Market Value Update</strong></p>
            <p>The league has completed a comprehensive market value recalculation for all players (salaries remain unchanged).</p>
            <ul>
            <li><strong>✅ Players Updated:</strong> {result['updated_count']}</li>
            <li><strong>❌ Errors:</strong> {result['errors']}</li>
            <li><strong>🚫 Excluded:</strong> No Club players (market value set to €0)</li>
            </ul>
            """

            # Add top 5 players by position
            if 'top_players_by_position' in result and result['top_players_by_position']:
                blog_content += "<p><strong>🏆 Top 5 Most Valuable Players by Position:</strong></p>"

                for position, players in result['top_players_by_position'].items():
                    if players:  # Only show positions with players
                        blog_content += f"<h6>{position}</h6><ul>"
                        for i, player in enumerate(players, 1):
                            blog_content += f"<li>{i}. {player['name']} ({player['club_name']}): €{player['market_value']:,}</li>"
                        blog_content += "</ul>"

            blog_content += """
            <p><strong>📈 What was recalculated:</strong></p>
            <ul>
            <li>Market values based on current salaries and age multipliers</li>
            <li>Age-based market value adjustments</li>
            <li>No Club players automatically set to €0 market value</li>
            </ul>
            <p><strong>💡 Note:</strong> Player salaries remain unchanged to maintain financial stability.</p>
            """

            post_transfer_news(blog_title, blog_content, user_id=1)

        else:
            flash(f"❌ Error during market value recalculation: {result['message']}", 'danger')

    except Exception as e:
        flash(f'Error during market value recalculation: {e}', 'danger')
        print(f"❌ Error: {e}")

    return redirect(url_for('tools'))

@app.route('/tools/recalculate_free_agent_salaries', methods=['POST'])
@login_required
def recalculate_free_agent_salaries():
    """Recalculate salary demands for all free agents using game mechanics"""
    try:
        # Use the game mechanics module to update free agent salaries
        result = game_mechanics.recalculate_free_agent_salaries('pes6_league_db.sqlite')

        if result['success']:
            flash(f"✅ Free agent salary recalculation completed! {result['free_agents_updated']} free agents updated.", 'success')

            # Create a blog post about the free agent salary recalculation
            blog_title = f"💰 Free Agent Salary Demands Updated"

            blog_content = f"""
            <p><strong>📊 Free Agent Market Update</strong></p>
            <p>The league has completed a comprehensive salary demand recalculation for all free agents.</p>
            <ul>
            <li><strong>✅ Free Agents Updated:</strong> {result['free_agents_updated']}</li>
            <li><strong>🎯 New Demands:</strong> All free agents now have updated salary demands based on their current skills and age</li>
            </ul>
            <p><strong>✅ All free agent salary demands have been recalculated using the latest market standards!</strong></p>
            """

            post_transfer_news(blog_title, blog_content, user_id=1)

        else:
            flash(f"❌ Free agent salary recalculation failed: {result.get('message', 'Unknown error')}", 'error')

    except Exception as e:
        flash(f"❌ Error during free agent salary recalculation: {str(e)}", 'error')
        app.logger.error(f"Error in recalculate_free_agent_salaries: {e}")

    return redirect(url_for('tools'))

@app.route('/tools/scheduled_market_activity', methods=['POST'])
@login_required
def scheduled_market_activity():
    """Trigger scheduled market activity (CPU AI, expired offers, etc.)"""
    if not MARKET_BAZAAR_ENABLED:
        flash("❌ Market bazaar activity is currently disabled.", 'warning')
        return redirect(url_for('tools'))

    try:
        # Check if market activity is already running to prevent multiple simultaneous triggers
        cur = db_helper.get_cursor()
        cur.execute("SELECT value FROM app_settings WHERE key = 'market_activity_running'")
        running_check = cur.fetchone()

        if running_check and running_check[0] == 'true':
            flash("⚠️ Market activity is already running. Please wait for it to complete.", 'warning')
            return redirect(url_for('tools'))

        # Set lock to prevent multiple simultaneous triggers
        cur.execute("""
            INSERT OR REPLACE INTO app_settings (key, value, updated_at)
            VALUES ('market_activity_running', 'true', CURRENT_TIMESTAMP)
        """)
        db_helper.commit()

        from cpu_ai import cpu_ai

        # Trigger CPU AI activity
        cpu_result = cpu_ai.process_cpu_ai_actions()

        # Process user offers to CPU teams (negotiate_with_cpu)
        user_offers_result = cpu_ai.process_user_offers()

        # Process expired offers
        from app import check_expired_offers
        check_expired_offers()

        # Create a blog post about the market activity (using same format as manual trigger)
        actions_count = cpu_result.get('actions_count', 0)
        actions_taken = cpu_result.get('actions_taken', [])

        # Add user offers to the actions list
        for offer_result in user_offers_result:
            # Get the actual username for the buyer
            cur = db_helper.get_cursor()
            cur.execute("""
                SELECT u.username
                FROM users u
                JOIN league_teams lt ON u.id = lt.user_id
                WHERE lt.id = ?
            """, (offer_result['buyer_team_id'],))
            user_result = cur.fetchone()
            username = user_result['username'] if user_result else 'Unknown User'
            cur.close()

            actions_taken.append({
                'team': f'{username} (User)',
                'action': offer_result['action'],
                'details': {
                    'player_name': offer_result['player_name'],
                    'cpu_team_name': offer_result['cpu_team_name'],
                    'offered_price': offer_result['offered_price']
                }
            })

        if actions_count > 0:
            blog_title = f"Market Bazaar Activity: {actions_count} Actions Taken"
            blog_content = f"The market bazaar has been buzzing with activity! Here's what happened:<br><br>"

            # Group actions by type for cleaner presentation
            listings = []
            offers = []

            for action in actions_taken:
                if action['action'] == 'list_player_for_sale':
                    details = action['details']
                    listings.append(f"• {action['team']} listed {details['player_name']} for €{details['asking_price']:,}")
                elif action['action'] == 'list_player_for_loan':
                    details = action['details']
                    listings.append(f"• {action['team']} listed {details['player_name']} for loan (€{details.get('loan_fee', 0):,})")
                elif action['action'] == 'buy_player':
                    details = action['details']
                    offers.append(f"• ✅ DEAL COMPLETED: {action['team']} bought {details['player_name']} for €{details['price_paid']:,} from {details['seller_team']}")
                elif action['action'] == 'make_user_offer':
                    details = action['details']
                    offers.append(f"• 💰 OFFER TO USER: {action['team']} offered €{details['offered_price']:,} for {details['player_name']} from {details['current_team']}")
                elif action['action'] == 'loan_player':
                    details = action['details']
                    offers.append(f"• 🔄 LOAN COMPLETED: {action['team']} loaned {details['player_name']} from {details['loaned_from']}")
                elif action['action'] == 'offer_accepted':
                    details = action['details']
                    offers.append(f"• ✅ NEGOTIATION SUCCESS: User successfully negotiated {details['player_name']} from {details['cpu_team_name']} for €{details['offered_price']:,}")
                elif action['action'] == 'offer_rejected':
                    details = action['details']
                    offers.append(f"• ❌ NEGOTIATION FAILED: User's offer for {details['player_name']} from {details['cpu_team_name']} (€{details['offered_price']:,}) was rejected")

            # Add listings section
            if listings:
                blog_content += "<strong>Players Listed for Sale:</strong><br><br>"
                blog_content += "<br>".join(listings) + "<br><br>"

            # Add deals, offers and negotiations section
            if offers:
                blog_content += "<strong>Transfer Activity & Negotiations:</strong><br><br>"
                blog_content += "<br>".join(offers) + "<br><br>"

            blog_content += "The market bazaar is buzzing with activity!"
        else:
            blog_title = f"Market Bazaar Activity: No Actions Taken"
            blog_content = f"The market bazaar was quiet this time around.<br><br>"
            blog_content += f"<strong>⏰ Expired Offers:</strong> Processed and cleaned up<br><br>"
            blog_content += f"<strong>🔄 Market Updates:</strong> All pending transactions processed<br><br>"
            blog_content += "The market bazaar is ready for the next round of activity!"

        post_transfer_news(blog_title, blog_content, user_id=1)

        # Store the last market activity time and set next one
        from datetime import datetime, timedelta
        current_time = datetime.now().isoformat()
        next_activity_time = get_next_market_activity_time()

        # Update the database with the new times
        cur = db_helper.get_cursor()
        cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('last_market_activity', ?)",
                   (current_time,))
        cur.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('next_market_activity', ?)",
                   (next_activity_time,))
        db_helper.commit()
        cur.close()

        app.logger.info(f"Market activity completed at {current_time}, next activity scheduled for {next_activity_time}")

        flash(f"✅ Scheduled market activity completed! {cpu_result.get('actions_count', 0)} CPU actions taken.", 'success')

    except Exception as e:
        flash(f"❌ Error during scheduled market activity: {str(e)}", 'error')
        app.logger.error(f"Error in scheduled_market_activity: {e}")

    finally:
        # Always unlock the market activity, even if there was an error
        try:
            cur = db_helper.get_cursor()
            cur.execute("""
                INSERT OR REPLACE INTO app_settings (key, value, updated_at)
                VALUES ('market_activity_running', 'false', CURRENT_TIMESTAMP)
            """)
            db_helper.commit()
            cur.close()
        except Exception as unlock_error:
            app.logger.error(f"Error unlocking market activity: {unlock_error}")

    return redirect(url_for('tools'))

@app.route('/tools/retire_player_manual', methods=['POST'])
@login_required
def retire_player_manual():
    """Manually retire a player and generate a regen to replace them"""
    try:
        player_id = request.form.get('player_id')
        selected_nationality = request.form.get('nationality')

        if not player_id:
            flash("❌ No player selected", 'error')
            return redirect(url_for('tools'))

        cur = db_helper.get_cursor()

        # Get player details
        cur.execute("""
            SELECT p.*, t.club_name
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE p.id = ?
        """, (player_id,))

        player = cur.fetchone()
        if not player:
            flash("❌ Player not found", 'error')
            return redirect(url_for('tools'))

        player_name = player['player_name']
        team_name = player['club_name']
        team_id = player['club_id']

        # Generate regen using the same system as end-of-season
        from game_mechanics import generate_proper_regen

        # Convert player data to dictionary format for regen generation
        retired_player_data = dict(player)

        # Create regen data with optional nationality override
        regen_data = generate_proper_regen(retired_player_data, override_nationality=selected_nationality)

        # Update the player with regen data (reuse the same ID)
        cur.execute("""
            UPDATE players SET
                player_name = ?, shirt_name = ?, age = ?, nationality = ?, skin_color = ?,
                strong_foot = ?, favoured_side = ?, registered_position = ?,
                height = ?, weight = ?,
                salary = ?, contract_years_remaining = ?, yearly_wage_rise = ?,
                development_key = ?, trait_key = ?, games_played = ?, goals = ?, assists = ?,
                attack = ?, defense = ?, balance = ?, stamina = ?, top_speed = ?,
                acceleration = ?, response = ?, agility = ?, dribble_accuracy = ?,
                dribble_speed = ?, short_pass_accuracy = ?, short_pass_speed = ?,
                long_pass_accuracy = ?, long_pass_speed = ?, shot_accuracy = ?,
                shot_power = ?, shot_technique = ?, free_kick_accuracy = ?, swerve = ?,
                heading = ?, jump = ?, technique = ?, aggression = ?, mentality = ?,
                goal_keeping = ?, team_work = ?, consistency = ?, condition_fitness = ?,
                gk = ?, cwp = ?, cbt = ?, sb = ?, dmf = ?, wb = ?, cmf = ?, smf = ?,
                amf = ?, wf = ?, ss = ?, cf = ?, dribbling_skill = ?, tactical_dribble = ?,
                positioning = ?, reaction = ?, playmaking = ?, passing = ?, scoring = ?,
                one_one_scoring = ?, post_player = ?, lines = ?, middle_shooting = ?,
                side = ?, centre = ?, penalties = ?, one_touch_pass = ?, outside = ?,
                marking = ?, sliding = ?, covering = ?, d_line_control = ?,
                penalty_stopper = ?, one_on_one_stopper = ?, long_throw = ?,
                face_type = ?, preset_face_number = ?, head_width = ?, neck_length = ?,
                neck_width = ?, shoulder_height = ?, shoulder_width = ?, chest_measurement = ?,
                waist_circumference = ?, arm_circumference = ?, leg_circumference = ?,
                calf_circumference = ?, leg_length = ?, wristband = ?, wristband_color = ?,
                international_number = ?, classic_number = ?, club_number = ?,
                dribble_style = ?, free_kick_style = ?, pk_style = ?, drop_kick_style = ?, seed_player = ?
            WHERE id = ?
        """, (
            regen_data['player_name'], regen_data['shirt_name'], regen_data['age'], regen_data['nationality'], regen_data['skin_color'],
            regen_data['strong_foot'], regen_data['favoured_side'], regen_data['registered_position'],
            regen_data['height'], regen_data['weight'],
            regen_data['salary'], regen_data['contract_years_remaining'], regen_data['yearly_wage_rise'],
            regen_data['development_key'], regen_data['trait_key'], regen_data['games_played'], regen_data['goals'], regen_data['assists'],
            regen_data['attack'], regen_data['defense'], regen_data['balance'], regen_data['stamina'], regen_data['top_speed'],
            regen_data['acceleration'], regen_data['response'], regen_data['agility'], regen_data['dribble_accuracy'],
            regen_data['dribble_speed'], regen_data['short_pass_accuracy'], regen_data['short_pass_speed'],
            regen_data['long_pass_accuracy'], regen_data['long_pass_speed'], regen_data['shot_accuracy'],
            regen_data['shot_power'], regen_data['shot_technique'], regen_data['free_kick_accuracy'], regen_data['swerve'],
            regen_data['heading'], regen_data['jump'], regen_data['technique'], regen_data['aggression'], regen_data['mentality'],
            regen_data['goal_keeping'], regen_data['team_work'], regen_data['consistency'], regen_data['condition_fitness'],
            regen_data['gk'], regen_data['cwp'], regen_data['cbt'], regen_data['sb'], regen_data['dmf'], regen_data['wb'], regen_data['cmf'], regen_data['smf'],
            regen_data['amf'], regen_data['wf'], regen_data['ss'], regen_data['cf'], regen_data['dribbling_skill'], regen_data['tactical_dribble'],
            regen_data['positioning'], regen_data['reaction'], regen_data['playmaking'], regen_data['passing'], regen_data['scoring'],
            regen_data['one_one_scoring'], regen_data['post_player'], regen_data['lines'], regen_data['middle_shooting'],
            regen_data['side'], regen_data['centre'], regen_data['penalties'], regen_data['one_touch_pass'], regen_data['outside'],
            regen_data['marking'], regen_data['sliding'], regen_data['covering'], regen_data['d_line_control'],
            regen_data['penalty_stopper'], regen_data['one_on_one_stopper'], regen_data['long_throw'],
            regen_data['face_type'], regen_data['preset_face_number'], regen_data['head_width'], regen_data['neck_length'],
            regen_data['neck_width'], regen_data['shoulder_height'], regen_data['shoulder_width'], regen_data['chest_measurement'],
            regen_data['waist_circumference'], regen_data['arm_circumference'], regen_data['leg_circumference'],
            regen_data['calf_circumference'], regen_data['leg_length'], regen_data['wristband'], regen_data['wristband_color'],
            regen_data['international_number'], regen_data['classic_number'], regen_data['club_number'],
            regen_data['dribble_style'], regen_data['free_kick_style'], regen_data['pk_style'], regen_data['drop_kick_style'],
            regen_data.get('seed_player'),
            player_id
        ))

        # Calculate overall rating and bundled skills for the new regen
        from refresh_and_reimport import calculate_player_overall
        from game_mechanics import calculate_bundled_skill_ratings
        
        # Get the updated player data to calculate overall
        cur.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        updated_player = cur.fetchone()
        updated_player_dict = dict(updated_player)
        
        # Calculate overall rating
        overall = calculate_player_overall(updated_player_dict)
        
        # Calculate bundled skill ratings
        bundled_ratings = calculate_bundled_skill_ratings(updated_player_dict)
        
        # Update player with overall and bundled ratings
        cur.execute("""
            UPDATE players SET
                overall = ?,
                attack_rating = ?,
                defense_rating = ?,
                physical_rating = ?,
                power_rating = ?,
                technique_rating = ?,
                goalkeeping_rating = ?
            WHERE id = ?
        """, (
            overall,
            bundled_ratings['attack_rating'],
            bundled_ratings['defense_rating'],
            bundled_ratings['physical_rating'],
            bundled_ratings['power_rating'],
            bundled_ratings['technique_rating'],
            bundled_ratings['goalkeeping_rating'],
            player_id
        ))

        # Create blog post about the retirement
        blog_title = f"Player Retirement: {player_name} Retires from {team_name}"
        blog_content = f"""
        <p><strong>👴 Player Retirement Announcement</strong></p>
        <p><strong>{player_name}</strong> has announced their retirement from professional football while at <strong>{team_name}</strong>.</p>
        <p>The club has immediately signed a promising young replacement to fill the void left by this veteran player.</p>
        <p><strong>🔄 New Signing:</strong> A talented young player has joined {team_name} to replace the retired veteran.</p>
        <p><strong>✅ Retirement processed successfully!</strong></p>
        """

        post_transfer_news(blog_title, blog_content, user_id=1)

        db_helper.commit()
        cur.close()

        flash(f"✅ Successfully retired {player_name} and generated a new regen to replace them!", 'success')

    except Exception as e:
        flash(f"❌ Error retiring player: {str(e)}", 'error')
        app.logger.error(f"Error in retire_player_manual: {e}")
        if cur:
            db_helper.get_connection().rollback()
            cur.close()

    return redirect(url_for('tools'))

@app.route('/api/market_timer_status')
def market_timer_status():
    """Get the current market timer status"""
    try:
        # For now, we'll use a simple approach - you can enhance this with database storage
        # Calculate time since last market activity (you can store this in database)
        from datetime import datetime, timedelta

        # This is a simple implementation - you can enhance it with database storage
        # For now, we'll return a default 4-hour timer
        return jsonify({
            'success': True,
            'timer_seconds': 4 * 60 * 60,  # 4 hours
            'last_activity': None,  # You can store this in database
            'next_activity': None   # You can calculate this
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/webhook/scheduled_market_activity', methods=['POST'])
def webhook_scheduled_market_activity():
    """Web hook for scheduled market activity (PythonAnywhere compatible)"""
    if not MARKET_BAZAAR_ENABLED:
        return jsonify({
            'success': False,
            'error': 'Market bazaar activity is currently disabled'
        }), 400

    try:
        # Check if market activity is already running to prevent multiple simultaneous triggers
        cur = db_helper.get_cursor()
        cur.execute("SELECT value FROM app_settings WHERE key = 'market_activity_running'")
        running_check = cur.fetchone()

        if running_check and running_check[0] == 'true':
            return jsonify({
                'success': False,
                'error': 'Market activity is already running',
                'timestamp': datetime.now().isoformat()
            }), 409  # Conflict status code

        # Set lock to prevent multiple simultaneous triggers
        cur.execute("""
            INSERT OR REPLACE INTO app_settings (key, value, updated_at)
            VALUES ('market_activity_running', 'true', CURRENT_TIMESTAMP)
        """)
        db_helper.commit()

        from cpu_ai import cpu_ai

        # Trigger CPU AI activity
        cpu_result = cpu_ai.process_cpu_ai_actions()

        # Process expired offers
        check_expired_offers()

        # Create a blog post about the market activity (using same format as manual trigger)
        actions_count = cpu_result.get('actions_count', 0)
        actions_taken = cpu_result.get('actions_taken', [])

        # Add user offers to the actions list
        for offer_result in user_offers_result:
            # Get the actual username for the buyer
            cur = db_helper.get_cursor()
            cur.execute("""
                SELECT u.username
                FROM users u
                JOIN league_teams lt ON u.id = lt.user_id
                WHERE lt.id = ?
            """, (offer_result['buyer_team_id'],))
            user_result = cur.fetchone()
            username = user_result['username'] if user_result else 'Unknown User'
            cur.close()

            actions_taken.append({
                'team': f'{username} (User)',
                'action': offer_result['action'],
                'details': {
                    'player_name': offer_result['player_name'],
                    'cpu_team_name': offer_result['cpu_team_name'],
                    'offered_price': offer_result['offered_price']
                }
            })

        if actions_count > 0:
            blog_title = f"Market Bazaar Activity: {actions_count} Actions Taken"
            blog_content = f"The market bazaar has been buzzing with activity! Here's what happened:<br><br>"

            # Group actions by type for cleaner presentation
            listings = []
            offers = []

            for action in actions_taken:
                if action['action'] == 'list_player_for_sale':
                    details = action['details']
                    listings.append(f"• {action['team']} listed {details['player_name']} for €{details['asking_price']:,}")
                elif action['action'] == 'list_player_for_loan':
                    details = action['details']
                    listings.append(f"• {action['team']} listed {details['player_name']} for loan (€{details.get('loan_fee', 0):,})")
                elif action['action'] == 'buy_player':
                    details = action['details']
                    offers.append(f"• ✅ DEAL COMPLETED: {action['team']} bought {details['player_name']} for €{details['price_paid']:,} from {details['seller_team']}")
                elif action['action'] == 'make_user_offer':
                    details = action['details']
                    offers.append(f"• 💰 OFFER TO USER: {action['team']} offered €{details['offered_price']:,} for {details['player_name']} from {details['current_team']}")
                elif action['action'] == 'loan_player':
                    details = action['details']
                    offers.append(f"• 🔄 LOAN COMPLETED: {action['team']} loaned {details['player_name']} from {details['loaned_from']}")
                elif action['action'] == 'offer_accepted':
                    details = action['details']
                    offers.append(f"• ✅ NEGOTIATION SUCCESS: User successfully negotiated {details['player_name']} from {details['cpu_team_name']} for €{details['offered_price']:,}")
                elif action['action'] == 'offer_rejected':
                    details = action['details']
                    offers.append(f"• ❌ NEGOTIATION FAILED: User's offer for {details['player_name']} from {details['cpu_team_name']} (€{details['offered_price']:,}) was rejected")

            # Add listings section
            if listings:
                blog_content += "<strong>Players Listed for Sale:</strong><br><br>"
                blog_content += "<br>".join(listings) + "<br><br>"

            # Add deals, offers and negotiations section
            if offers:
                blog_content += "<strong>Transfer Activity & Negotiations:</strong><br><br>"
                blog_content += "<br>".join(offers) + "<br><br>"

            blog_content += "The market bazaar is buzzing with activity!"
        else:
            blog_title = f"Market Bazaar Activity: No Actions Taken"
            blog_content = f"The market bazaar was quiet this time around.<br><br>"
            blog_content += f"<strong>⏰ Expired Offers:</strong> Processed and cleaned up<br><br>"
            blog_content += f"<strong>🔄 Market Updates:</strong> All pending transactions processed<br><br>"
            blog_content += "The market bazaar is ready for the next round of activity!"

        post_transfer_news(blog_title, blog_content, user_id=1)

        from datetime import datetime
        return jsonify({
            'success': True,
            'message': 'Scheduled market activity completed successfully',
            'actions_taken': cpu_result.get('actions_count', 0),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        app.logger.error(f"Error in webhook_scheduled_market_activity: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

    finally:
        # Always unlock the market activity, even if there was an error
        try:
            cur = db_helper.get_cursor()
            cur.execute("""
                INSERT OR REPLACE INTO app_settings (key, value, updated_at)
                VALUES ('market_activity_running', 'false', CURRENT_TIMESTAMP)
            """)
            db_helper.commit()
            cur.close()
        except Exception as unlock_error:
            app.logger.error(f"Error unlocking market activity: {unlock_error}")

def get_current_season():
    """Get the current season name"""
    cur = db_helper.get_cursor()
    try:
        cur.execute("SELECT season_name FROM league_seasons WHERE is_current = 1")
        result = cur.fetchone()
        if result:
            return result['season_name']
        else:
            # Fallback to 00/01 if no current season found
            return '00/01'
    except Exception as e:
        print(f"Error getting current season: {e}")
        return '00/01'
    finally:
        cur.close()

def increment_season():
    """Increment to the next season and return the new season name"""
    cur = db_helper.get_cursor()
    try:
        # Get current season
        cur.execute("SELECT season_name FROM league_seasons WHERE is_current = 1")
        current_result = cur.fetchone()

        if not current_result:
            # No current season, start with 00/01
            new_season = '00/01'
        else:
            current_season = current_result['season_name']
            # Parse season (e.g., "00/01" -> 0, 1)
            parts = current_season.split('/')
            if len(parts) == 2:
                year1, year2 = int(parts[0]), int(parts[1])
                # Increment: 00/01 -> 01/02, 01/02 -> 02/03, etc.
                new_year1 = f"{(year1 + 1):02d}"
                new_year2 = f"{(year2 + 1):02d}"
                new_season = f"{new_year1}/{new_year2}"
            else:
                # Fallback if format is wrong
                new_season = '00/01'

        # Mark current season as not current
        cur.execute("UPDATE league_seasons SET is_current = 0 WHERE is_current = 1")

        # Insert new season as current
        cur.execute("""
            INSERT OR REPLACE INTO league_seasons (season_name, is_current)
            VALUES (?, 1)
        """, (new_season,))

        db_helper.commit()
        return new_season

    except Exception as e:
        print(f"Error incrementing season: {e}")
        db_helper.get_connection().rollback()
        return '00/01'
    finally:
        cur.close()

def create_user_season_blog_posts():
    """Create user-specific end-of-season blog posts with development and retirement summaries."""
    cur = db_helper.get_cursor()

    try:
        # Get all human users (excluding CPU)
        cur.execute("SELECT id, username FROM users WHERE id != 1")
        users = cur.fetchall()

        for user in users:
            user_id = user['id']
            username = user['username']

            print(f"📝 Creating season summary for {username}...")

            # Get user's teams
            cur.execute("""
                SELECT DISTINCT lt.team_name, t.id as team_id
                FROM league_teams lt
                JOIN teams t ON lt.team_name = t.club_name
                WHERE lt.user_id = ?
            """, (user_id,))
            teams = cur.fetchall()

            if not teams:
                continue

            team_ids = [team[1] for team in teams]
            team_names = [team[0] for team in teams]

            # Get team statistics
            team_stats = {}
            total_players = 0
            total_salaries = 0
            total_market_value = 0

            for team_id, team_name in zip(team_ids, team_names):
                cur.execute("""
                    SELECT
                        COUNT(*) as player_count,
                        AVG(age) as avg_age,
                        SUM(salary) as total_salaries,
                        SUM(market_value) as total_market_value
                    FROM players
                    WHERE club_id = ?
                """, (team_id,))

                stats = cur.fetchone()
                team_stats[team_name] = {
                    'player_count': stats[0],
                    'avg_age': round(stats[1], 1) if stats[1] else 0,
                    'total_salaries': stats[2] or 0,
                    'total_market_value': stats[3] or 0
                }

                total_players += stats[0]
                total_salaries += stats[2] or 0
                total_market_value += stats[3] or 0

            # Get top 3 players by market value
            cur.execute("""
                SELECT p.player_name, p.market_value, t.club_name, p.age, p.salary
                FROM players p
                JOIN teams t ON p.club_id = t.id
                WHERE p.club_id IN ({})
                ORDER BY p.market_value DESC
                LIMIT 3
            """.format(','.join('?' * len(team_ids))), team_ids)
            top_players = cur.fetchall()

            # Get youngest and oldest players
            cur.execute("""
                SELECT p.player_name, p.age, t.club_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                WHERE p.club_id IN ({})
                ORDER BY p.age ASC
                LIMIT 1
            """.format(','.join('?' * len(team_ids))), team_ids)
            youngest = cur.fetchone()

            cur.execute("""
                SELECT p.player_name, p.age, t.club_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                WHERE p.club_id IN ({})
                ORDER BY p.age DESC
                LIMIT 1
            """.format(','.join('?' * len(team_ids))), team_ids)
            oldest = cur.fetchone()

            # Create blog post
            title = f"📊 {username}'s End of Season Report"

            # Build team overview HTML
            team_overview_html = ""
            for team_name, stats in team_stats.items():
                team_overview_html += f"""
                <div class="team-stats" style="margin: 10px 0; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                    <h5 style="margin: 0 0 5px 0; color: #333;">{team_name}</h5>
                    <ul style="margin: 5px 0; padding-left: 20px;">
                        <li><strong>Players:</strong> {stats['player_count']}</li>
                        <li><strong>Average Age:</strong> {stats['avg_age']}</li>
                        <li><strong>Total Salaries:</strong> €{stats['total_salaries']:,}</li>
                        <li><strong>Total Market Value:</strong> €{stats['total_market_value']:,}</li>
                    </ul>
                </div>
                """

            # Build top players HTML
            top_players_html = ""
            if top_players:
                top_players_html = "<h4>⭐ Top 3 Most Valuable Players</h4><ul>"
                for player in top_players:
                    top_players_html += f"<li><strong>{player[0]}</strong> ({player[2]}): €{player[1]:,} - Age {player[3]}, Salary €{player[4]:,}</li>"
                top_players_html += "</ul>"

            # Build age extremes HTML
            age_extremes_html = ""
            if youngest and oldest:
                age_extremes_html = f"""
                <h4>👶👴 Age Extremes</h4>
                <ul>
                    <li><strong>Youngest:</strong> {youngest[0]} ({youngest[2]}) - Age {youngest[1]}</li>
                    <li><strong>Oldest:</strong> {oldest[0]} ({oldest[2]}) - Age {oldest[1]}</li>
                </ul>
                """

            content = f"""
            <div class="season-summary" style="font-family: Arial, sans-serif;">
                <h3 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">🏆 {username}'s End of Season Summary</h3>

                <div class="overview" style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <h4 style="color: #34495e; margin-top: 0;">📈 Overall Statistics</h4>
                    <ul>
                        <li><strong>Total Players:</strong> {total_players}</li>
                        <li><strong>Total Salaries:</strong> €{total_salaries:,}</li>
                        <li><strong>Total Market Value:</strong> €{total_market_value:,}</li>
                        <li><strong>Managed Teams:</strong> {', '.join(team_names)}</li>
                    </ul>
                </div>

                <div class="team-overview" style="margin: 15px 0;">
                    <h4 style="color: #34495e;">🏟️ Team Breakdown</h4>
                    {team_overview_html}
                </div>

                <div class="player-highlights" style="margin: 15px 0;">
                    {top_players_html}
                    {age_extremes_html}
                </div>

                <div class="season-conclusion" style="background: #e8f5e8; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <h4 style="color: #27ae60; margin-top: 0;">🎯 Season Conclusion</h4>
                    <p>Another successful season completed! Your teams are well-positioned for the challenges ahead.
                    With a combined market value of <strong>€{total_market_value:,}</strong> and a talented squad of <strong>{total_players} players</strong>,
                    the future looks bright for {username}'s football empire.</p>
                </div>
            </div>
            """

            # Post the blog entry
            post_transfer_news(title, content, user_id=1)
            print(f"✅ Season summary blog post created for {username}")

    except Exception as e:
        print(f"❌ Error creating user season blog posts: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()

def calculate_player_career_stats(cur, player_id):
    """Calculate career statistics for a player by summing historical data + current stats"""
    try:
        # Get current season stats
        cur.execute("""
            SELECT games_played, goals, assists, salary, championships_won, cups_won
            FROM players
            WHERE id = ?
        """, (player_id,))

        current_stats = cur.fetchone()
        if not current_stats:
            return {
                'career_earnings': 0,
                'total_games': 0,
                'total_goals': 0,
                'total_assists': 0,
                'seasons_played': 0,
                'championships_won': 0,
                'cups_won': 0
            }

        current_games, current_goals, current_assists, current_salary, championships_won, cups_won = current_stats

        # Get historical stats from player_season_history
        cur.execute("""
            SELECT SUM(games_played), SUM(goals), SUM(assists), SUM(salary), COUNT(DISTINCT season)
            FROM player_season_history
            WHERE player_id = ?
        """, (player_id,))

        historical_stats = cur.fetchone()
        historical_games, historical_goals, historical_assists, historical_salary, historical_seasons = historical_stats

        # Sum current + historical stats
        total_games = (current_games or 0) + (historical_games or 0)
        total_goals = (current_goals or 0) + (historical_goals or 0)
        total_assists = (current_assists or 0) + (historical_assists or 0)
        total_salary = (current_salary or 0) + (historical_salary or 0)
        total_seasons = (historical_seasons or 0) + 1  # +1 for current season

        # Calculate career earnings (total salary * 2 as per user's request)
        career_earnings = total_salary * 2

        return {
            'career_earnings': career_earnings,
            'total_games': total_games,
            'total_goals': total_goals,
            'total_assists': total_assists,
            'seasons_played': total_seasons,
            'championships_won': championships_won or 0,
            'cups_won': cups_won or 0
        }

    except Exception as e:
        app.logger.error(f"Error calculating career stats for player {player_id}: {e}")
        return {
            'career_earnings': 0,
            'total_games': 0,
            'total_goals': 0,
            'total_assists': 0,
            'seasons_played': 0,
            'championships_won': 0,
            'cups_won': 0
        }

@app.route('/tools/end_of_season_process', methods=['POST'])
@login_required
def end_of_season_process():
    """Process end of season changes: salaries, ages, contracts, and salary increases"""
    cur = db_helper.get_cursor()

    try:
        # Initialize all counters
        payments_processed = 0
        cpu_teams_processed = 0
        age_updated = 0
        contract_updated = 0
        salary_doubled = 0
        wage_rise_applied = 0
        players_developed = 0
        total_skill_changes = 0
        retired_count = 0
        new_players_generated = 0
        history_records_created = 0

        # Step 1: Process salary bills (trigger the existing route logic)
        print("🔄 Step 1: Processing salary bills...")

        # Process human users (except CPU)
        cur.execute("SELECT id, username FROM users WHERE id != 1")
        users = cur.fetchall()

        for user in users:
            # Calculate the user's total salary bill
            cur.execute("""
                SELECT SUM(p.salary) as total_salary
                FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.club_name = lt.team_name
                WHERE lt.user_id = ?
            """, (user['id'],))
            result = cur.fetchone()
            total_salary = result['total_salary'] if result and result['total_salary'] else 0

            if total_salary > 0:
                # Get top 3 highest paid players for the blog post
                cur.execute("""
                    SELECT p.player_name, p.salary, lt.team_name
                    FROM players p
                    JOIN teams t ON p.club_id = t.id
                    JOIN league_teams lt ON t.club_name = lt.team_name
                    WHERE lt.user_id = ?
                    ORDER BY p.salary DESC
                    LIMIT 3
                """, (user['id'],))
                top_players = cur.fetchall()

                # Get total number of players
                cur.execute("""
                    SELECT COUNT(*) as player_count
                    FROM players p
                    JOIN teams t ON p.club_id = t.id
                    JOIN league_teams lt ON t.club_name = lt.team_name
                    WHERE lt.user_id = ?
                """, (user['id'],))
                player_count = cur.fetchone()['player_count']

                # Update user's unified budget (negative amount = user pays)
                add_user_movement(user['id'], 'End of Season Salary Bill',
                                 f'End of season salary bill for all your players: €{total_salary:,}',
                                 -total_salary)

                # Create enhanced blog post about the club's finances being in order
                blog_title = f"💰 {user['username']}'s End of Season Finances Settled"
                print(f"📝 Creating blog post for {user['username']}: {blog_title}")

                top_players_html = ""
                if top_players:
                    top_players_html = "<p><strong>Top 3 Player Wages:</strong></p><ul>"
                    for player in top_players:
                        top_players_html += f"<li>{player['player_name']} ({player['team_name']}): €{player['salary']:,}</li>"
                    top_players_html += "</ul>"

                blog_content = f"""
                <p><strong>🏦 End of Season Bank Payments</strong></p>
                <p><strong>{user['username']}</strong> has successfully processed their club's end of season salary bill of <strong>€{total_salary:,}</strong>.</p>
                <p>The payment covers <strong>{player_count} players</strong> across all managed teams.</p>
                {top_players_html}
                <p><strong>✅ Financial Status:</strong> All player wages have been settled and the club's finances are now in order for the new season.</p>
                <p>This ensures continued team stability and player satisfaction in the league.</p>
                """
                post_transfer_news(blog_title, blog_content, user_id=1)
                print(f"✅ Blog post created for {user['username']}")

                payments_processed += 1
                print(f"  - {user['username']}: End of season salary bill paid (€{total_salary:,} for {player_count} players)")

        # Process CPU teams (update their financial data without blog posts)
        cpu_teams_processed = 0
        cur.execute("""
            SELECT t.id, t.club_name, COALESCE(SUM(p.salary), 0) as total_salaries, t.budget
            FROM teams t
            LEFT JOIN players p ON t.id = p.club_id
            JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE lt.user_id = 1
            GROUP BY t.id, t.club_name, t.budget
        """)
        cpu_teams = cur.fetchall()

        for team in cpu_teams:
            team_id = team['id']
            club_name = team['club_name']
            total_salaries = team['total_salaries']
            current_budget = team['budget'] or 400000000  # Default if budget is NULL

            if total_salaries > 0:
                # Reduce budget by the salary bill amount
                new_budget = current_budget - total_salaries

                # Calculate available cap with new budget
                available_cap = new_budget - total_salaries

                # Update CPU team financial data
                cur.execute("""
                    UPDATE teams
                    SET total_salaries = ?, budget = ?, available_cap = ?
                    WHERE id = ?
                """, (total_salaries, new_budget, available_cap, team_id))

                cpu_teams_processed += 1
                print(f"  - CPU {club_name}: Budget reduced by €{total_salaries:,} (€{current_budget:,} → €{new_budget:,}), available cap: €{available_cap:,}")

        # Step 2: Add 1 year to every player's age (exclude draftees)
        print("🔄 Step 2: Updating player ages...")
        cur.execute("UPDATE players SET age = age + 1 WHERE (draftee = 0 OR draftee IS NULL)")
        age_updated = cur.rowcount
        print(f"  ✅ {age_updated} players had their age increased by 1 year (draftees excluded)")

        # Step 3: Reduce 1 year to every player's contract (except "No Club" and draftees)
        print("🔄 Step 3: Updating player contracts...")
        cur.execute("UPDATE players SET contract_years_remaining = contract_years_remaining - 1 WHERE club_id != 141 AND (draftee = 0 OR draftee IS NULL)")
        contract_updated = cur.rowcount
        print(f"  ✅ {contract_updated} players had their contract reduced by 1 year (excluding No Club and draftees)")

        # Step 4: Multiply each player's salary by 2 and add to career earnings (exclude draftees)
        print("🔄 Step 4: Doubling player salaries and updating career earnings...")
        cur.execute("UPDATE players SET salary = salary, career_earnings = career_earnings + (salary * 2) WHERE club_id != 141 AND (draftee = 0 OR draftee IS NULL)")
        salary_doubled = cur.rowcount
        print(f"  ✅ {salary_doubled} players had their salary doubled and career earnings updated (excluding No Club and draftees)")

        # Step 5: Apply yearly wage rise to each player's salary (exclude draftees)
        print("🔄 Step 5: Applying yearly wage rises...")
        cur.execute("""
            UPDATE players
            SET salary = salary * (1 + COALESCE(yearly_wage_rise, 0) + 0.01)
            WHERE yearly_wage_rise IS NOT NULL AND (draftee = 0 OR draftee IS NULL)
        """)
        wage_rise_applied = cur.rowcount
        print(f"  ✅ {wage_rise_applied} players had their yearly wage rise applied (draftees excluded)")

        # Step 6: Process player skill development (exclude draftees)
        print("🔄 Step 6: Processing player skill development...")
        from game_mechanics import calculate_player_skill_development

        # Get all players with their development keys (exclude draftees)
        cur.execute("""
            SELECT id, player_name, age, registered_position, development_key, trait_key,
                   attack, defense, balance, stamina, top_speed, acceleration,
                   response, agility, dribble_accuracy, dribble_speed,
                   short_pass_accuracy, short_pass_speed, long_pass_accuracy, long_pass_speed,
                   shot_accuracy, shot_power, shot_technique, free_kick_accuracy, swerve,
                   heading, jump, technique, aggression, mentality, goal_keeping,
                   team_work, consistency, condition_fitness, games_played, goals, assists, seed_player
            FROM players
            WHERE development_key > 0 AND trait_key IS NOT NULL 
            AND (draftee = 0 OR draftee IS NULL)
        """)

        players_for_development = cur.fetchall()
        players_developed = 0
        total_skill_changes = 0

        for player in players_for_development:
            # Convert player data to dictionary format
            player_data = dict(player)

            # Calculate development
            development_result = calculate_player_skill_development(
                player_data,
                player_data['development_key'],
                player_data['trait_key']
            )

            # Apply skill changes to database
            skill_changes = development_result['skill_changes']
            for skill_name, change_info in skill_changes.items():
                if change_info['change'] != 0:  # Only update if there's a change
                    new_value = change_info['new']
                    cur.execute(f"UPDATE players SET {skill_name} = ? WHERE id = ?",
                              (new_value, player_data['id']))

            players_developed += 1
            total_skill_changes += development_result['total_skill_change']

            # Progress indicator
            if players_developed % 500 == 0:
                print(f"    📈 Processed {players_developed} players...")

        print(f"  ✅ {players_developed} players had their skills developed (total change: {total_skill_changes:+d} points)")

        # Step 7: Record player historical data for the current season (BEFORE retirements)
        print("🔄 Step 7: Recording player historical data...")
        current_season = get_current_season()

        # Get all players with their current season stats
        cur.execute("""
            SELECT p.id, p.player_name, p.club_id, t.club_name, p.games_played, p.goals, p.assists, p.salary
            FROM players p
            LEFT JOIN teams t ON p.club_id = t.id
            WHERE p.club_id IS NOT NULL AND p.club_id != 141
        """)

        players_for_history = cur.fetchall()
        history_records_created = 0

        for player in players_for_history:
            try:
                cur.execute("""
                    INSERT OR REPLACE INTO player_season_history
                    (player_id, season, club_id, club_name, games_played, goals, assists, salary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (player['id'], current_season, player['club_id'], player['club_name'],
                      player['games_played'], player['goals'], player['assists'], player['salary']))
                history_records_created += 1
            except Exception as e:
                print(f"  ❌ Error recording history for player {player['player_name']}: {e}")

        print(f"  ✅ Created {history_records_created} player historical records for season {current_season}")

        # Step 7.5: Reset player statistics for new season
        print("🔄 Step 7.5: Resetting player statistics for new season...")
        cur.execute("UPDATE players SET games_played = 0, goals = 0, assists = 0 WHERE club_id IS NOT NULL AND club_id != 141")
        stats_reset_count = cur.rowcount
        print(f"  ✅ Reset statistics for {stats_reset_count} players (games_played, goals, assists = 0)")

        # Step 7.6: Return loaned players to their original clubs
        print("🔄 Step 7.6: Returning loaned players to their original clubs...")
        cur.execute("""
            SELECT p.id, p.player_name, p.loaned_by, p.club_id, t.club_name as current_club
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE p.loaned_by IS NOT NULL AND p.loaned_by != ''
        """)
        loaned_players = cur.fetchall()

        returned_count = 0
        for player in loaned_players:
            # Find the original club by name
            cur.execute("SELECT id FROM teams WHERE club_name = ?", (player['loaned_by'],))
            original_club = cur.fetchone()

            if original_club:
                # Return player to original club and clear loaned_by
                cur.execute("""
                    UPDATE players
                    SET club_id = ?, loaned_by = NULL
                    WHERE id = ?
                """, (original_club['id'], player['id']))
                returned_count += 1
                print(f"  📤 Returned {player['player_name']} from {player['current_club']} to {player['loaned_by']}")
            else:
                print(f"  ⚠️ Could not find original club '{player['loaned_by']}' for {player['player_name']}")

        print(f"  ✅ Returned {returned_count} loaned players to their original clubs")

        # Step 8: Create user-specific end-of-season blog posts
        print("🔄 Step 8: Creating user-specific end-of-season summaries...")
        create_user_season_blog_posts()

        # Step 9: Process player retirements and replace with regens (NO NEW IDs)
        print("🔄 Step 9: Processing player retirements and replacements...")
        from game_mechanics import check_player_retirement, generate_proper_regen

        # Get all players aged 30+ for retirement checking (exclude draftees)
        cur.execute("""
            SELECT id, player_name, age, registered_position, salary, club_id, nationality,
                   contract_years_remaining, games_played, market_value
            FROM players
            WHERE age >= 30 AND (draftee = 0 OR draftee IS NULL)
            ORDER BY age DESC
        """)

        players_to_check = cur.fetchall()
        retired_players = []
        replacement_players = []
        teams_updated = set()

        print(f"  📊 Checking {len(players_to_check)} players (aged 30+) for retirement (draftees excluded)...")

        # Check each player for retirement
        for player in players_to_check:
            player_data = {
                'id': player['id'],
                'player_name': player['player_name'],
                'age': player['age'],
                'registered_position': player['registered_position'],
                'salary': player['salary'],
                'club_id': player['club_id'],
                'nationality': player['nationality'],
                'contract_years_remaining': player['contract_years_remaining'],
                'games_played': player['games_played'],
                'market_value': player['market_value']
            }

            # Check if player should retire
            retirement_result = check_player_retirement(player_data)

            if retirement_result['wants_to_retire']:
                retired_players.append(player_data)
                print(f"    👴 {player['player_name']} ({player['age']}yo, {player['registered_position']}) - {retirement_result['reason']}")

                # Get team name for reporting
                cur.execute("SELECT club_name FROM teams WHERE id = ?", (player['club_id'],))
                team_result = cur.fetchone()
                team_name = team_result['club_name'] if team_result else "Unknown Team"
                teams_updated.add(team_name)

        retired_count = len(retired_players)
        print(f"  ✅ {retired_count} players will retire")

        # Generate replacement data for each retired player
        for retired_player in retired_players:
            # Fetch complete player data for regen generation
            cur.execute("""
                SELECT * FROM players WHERE id = ?
            """, (retired_player['id'],))
            complete_player_data = cur.fetchone()

            if not complete_player_data:
                print(f"    ❌ Could not find complete data for retired player {retired_player['player_name']} (ID: {retired_player['id']})")
                continue

            # Convert to dictionary for generate_proper_regen
            column_names = [description[0] for description in cur.description]
            retired_player_dict = dict(zip(column_names, complete_player_data))

            # Generate a proper regen based on the retiring player
            new_player = generate_proper_regen(
                retired_player_data=retired_player_dict,
                db_path='pes6_league_db.sqlite'
            )

            # Store the replacement data
            replacement_players.append({
                'new_player': new_player,
                'retired_player': retired_player
            })

            print(f"    🔄 Prepared replacement: {retired_player['player_name']} ({retired_player['age']}yo, {retired_player['registered_position']}) → {new_player['player_name']} ({new_player['age']}yo, {new_player['nationality']})")

        teams_updated = list(teams_updated)
        print(f"  ✅ {retired_count} players retiring, {len(replacement_players)} replacements prepared for {len(teams_updated)} teams")

        # Create a summary blog post
        summary_title = f"🏆 End of Season Processing Complete"
        summary_content = f"""
        <p><strong>📊 End of Season League Update</strong></p>
        <p>The league has successfully completed end of season processing:</p>
        <ul>
        <li><strong>💰 Salary Bills:</strong> Processed for {payments_processed} human clubs and {cpu_teams_processed} CPU clubs</li>
        <li><strong>👴 Player Ages:</strong> All {age_updated} players aged by 1 year</li>
        <li><strong>📜 Contracts:</strong> {contract_updated} players had contracts reduced by 1 year</li>
        <li><strong>💵 Salaries:</strong> All {salary_doubled} players had salaries doubled</li>
        <li><strong>📈 Wage Rises:</strong> {wage_rise_applied} players had yearly wage rises applied</li>
        <li><strong>🎯 Skill Development:</strong> {players_developed} players had their skills developed (total change: {total_skill_changes:+d} points)</li>
        <li><strong>👋 Player Retirements:</strong> {retired_count} players retired from the league</li>
        <li><strong>🌟 New Talent:</strong> {new_players_generated} new young players (16-18 years old) joined to replace retirees</li>
        </ul>
        <p><strong>✅ The new season is ready to begin!</strong></p>
        <p>All clubs have settled their financial obligations, player contracts have been updated, skills have evolved, veterans have retired, and fresh talent has entered the league for the upcoming season.</p>
        """
        post_transfer_news(summary_title, summary_content, user_id=1)
        print(f"📊 Summary blog post created for end of season processing")

        db_helper.commit()

        # Now replace the retiring players with regens (after main transaction is committed)
        print(f"🔍 DEBUG: Checking replacement_players - exists: {'replacement_players' in locals()}, length: {len(locals().get('replacement_players', []))}")
        if 'replacement_players' in locals() and replacement_players:
            print(f"🔄 Recording {len(replacement_players)} retiring players in Hall of Fame and replacing with regens...")

            # First, record all retiring players in Hall of Fame before they're overwritten

            # Get current season for retirement records
            try:
                cur.execute("SELECT season_name FROM league_seasons WHERE is_current = 1")
                current_season_result = cur.fetchone()
                current_season = current_season_result[0] if current_season_result else "Unknown Season"
            except:
                current_season = "Unknown Season"

            hall_of_fame_recorded = 0
            for replacement in replacement_players:
                try:
                    retired_player = replacement['retired_player']
                    retired_id = retired_player['id']

                    # Get full player data before it's overwritten
                    cur.execute("""
                        SELECT p.id, p.player_name, p.age, p.nationality, p.registered_position,
                               p.salary, p.market_value, p.games_played, p.goals, p.assists,
                               p.championships_won, p.cups_won, t.club_name
                        FROM players p
                        LEFT JOIN teams t ON p.club_id = t.id
                        WHERE p.id = ?
                    """, (retired_id,))

                    full_player_data = cur.fetchone()
                    if full_player_data:
                        # Calculate career stats
                        career_stats = calculate_player_career_stats(cur, retired_id)

                        # Get team name (last column)
                        team_name = full_player_data[12] if full_player_data[12] else "No Club"

                        # Insert into retired_players table with retirement season
                        cur.execute("""
                            INSERT INTO retired_players (
                                player_id, player_name, team_name, age_at_retirement,
                                nationality, registered_position, career_earnings,
                                total_games_played, total_goals, total_assists,
                                final_salary, final_market_value, retirement_reason,
                                seasons_played, retirement_season, championships_won, cups_won
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            retired_id,
                            retired_player['player_name'],
                            team_name,
                            retired_player['age'],
                            full_player_data[3],  # nationality
                            full_player_data[4],  # registered_position
                            career_stats['career_earnings'],
                            career_stats['total_games'],
                            career_stats['total_goals'],
                            career_stats['total_assists'],
                            full_player_data[5] or 0,  # salary
                            full_player_data[6] or 0,  # market_value
                            retired_player.get('reason', f'Retired at age {retired_player["age"]}'),
                            career_stats['seasons_played'],
                            current_season,
                            full_player_data[10] or 0,  # championships_won
                            full_player_data[11] or 0   # cups_won
                        ))

                        hall_of_fame_recorded += 1
                        print(f"    🏆 SUCCESS: Recorded {retired_player['player_name']} in Hall of Fame (Season {current_season})")

                except Exception as e:
                    print(f"    ❌ Failed to record {retired_player.get('player_name', 'unknown')} in Hall of Fame: {e}")

            print(f"  🏆 {hall_of_fame_recorded} players recorded in Hall of Fame")

            # Now replace the players with regens
            for replacement in replacement_players:
                try:
                    retired_id = replacement['retired_player']['id']
                    new_player_data = replacement['new_player']

                    # Update the retiring player with regen data (keeping the same ID)
                    cur.execute("""
                        UPDATE players SET
                            player_name = ?, shirt_name = ?, age = ?, nationality = ?, skin_color = ?,
                            strong_foot = ?, favoured_side = ?, registered_position = ?,
                            height = ?, weight = ?,
                            salary = ?, contract_years_remaining = ?, yearly_wage_rise = ?,
                            development_key = ?, trait_key = ?, games_played = ?, goals = ?, assists = ?,
                            attack = ?, defense = ?, balance = ?, stamina = ?, top_speed = ?,
                            acceleration = ?, response = ?, agility = ?, dribble_accuracy = ?,
                            dribble_speed = ?, short_pass_accuracy = ?, short_pass_speed = ?,
                            long_pass_accuracy = ?, long_pass_speed = ?, shot_accuracy = ?,
                            shot_power = ?, shot_technique = ?, free_kick_accuracy = ?, swerve = ?,
                            heading = ?, jump = ?, technique = ?, aggression = ?, mentality = ?,
                            goal_keeping = ?, team_work = ?, consistency = ?, condition_fitness = ?,
                            gk = ?, cwp = ?, cbt = ?, sb = ?, dmf = ?, wb = ?, cmf = ?, smf = ?,
                            amf = ?, wf = ?, ss = ?, cf = ?, dribbling_skill = ?, tactical_dribble = ?,
                            positioning = ?, reaction = ?, playmaking = ?, passing = ?, scoring = ?,
                            one_one_scoring = ?, post_player = ?, lines = ?, middle_shooting = ?,
                            side = ?, centre = ?, penalties = ?, one_touch_pass = ?, outside = ?,
                            marking = ?, sliding = ?, covering = ?, d_line_control = ?,
                            penalty_stopper = ?, one_on_one_stopper = ?, long_throw = ?,
                            face_type = ?, preset_face_number = ?, head_width = ?, neck_length = ?,
                            neck_width = ?, shoulder_height = ?, shoulder_width = ?, chest_measurement = ?,
                            waist_circumference = ?, arm_circumference = ?, leg_circumference = ?,
                            calf_circumference = ?, leg_length = ?, wristband = ?, wristband_color = ?,
                            international_number = ?, classic_number = ?, club_number = ?,
                            dribble_style = ?, free_kick_style = ?, pk_style = ?, drop_kick_style = ?, seed_player = ?
                        WHERE id = ?
                    """, (
                        new_player_data['player_name'], new_player_data['shirt_name'], new_player_data['age'], new_player_data['nationality'],
                        new_player_data['skin_color'], new_player_data['strong_foot'], new_player_data['favoured_side'],
                        new_player_data['registered_position'], new_player_data['height'], new_player_data['weight'],
                        new_player_data['salary'], new_player_data['contract_years_remaining'], new_player_data['yearly_wage_rise'],
                        new_player_data['development_key'], new_player_data['trait_key'],
                        new_player_data['games_played'], new_player_data['goals'], new_player_data['assists'],
                        new_player_data['attack'], new_player_data['defense'], new_player_data['balance'],
                        new_player_data['stamina'], new_player_data['top_speed'], new_player_data['acceleration'],
                        new_player_data['response'], new_player_data['agility'], new_player_data['dribble_accuracy'],
                        new_player_data['dribble_speed'], new_player_data['short_pass_accuracy'],
                        new_player_data['short_pass_speed'], new_player_data['long_pass_accuracy'],
                        new_player_data['long_pass_speed'], new_player_data['shot_accuracy'],
                        new_player_data['shot_power'], new_player_data['shot_technique'],
                        new_player_data['free_kick_accuracy'], new_player_data['swerve'],
                        new_player_data['heading'], new_player_data['jump'], new_player_data['technique'],
                        new_player_data['aggression'], new_player_data['mentality'],
                        new_player_data['goal_keeping'], new_player_data['team_work'],
                        new_player_data['consistency'], new_player_data['condition_fitness'],
                        new_player_data['gk'], new_player_data['cwp'], new_player_data['cbt'],
                        new_player_data['sb'], new_player_data['dmf'], new_player_data['wb'],
                        new_player_data['cmf'], new_player_data['smf'], new_player_data['amf'],
                        new_player_data['wf'], new_player_data['ss'], new_player_data['cf'],
                        new_player_data['dribbling_skill'], new_player_data['tactical_dribble'],
                        new_player_data['positioning'], new_player_data['reaction'],
                        new_player_data['playmaking'], new_player_data['passing'],
                        new_player_data['scoring'], new_player_data['one_one_scoring'],
                        new_player_data['post_player'], new_player_data['lines'],
                        new_player_data['middle_shooting'], new_player_data['side'],
                        new_player_data['centre'], new_player_data['penalties'],
                        new_player_data['one_touch_pass'], new_player_data['outside'],
                        new_player_data['marking'], new_player_data['sliding'],
                        new_player_data['covering'], new_player_data['d_line_control'],
                        new_player_data['penalty_stopper'], new_player_data['one_on_one_stopper'],
                        new_player_data['long_throw'], new_player_data['face_type'],
                        new_player_data['preset_face_number'], new_player_data['head_width'],
                        new_player_data['neck_length'], new_player_data['neck_width'],
                        new_player_data['shoulder_height'], new_player_data['shoulder_width'],
                        new_player_data['chest_measurement'], new_player_data['waist_circumference'],
                        new_player_data['arm_circumference'], new_player_data['leg_circumference'],
                        new_player_data['calf_circumference'], new_player_data['leg_length'],
                        new_player_data['wristband'], new_player_data['wristband_color'],
                        new_player_data['international_number'], new_player_data['classic_number'],
                        new_player_data['club_number'], new_player_data['dribble_style'],
                        new_player_data['free_kick_style'], new_player_data['pk_style'],
                        new_player_data['drop_kick_style'], new_player_data.get('seed_player'),
                        retired_id
                    ))

                    new_players_generated += 1
                    print(f"    ✅ Replaced {replacement['retired_player']['player_name']} (ID: {retired_id}) with {new_player_data['player_name']}")

                    # Clear historical data for the new regen (they should start with clean records)
                    cur.execute("DELETE FROM player_season_history WHERE player_id = ?", (retired_id,))
                    
                    # Reset career stats for the new regen
                    cur.execute("""
                        UPDATE players 
                        SET career_earnings = 0, championships_won = 0, cups_won = 0
                        WHERE id = ?
                    """, (retired_id,))

                except Exception as e:
                    print(f"    ❌ Error replacing {replacement['retired_player']['player_name']}: {e}")

            db_helper.commit()
            print(f"  ✅ Successfully replaced {new_players_generated} retiring players with regens")
            print(f"  ✅ Cleared historical data for {new_players_generated} new regens")

        # Step 10: Recalculate overall ratings for all players
        print("🔄 Step 10: Recalculating overall ratings for all players...")
        from refresh_and_reimport import recalculate_all_overalls
        recalculate_all_overalls()
        print("  ✅ Overall ratings recalculated for all players")

        # Step 10b: Recalculate bundled skill ratings after regens and overall updates
        print("🔄 Step 10b: Recalculating bundled skill ratings for all players...")
        from game_mechanics import calculate_bundled_skill_ratings
        
        # Get all players with their skills
        cur.execute("SELECT * FROM players")
        all_players = cur.fetchall()
        column_names = [description[0] for description in cur.description]
        
        ratings_updated = 0
        for player_row in all_players:
            player_dict = dict(zip(column_names, player_row))
            
            try:
                # Calculate bundled ratings
                bundled_ratings = calculate_bundled_skill_ratings(player_dict)
                
                # Update database
                cur.execute("""
                    UPDATE players 
                    SET attack_rating = ?, defense_rating = ?, physical_rating = ?, 
                        power_rating = ?, technique_rating = ?, goalkeeping_rating = ?
                    WHERE id = ?
                """, (
                    bundled_ratings['attack_rating'],
                    bundled_ratings['defense_rating'],
                    bundled_ratings['physical_rating'],
                    bundled_ratings['power_rating'],
                    bundled_ratings['technique_rating'],
                    bundled_ratings['goalkeeping_rating'],
                    player_dict['id']
                ))
                ratings_updated += 1
            except Exception as e:
                print(f"    ⚠️ Error updating bundled ratings for player {player_dict.get('player_name', 'Unknown')}: {e}")
                continue
        
        print(f"  ✅ Recalculated bundled skill ratings for {ratings_updated} players")

        # Step 11: Increment to next season
        print("🔄 Step 11: Incrementing to next season...")
        new_season = increment_season()
        print(f"  ✅ Season incremented from {current_season} to {new_season}")

        flash(f'End of season processing completed! {payments_processed} users had salary bills processed, {cpu_teams_processed} CPU teams updated, {age_updated} players aged, {contract_updated} contracts reduced, {salary_doubled} salaries doubled, {wage_rise_applied} wage rises applied, {players_developed} players had their skills developed, {retired_count} players retired, {new_players_generated} new young players joined to replace them, {history_records_created} player historical records created, and overall ratings recalculated.', 'success')

    except Exception as e:
        db_helper.get_connection().rollback()
        flash(f'Error during end of season processing: {e}', 'danger')
        print(f"❌ Error: {e}")
    finally:
        cur.close()

    return redirect(url_for('tools'))

@app.route('/tools/divide_salaries_by_2', methods=['POST'])
@login_required
def divide_salaries_by_2():
    """Divide all player salaries by 2"""
    cur = db_helper.get_cursor()

    try:
        cur.execute("SELECT id, player_name, salary FROM players WHERE salary > 0")
        players = cur.fetchall()

        updated_players = 0

        for player in players:
            old_salary = player['salary']
            new_salary = old_salary // 2  # Integer division by 2

            # Update player salary
            cur.execute("UPDATE players SET salary = ? WHERE id = ?", (new_salary, player['id']))
            updated_players += 1

        db_helper.commit()

        flash(f'All player salaries divided by 2! {updated_players} players updated.', 'success')

    except Exception as e:
        db_helper.get_connection().rollback()
        flash(f'Error dividing salaries: {e}', 'danger')
    finally:
        cur.close()

    return redirect(url_for('tools'))

@app.route('/tools/pay_current_salary_bill', methods=['POST'])
@login_required
def pay_current_salary_bill():
    """Directly deduct salary bills from all users (except CPU) and process CPU team finances"""
    cur = db_helper.get_cursor()

    try:
        # Process human users (except CPU)
        cur.execute("SELECT id, username FROM users WHERE id != 1")
        users = cur.fetchall()

        payments_processed = 0

        for user in users:
            # Calculate the user's total salary bill
            cur.execute("""
                SELECT SUM(p.salary) as total_salary
                FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.club_name = lt.team_name
                WHERE lt.user_id = ?
            """, (user['id'],))
            result = cur.fetchone()
            total_salary = result['total_salary'] if result and result['total_salary'] else 0
            total_salary = int(total_salary/2)  # Ensure it's an integer

            if total_salary <= 0:
                print(f"  - {user['username']}: No salary bill to pay")
                continue

            # Get top 3 highest paid players for the blog post
            cur.execute("""
                SELECT p.player_name, p.salary, lt.team_name
                FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.club_name = lt.team_name
                WHERE lt.user_id = ?
                ORDER BY p.salary DESC
                LIMIT 3
            """, (user['id'],))
            top_players = cur.fetchall()

            # Get total number of players
            cur.execute("""
                SELECT COUNT(*) as player_count
                FROM players p
                JOIN teams t ON p.club_id = t.id
                JOIN league_teams lt ON t.club_name = lt.team_name
                WHERE lt.user_id = ?
            """, (user['id'],))
            player_count = cur.fetchone()['player_count']

            # Update user's unified budget (negative amount = user pays)
            add_user_movement(user['id'], 'Salary Bill Payment',
                             f'Paid salary bill for all your players: €{total_salary:,}',
                             -total_salary)

            # Create enhanced blog post about the club's finances being in order
            blog_title = f"💰 {user['username']}'s Club Finances Settled"
            print(f"📝 Creating blog post for {user['username']}: {blog_title}")  # Debug line

            top_players_html = ""
            if top_players:
                top_players_html = "<p><strong>Top 3 Player Wages:</strong></p><ul>"
                for player in top_players:
                    top_players_html += f"<li>{player['player_name']} ({player['team_name']}): €{player['salary']:,}</li>"
                top_players_html += "</ul>"

            blog_content = f"""
            <p><strong>🏦 Processing Bank Payments</strong></p>
            <p><strong>{user['username']}</strong> has successfully processed their club's salary bill of <strong>€{total_salary:,}</strong>.</p>
            <p>The payment covers <strong>{player_count} players</strong> across all managed teams.</p>
            {top_players_html}
            <p><strong>✅ Financial Status:</strong> All player wages have been settled and the club's finances are now in order.</p>
            <p>This ensures continued team stability and player satisfaction in the league.</p>
            """
            post_transfer_news(blog_title, blog_content, user_id=1)
            print(f"✅ Blog post created for {user['username']}")  # Debug line

            # Small delay to make blog posts more visible
            time.sleep(0.5)

            payments_processed += 1
            print(f"  - {user['username']}: Salary bill paid (€{total_salary:,} for {player_count} players)")

        # Process CPU teams (update their financial data without blog posts)
        cpu_teams_processed = 0
        cur.execute("""
            SELECT t.id, t.club_name, COALESCE(SUM(p.salary), 0) as total_salaries, t.budget
            FROM teams t
            LEFT JOIN players p ON t.id = p.club_id
            JOIN league_teams lt ON t.club_name = lt.team_name
            WHERE lt.user_id = 1
            GROUP BY t.id, t.club_name, t.budget
        """)
        cpu_teams = cur.fetchall()

        for team in cpu_teams:
            team_id = team['id']
            club_name = team['club_name']
            total_salaries = team['total_salaries']
            total_salaries = int(total_salaries/2)  # Ensure it's an integer
            current_budget = team['budget'] or 400000000  # Default if budget is NULL

            if total_salaries > 0:
                # Reduce budget by the salary bill amount
                new_budget = current_budget - total_salaries

                # Calculate available cap with new budget
                available_cap = new_budget - total_salaries

                # Update CPU team financial data
                cur.execute("""
                    UPDATE teams
                    SET total_salaries = ?, budget = ?, available_cap = ?
                    WHERE id = ?
                """, (total_salaries, new_budget, available_cap, team_id))

                cpu_teams_processed += 1
                print(f"  - CPU {club_name}: Budget reduced by €{total_salaries:,} (€{current_budget:,} → €{new_budget:,}), available cap: €{available_cap:,}")

        # Create a summary blog post if multiple users were processed
        if payments_processed > 1:
            summary_title = f"🏦 League-Wide Salary Bill Processing Complete"
            summary_content = f"""
            <p><strong>📊 League Financial Update</strong></p>
            <p>The league has successfully processed salary bills for <strong>{payments_processed} clubs</strong>.</p>
            <p><strong>✅ All clubs have settled their player wages and their finances are now in order.</strong></p>
            <p>This ensures continued stability across the entire league and maintains player satisfaction.</p>
            """
            post_transfer_news(summary_title, summary_content, user_id=1)
            print(f"📊 Summary blog post created for {payments_processed} users")

        db_helper.commit()

        flash(f'Salary bills processed! {payments_processed} users had their salary bills deducted and blog posts created. {cpu_teams_processed} CPU teams had their financial data updated.', 'success')

    except Exception as e:
        db_helper.get_connection().rollback()
        flash(f'Error processing salary bills: {e}', 'danger')
        print(f"❌ Error: {e}")  # Debug line
    finally:
        cur.close()

    return redirect(url_for('tools'))



@app.route('/tools/money_allocator', methods=['GET', 'POST'])
@login_required
def money_allocator():
    """Money Allocator: Add or subtract money from user budgets"""
    cur = db_helper.get_cursor()

    if request.method == 'POST':
        user_id = request.form.get('user_id')
        amount = request.form.get('amount')
        operation = request.form.get('operation')  # 'add' or 'subtract'
        description = request.form.get('description', 'Manual allocation')

        try:
            user_id = int(user_id)
            amount = int(amount)

            if operation == 'subtract':
                amount = -amount  # Make it negative for subtraction

            # Get current budget
            current_budget = get_user_budget(user_id)
            new_budget = current_budget + amount

            # Update budget
            update_user_budget(user_id, new_budget)

            # Add movement record
            add_user_movement(user_id, 'Manual Allocation', description, amount)

            # Get username for flash message
            cur.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            user = cur.fetchone()
            username = user['username'] if user else f'User {user_id}'

            operation_text = 'added to' if amount > 0 else 'subtracted from'
            flash(f'€{abs(amount):,} {operation_text} {username}\'s budget. New balance: €{new_budget:,}', 'success')

        except ValueError:
            flash('Invalid amount or user ID.', 'danger')
        except Exception as e:
            flash(f'Error updating budget: {e}', 'danger')

    # Get all users for the form
    cur.execute("SELECT id, username FROM users WHERE id != 1 ORDER BY username")
    users = cur.fetchall()
    cur.close()

    return render_template('money_allocator.html', users=users)

@app.route('/tools/cpu_contract_renewals', methods=['POST'])
@login_required
def cpu_contract_renewals():
    """Process CPU team contract renewals for players with expired contracts"""
    try:
        from contract_renewal import ContractRenewalManager

        manager = ContractRenewalManager()
        if not manager.connect():
            flash('Failed to connect to database', 'danger')
            return redirect(url_for('tools'))

        try:
            # Process CPU contract renewals
            result = manager.process_cpu_contract_renewals()

            if result['success']:
                # Create blog post
                manager.create_contract_renewal_blog_post(result)

                flash(f'CPU contract renewals processed! {result["renewed"]} contracts renewed, {result["rejected"]} players entered free agency.', 'success')
            else:
                flash(f'Error processing CPU contract renewals: {result["error"]}', 'danger')

        finally:
            manager.disconnect()

    except Exception as e:
        flash(f'Error processing CPU contract renewals: {e}', 'danger')

    return redirect(url_for('tools'))

@app.route('/contract_renewal/get_expired_players', methods=['GET'])
@login_required
def get_expired_players():
    """Get user's players with expired contracts"""
    try:
        from contract_renewal import ContractRenewalManager

        manager = ContractRenewalManager()
        if not manager.connect():
            return jsonify({'success': False, 'error': 'Database connection failed'})

        try:
            expired_players = manager.get_user_players_with_expired_contracts(current_user.id)

            # Calculate contract terms for each player
            players_with_terms = []
            for player in expired_players:
                contract_terms = manager.calculate_new_contract_terms(player, is_cpu=False)
                player['contract_terms'] = contract_terms
                players_with_terms.append(player)

            return jsonify({
                'success': True,
                'players': players_with_terms
            })

        finally:
            manager.disconnect()

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/contract_renewal/sign', methods=['POST'])
@login_required
def sign_contract():
    """Sign player contract with their demands"""
    try:
        from contract_renewal import ContractRenewalManager

        player_id = int(request.form.get('player_id'))

        manager = ContractRenewalManager()
        if not manager.connect():
            return jsonify({'success': False, 'error': 'Failed to connect to database'})

        try:
            result = manager.sign_player_contract(player_id, current_user.id)
            return jsonify(result)

        finally:
            manager.disconnect()

    except Exception as e:
        return jsonify({'success': False, 'error': f'Error signing contract: {e}'})

@app.route('/contract_renewal/walk_away', methods=['POST'])
@login_required
def let_player_walk_away():
    """Let player walk away to free agency"""
    try:
        from contract_renewal import ContractRenewalManager

        player_id = int(request.form.get('player_id'))

        manager = ContractRenewalManager()
        if not manager.connect():
            return jsonify({'success': False, 'error': 'Failed to connect to database'})

        try:
            result = manager.let_player_walk_away(player_id, current_user.id)
            return jsonify(result)

        finally:
            manager.disconnect()

    except Exception as e:
        return jsonify({'success': False, 'error': f'Error letting player walk away: {e}'})

@app.route('/contract_renewal/reject', methods=['POST'])
@login_required
def reject_contract():
    """Handle player rejecting contract and going to free agency"""
    try:
        from contract_renewal import ContractRenewalManager

        player_id = int(request.form.get('player_id'))

        manager = ContractRenewalManager()
        if not manager.connect():
            return jsonify({'success': False, 'error': 'Failed to connect to database'})

        try:
            result = manager.reject_user_contract(player_id, current_user.id)
            return jsonify(result)

        finally:
            manager.disconnect()

    except Exception as e:
        return jsonify({'success': False, 'error': f'Error rejecting contract: {e}'})


@app.route('/free_agency/get_user_teams', methods=['GET'])
@login_required
def get_user_teams():
    """Get current user's teams for AJAX call"""
    cur = db_helper.get_cursor()
    cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = ? ORDER BY team_name", (current_user.id,))
    user_teams = cur.fetchall()
    cur.close()

    teams_list = [{'id': team['id'], 'name': team['team_name']} for team in user_teams]
    return jsonify({'teams': teams_list})

@app.route('/free_agency/place_player/<int:offer_id>', methods=['POST'])
@login_required
def place_expired_player(offer_id):
    """Place a player from an expired offer into a selected team via AJAX"""
    cur = db_helper.get_cursor()

    try:
        # Get the offer details with player age for signing bonus calculation
        cur.execute("""
            SELECT fao.id, fao.player_id, fao.user_id, fao.offered_salary, fao.offered_contract_years,
                   fao.expires_at, fao.status, p.player_name, p.age, u.username
            FROM free_agent_offers fao
            JOIN players p ON fao.player_id = p.id
            JOIN users u ON fao.user_id = u.id
            WHERE fao.id = ? AND fao.status = 'active'
        """, (offer_id,))
        offer = cur.fetchone()

        if not offer:
            return jsonify({'success': False, 'error': 'Offer not found or already processed.'})

        # Check if offer belongs to current user
        if offer['user_id'] != current_user.id:
            return jsonify({'success': False, 'error': 'You can only place players from your own offers.'})

        selected_team_id = request.json.get('selected_team_id')

        if not selected_team_id:
            return jsonify({'success': False, 'error': 'Please select a team.'})

        # Get the selected team
        cur.execute("SELECT id, team_name FROM league_teams WHERE id = ? AND user_id = ?",
                   (selected_team_id, current_user.id))
        selected_team = cur.fetchone()

        if not selected_team:
            return jsonify({'success': False, 'error': 'Invalid team selection.'})

        # Find the corresponding PES6 team ID
        cur.execute("SELECT id FROM teams WHERE club_name = ?", (selected_team['team_name'],))
        pes6_team_result = cur.fetchone()

        if not pes6_team_result:
            return jsonify({'success': False, 'error': 'Could not find the corresponding PES6 team.'})

        pes6_team_id = pes6_team_result['id']

        # Calculate signing bonus and yearly wage rise
        import random

        # Calculate signing bonus (25-50% of base salary, higher for younger players)
        player_age = offer['age']
        if player_age <= 22:
            signing_bonus_percentage = random.uniform(0.40, 0.50)  # 40-50% for very young players
        elif player_age <= 25:
            signing_bonus_percentage = random.uniform(0.35, 0.45)  # 35-45% for young players
        elif player_age <= 28:
            signing_bonus_percentage = random.uniform(0.30, 0.40)  # 30-40% for mid-age players
        else:
            signing_bonus_percentage = random.uniform(0.25, 0.35)  # 25-35% for older players

        signing_bonus = int(offer['offered_salary'] * signing_bonus_percentage)

        # Calculate yearly wage rise (same logic as contract renewal)
        if player_age <= 22:
            yearly_wage_rise = random.uniform(0.15, 0.25)  # 15-25% for very young players
        elif player_age <= 25:
            yearly_wage_rise = random.uniform(0.10, 0.20)  # 10-20% for young players
        elif player_age <= 28:
            yearly_wage_rise = random.uniform(0.05, 0.15)  # 5-15% for mid-age players
        else:
            yearly_wage_rise = random.uniform(0.01, 0.10)  # 1-10% for older players

        # Process the placement
        cur.execute("UPDATE free_agent_offers SET status = 'completed' WHERE id = ?", (offer_id,))

        # Update player's salary, contract, yearly wage rise, and club_id
        cur.execute("""
            UPDATE players
            SET salary = ?, contract_years_remaining = ?, yearly_wage_rise = ?, club_id = ?
            WHERE id = ?
        """, (offer['offered_salary'], offer['offered_contract_years'], yearly_wage_rise, pes6_team_id, offer['player_id']))

        # Deduct signing bonus from team budget
        cur.execute("UPDATE teams SET budget = budget - ? WHERE id = ?", (signing_bonus, pes6_team_id))

        # Record signing bonus transaction in finances
        add_user_movement(current_user.id, 'Signing Bonus',
                         f"Signing bonus for {offer['player_name']} (Free Agency)", -signing_bonus)

        # Add to team_players table
        cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)",
                   (selected_team['id'], offer['player_id']))

        # Post transfer news with signing bonus info
        title = f"Free Agent Placement: {offer['player_name']}"
        content = f"{offer['player_name']} has been placed in {selected_team['team_name']} by {offer['username']} for €{offer['offered_salary']:,} per year for {offer['offered_contract_years']} years. Signing bonus: €{signing_bonus:,} ({(signing_bonus_percentage*100):.1f}% of salary). Yearly wage rise: {(yearly_wage_rise*100):.1f}%."
        post_transfer_news(title, content, current_user.id)

        db_helper.commit()
        return jsonify({
            'success': True,
            'message': f'Successfully placed {offer["player_name"]} in {selected_team["team_name"]}!',
            'player_name': offer['player_name'],
            'team_name': selected_team['team_name']
        })

    except Exception as e:
        db_helper.get_connection().rollback()
        return jsonify({'success': False, 'error': f'Error placing player: {str(e)}'})
    finally:
        cur.close()



# CPU League Routes
@app.route('/cpu_leagues')
@login_required
def cpu_leagues():
    """CPU Leagues page"""
    return render_template('cpu_leagues_page.html')

@app.route('/cpu_leagues/initialize', methods=['POST'])
@login_required
def initialize_cpu_league():
    """Initialize CPU league with specified number of divisions"""
    try:
        from cpu_leagues import league_manager

        data = request.get_json()
        division_count = data.get('division_count', 4)

        success = league_manager.initialize_league(division_count)

        if success:
            return jsonify({
                'success': True,
                'data': league_manager.get_league_status(),
                'standings': league_manager.get_standings()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to initialize league. Not enough CPU teams with sufficient players.'
            })

    except Exception as e:
        app.logger.error(f"Error initializing CPU league: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/cpu_leagues/simulate_round', methods=['POST'])
@login_required
def simulate_cpu_league_round():
    """Simulate one round of CPU league matches"""
    try:
        from cpu_leagues import league_manager

        # Simulate the round
        round_results = league_manager.simulate_round()

        if 'error' in round_results:
            return jsonify({
                'success': False,
                'error': round_results['error']
            })

        # Update player statistics in database
        league_manager.update_player_statistics()

        # Generate revenue if league is completed
        revenue_data = None
        if league_manager.league_status.value == 'completed':
            revenue_data = league_manager.generate_revenue()

        # Get playoff tree if in playoffs or completed
        playoff_tree = None
        if league_manager.league_status.value in ['playoffs', 'completed']:
            playoff_tree = league_manager._get_playoff_tree()

        return jsonify({
            'success': True,
            'data': league_manager.get_league_status(),
            'standings': league_manager.get_standings(),
            'round_results': round_results,
            'playoff_tree': playoff_tree,
            'revenue': revenue_data
        })

    except Exception as e:
        app.logger.error(f"Error simulating CPU league round: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/cpu_leagues/status')
@login_required
def get_cpu_league_status():
    """Get current CPU league status"""
    try:
        from cpu_leagues import league_manager

        # Get playoff tree if in playoffs or completed
        playoff_tree = None
        if league_manager.league_status.value in ['playoffs', 'completed']:
            playoff_tree = league_manager._get_playoff_tree()

        return jsonify({
            'success': True,
            'data': league_manager.get_league_status(),
            'standings': league_manager.get_standings(),
            'playoff_tree': playoff_tree
        })

    except Exception as e:
        app.logger.error(f"Error getting CPU league status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/cpu_leagues/reset', methods=['POST'])
@login_required
def reset_cpu_league():
    """Reset CPU league to initial state"""
    try:
        from cpu_leagues import league_manager

        league_manager.reset_league()

        return jsonify({
            'success': True,
            'message': 'League reset successfully'
        })

    except Exception as e:
        app.logger.error(f"Error resetting CPU league: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/cpu_leagues/leaderboards')
@login_required
def get_cpu_league_leaderboards():
    """Get CPU league leaderboards (top scorers and assists)"""
    try:
        from cpu_leagues import league_manager

        top_scorers = league_manager.get_top_scorers(10)
        top_assists = league_manager.get_top_assists(10)

        return jsonify({
            'success': True,
            'top_scorers': top_scorers,
            'top_assists': top_assists
        })

    except Exception as e:
        app.logger.error(f"Error getting CPU league leaderboards: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/hall_of_fame')
@login_required
def hall_of_fame():
    """Hall of Fame page displaying retired players with their career statistics"""
    cur = db_helper.get_cursor()

    try:
        # Get filter parameters
        sort_by = request.args.get('sort_by', 'retirement_date')  # Default sort by retirement date
        order = request.args.get('order', 'desc')  # Default descending order
        position_filter = request.args.get('position', '')
        nationality_filter = request.args.get('nationality', '')
        min_goals = request.args.get('min_goals', '')
        min_games = request.args.get('min_games', '')

        # Build the query with filters
        base_query = """
            SELECT
                rp.player_name,
                rp.team_name,
                rp.age_at_retirement,
                rp.nationality,
                rp.registered_position,
                rp.retirement_date,
                rp.retirement_season,
                rp.career_earnings,
                rp.total_games_played,
                rp.total_goals,
                rp.total_assists,
                rp.final_salary,
                rp.final_market_value,
                rp.retirement_reason,
                rp.seasons_played,
                rp.championships_won,
                rp.cups_won,
                CASE
                    WHEN rp.total_games_played > 0
                    THEN ROUND((CAST(rp.total_goals AS REAL) / rp.total_games_played), 3)
                    ELSE 0
                END as goals_per_game,
                CASE
                    WHEN rp.total_games_played > 0
                    THEN ROUND((CAST(rp.total_assists AS REAL) / rp.total_games_played), 3)
                    ELSE 0
                END as assists_per_game
            FROM retired_players rp
            WHERE 1=1
        """

        params = []

        # Add filters
        if position_filter:
            base_query += " AND rp.registered_position = ?"
            params.append(position_filter)

        if nationality_filter:
            base_query += " AND rp.nationality = ?"
            params.append(nationality_filter)

        if min_goals:
            try:
                base_query += " AND rp.total_goals >= ?"
                params.append(int(min_goals))
            except ValueError:
                pass

        if min_games:
            try:
                base_query += " AND rp.total_games_played >= ?"
                params.append(int(min_games))
            except ValueError:
                pass

        # Add sorting
        valid_sorts = {
            'retirement_date': 'rp.retirement_date',
            'player_name': 'rp.player_name',
            'age_at_retirement': 'rp.age_at_retirement',
            'total_goals': 'rp.total_goals',
            'total_assists': 'rp.total_assists',
            'total_games_played': 'rp.total_games_played',
            'career_earnings': 'rp.career_earnings',
            'championships_won': 'rp.championships_won',
            'cups_won': 'rp.cups_won',
            'goals_per_game': 'goals_per_game',
            'assists_per_game': 'assists_per_game'
        }

        sort_column = valid_sorts.get(sort_by, 'rp.retirement_date')
        sort_order = 'DESC' if order.lower() == 'desc' else 'ASC'

        base_query += f" ORDER BY {sort_column} {sort_order}"

        # Execute query
        cur.execute(base_query, params)
        retired_players = cur.fetchall()

        # Get unique positions and nationalities for filter dropdowns
        cur.execute("SELECT DISTINCT registered_position FROM retired_players WHERE registered_position IS NOT NULL ORDER BY registered_position")
        positions = [row[0] for row in cur.fetchall()]

        cur.execute("SELECT DISTINCT nationality FROM retired_players WHERE nationality IS NOT NULL ORDER BY nationality")
        nationalities = [row[0] for row in cur.fetchall()]

        # Calculate some statistics
        cur.execute("""
            SELECT
                COUNT(*) as total_retired,
                AVG(age_at_retirement) as avg_retirement_age,
                SUM(total_goals) as total_goals_all_time,
                SUM(total_assists) as total_assists_all_time,
                SUM(career_earnings) as total_career_earnings,
                MAX(total_goals) as most_goals_single_career,
                MAX(total_assists) as most_assists_single_career,
                MAX(career_earnings) as highest_career_earnings
            FROM retired_players
        """)

        hall_stats = cur.fetchone()

        # Get top performers
        cur.execute("""
            SELECT player_name, total_goals, team_name
            FROM retired_players
            WHERE total_goals > 0
            ORDER BY total_goals DESC
            LIMIT 10
        """)
        top_scorers = cur.fetchall()

        cur.execute("""
            SELECT player_name, total_assists, team_name
            FROM retired_players
            WHERE total_assists > 0
            ORDER BY total_assists DESC
            LIMIT 10
        """)
        top_assisters = cur.fetchall()

        cur.execute("""
            SELECT player_name, career_earnings, team_name
            FROM retired_players
            WHERE career_earnings > 0
            ORDER BY career_earnings DESC
            LIMIT 10
        """)
        top_earners = cur.fetchall()

        return render_template('hall_of_fame.html',
                             retired_players=retired_players,
                             positions=positions,
                             nationalities=nationalities,
                             hall_stats=hall_stats,
                             top_scorers=top_scorers,
                             top_assisters=top_assisters,
                             top_earners=top_earners,
                             current_sort=sort_by,
                             current_order=order,
                             current_filters={
                                 'position': position_filter,
                                 'nationality': nationality_filter,
                                 'min_goals': min_goals,
                                 'min_games': min_games
                             })

    except Exception as e:
        app.logger.error(f"Error in hall_of_fame route: {e}")
        flash('Error loading Hall of Fame data.', 'danger')
        return render_template('hall_of_fame.html',
                             retired_players=[],
                             positions=[],
                             nationalities=[],
                             hall_stats=None,
                             top_scorers=[],
                             top_assisters=[],
                             top_earners=[],
                             current_sort='retirement_date',
                             current_order='desc',
                             current_filters={})
    finally:
        cur.close()

# Colados League Routes
@app.route('/colados_league')
@login_required
def colados_league():
    """Main Colados League page"""
    cur = db_helper.get_cursor()

    try:
        # Get league overview data
        cur.execute("SELECT COUNT(*) as total_teams FROM division_teams WHERE is_active = 1")
        total_teams = cur.fetchone()['total_teams']

        cur.execute("SELECT COUNT(*) as total_games FROM league_games WHERE is_played = 1")
        total_games_played = cur.fetchone()['total_games']

        current_season = get_current_season()

        # Get divisions with their standings
        cur.execute("""
            SELECT d.id, d.name, d.description
            FROM divisions d
            ORDER BY d.id
        """)
        divisions_data = cur.fetchall()

        divisions = []
        for division in divisions_data:
            # Get standings for this division
            cur.execute("""
                SELECT ds.team_name, ds.games_played, ds.wins, ds.draws, ds.losses,
                       ds.goals_for, ds.goals_against, ds.goal_difference, ds.points
                FROM division_standings ds
                WHERE ds.division_id = ?
                ORDER BY ds.points DESC, ds.goal_difference DESC, ds.goals_for DESC
            """, (division['id'],))
            standings = cur.fetchall()

            # Get recent games for this division
            cur.execute("""
                SELECT id, home_team_name, away_team_name, home_score, away_score, round_number
                FROM league_games
                WHERE division_id = ? AND is_played = 1
                ORDER BY game_date DESC
                LIMIT 100
            """, (division['id'],))
            recent_games = cur.fetchall()

            # Get pending games for this division
            cur.execute("""
                SELECT id, home_team_name, away_team_name, round_number
                FROM league_games
                WHERE division_id = ? AND is_played = 0
                ORDER BY round_number ASC, id ASC
                LIMIT 10
            """, (division['id'],))
            pending_games = cur.fetchall()

            # Get division-specific top goalscorers
            cur.execute("""
                SELECT p.player_name, t.club_name as team_name, SUM(pgs.goals) as total_goals
                FROM player_game_stats pgs
                JOIN players p ON pgs.player_id = p.id
                JOIN teams t ON pgs.team_id = t.id
                JOIN league_games lg ON pgs.game_id = lg.id
                WHERE lg.division_id = ? AND pgs.goals > 0
                GROUP BY pgs.player_id, p.player_name, t.club_name
                ORDER BY total_goals DESC
                LIMIT 10
            """, (division['id'],))
            division_goalscorers = cur.fetchall()

            # Get division-specific top assists
            cur.execute("""
                SELECT p.player_name, t.club_name as team_name, SUM(pgs.assists) as total_assists
                FROM player_game_stats pgs
                JOIN players p ON pgs.player_id = p.id
                JOIN teams t ON pgs.team_id = t.id
                JOIN league_games lg ON pgs.game_id = lg.id
                WHERE lg.division_id = ? AND pgs.assists > 0
                GROUP BY pgs.player_id, p.player_name, t.club_name
                ORDER BY total_assists DESC
                LIMIT 10
            """, (division['id'],))
            division_assists = cur.fetchall()

            divisions.append({
                'id': division['id'],
                'name': division['name'],
                'description': division['description'],
                'standings': standings,
                'recent_games': recent_games,
                'pending_games': pending_games,
                'top_goalscorers': division_goalscorers,
                'top_assists': division_assists
            })

        # Get all teams for the team selection dropdown (like in tools.html)
        cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
        teams = cur.fetchall()

        # Get division teams for easy access
        division_teams = {}
        for division in divisions:
            cur.execute("""
                SELECT dt.team_id, dt.team_name
                FROM division_teams dt
                WHERE dt.division_id = ? AND dt.is_active = 1
                ORDER BY dt.team_name
            """, (division['id'],))
            division_teams[division['id']] = cur.fetchall()

        return render_template('colados_league.html',
                             total_teams=total_teams,
                             total_games_played=total_games_played,
                             current_season=current_season,
                             divisions=divisions,
                             teams=teams,
                             division_teams=division_teams)

    except Exception as e:
        app.logger.error(f"Error in colados_league: {e}")
        flash('Error loading Colados League data', 'danger')
        return redirect(url_for('index'))
    finally:
        cur.close()

@app.route('/colados_league/get_division_teams/<int:division_id>')
@login_required
def get_division_teams(division_id):
    """Get teams assigned to a specific division"""
    cur = db_helper.get_cursor()

    try:
        cur.execute("""
            SELECT dt.team_id, dt.team_name
            FROM division_teams dt
            WHERE dt.division_id = ? AND dt.is_active = 1
            ORDER BY dt.team_name
        """, (division_id,))
        teams = cur.fetchall()

        # Convert tuples to dictionaries for JSON response
        teams_list = [{'team_id': team[0], 'team_name': team[1]} for team in teams]

        return jsonify({'teams': teams_list})

    except Exception as e:
        app.logger.error(f"Error getting division teams: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@app.route('/colados_league/test_teams')
def test_teams():
    """Test route to check if teams data is available"""
    cur = db_helper.get_cursor()

    try:
        # Get all teams with their ownership info
        cur.execute("""
            SELECT DISTINCT t.id, t.club_name,
                   COALESCE(lt.user_id, 1) as user_id,
                   COALESCE(u.username, 'CPU') as username
            FROM teams t
            LEFT JOIN league_teams lt ON t.club_name = lt.team_name
            LEFT JOIN users u ON lt.user_id = u.id
            ORDER BY t.club_name
        """)
        teams = cur.fetchall()

        # Convert to list of dictionaries for JSON serialization
        teams_list = []
        for team in teams:
            teams_list.append({
                'id': team['id'],
                'club_name': team['club_name'],
                'user_id': team['user_id'],
                'username': team['username']
            })

        return jsonify({'teams': teams_list, 'count': len(teams_list)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@app.route('/colados_league/get_available_teams')
@login_required
def get_available_teams():
    """Get all teams that can be added to divisions"""
    cur = db_helper.get_cursor()

    try:
        app.logger.info(f"Getting all available teams for Colados League")

        # Get all teams with their ownership info
        cur.execute("""
            SELECT DISTINCT t.id, t.club_name,
                   COALESCE(lt.user_id, 1) as user_id,
                   COALESCE(u.username, 'CPU') as username
            FROM teams t
            LEFT JOIN league_teams lt ON t.club_name = lt.team_name
            LEFT JOIN users u ON lt.user_id = u.id
            ORDER BY t.club_name
        """)
        teams = cur.fetchall()

        app.logger.info(f"Raw teams query result: {teams}")

        # Convert to list of dictionaries for JSON serialization
        teams_list = []
        for team in teams:
            teams_list.append({
                'id': team['id'],
                'club_name': team['club_name'],
                'user_id': team['user_id'],
                'username': team['username']
            })

        app.logger.info(f"Found {len(teams_list)} teams for Colados League: {teams_list}")
        return jsonify({'teams': teams_list})

    except Exception as e:
        app.logger.error(f"Error getting teams: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@app.route('/colados_league/add_team_to_division', methods=['POST'])
@login_required
def add_team_to_division():
    """Add a team to a division"""
    cur = db_helper.get_cursor()

    try:
        division_id = request.form.get('division_id')
        team_id = request.form.get('team_id')

        if not division_id or not team_id:
            flash('Missing division or team selection', 'error')
            return redirect(url_for('colados_league'))

        # Get team name
        cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
        team_result = cur.fetchone()
        if not team_result:
            flash('Team not found', 'error')
            return redirect(url_for('colados_league'))

        team_name = team_result['club_name']

        # Check if team is already in this division
        cur.execute("""
            SELECT id FROM division_teams
            WHERE division_id = ? AND team_id = ? AND is_active = 1
        """, (division_id, team_id))
        existing = cur.fetchone()

        if existing:
            flash('Team is already in this division', 'error')
            return redirect(url_for('colados_league'))

        # Add team to division
        cur.execute("""
            INSERT INTO division_teams (division_id, team_id, team_name)
            VALUES (?, ?, ?)
        """, (division_id, team_id, team_name))

        # Initialize standings for this team
        cur.execute("""
            INSERT OR IGNORE INTO division_standings (division_id, team_id, team_name)
            VALUES (?, ?, ?)
        """, (division_id, team_id, team_name))

        db_helper.commit()

        flash(f'Team {team_name} added to division successfully!', 'success')
        return redirect(url_for('colados_league'))

    except Exception as e:
        app.logger.error(f"Error adding team to division: {e}")
        db_helper.get_connection().rollback()
        flash(f'Error adding team to division: {str(e)}', 'error')
        return redirect(url_for('colados_league'))
    finally:
        cur.close()

@app.route('/colados_league/create_game', methods=['POST'])
@login_required
def create_game():
    """Create a new game in a division"""
    cur = db_helper.get_cursor()

    try:
        division_id = request.form.get('division_id')
        round_number = request.form.get('round_number')
        home_team_id = request.form.get('home_team_id')
        away_team_id = request.form.get('away_team_id')

        if not all([division_id, round_number, home_team_id, away_team_id]):
            flash('Missing required fields', 'danger')
            return redirect(url_for('colados_league'))

        if home_team_id == away_team_id:
            flash('Home and away teams must be different', 'danger')
            return redirect(url_for('colados_league'))

        # Get team names - fix tuple access
        cur.execute("SELECT id, club_name FROM teams WHERE id IN (?, ?)", (home_team_id, away_team_id))
        teams = cur.fetchall()
        if len(teams) != 2:
            flash('One or both teams not found', 'danger')
            return redirect(url_for('colados_league'))

        # Find home and away team names
        home_team_name = None
        away_team_name = None
        for team_id, team_name in teams:
            if str(team_id) == str(home_team_id):
                home_team_name = team_name
            elif str(team_id) == str(away_team_id):
                away_team_name = team_name

        if not home_team_name or not away_team_name:
            flash('Could not find team names', 'danger')
            return redirect(url_for('colados_league'))

        # Check if game already exists
        cur.execute("""
            SELECT id FROM league_games
            WHERE division_id = ? AND round_number = ? AND home_team_id = ? AND away_team_id = ?
        """, (division_id, round_number, home_team_id, away_team_id))
        existing = cur.fetchone()

        if existing:
            flash('This game already exists', 'danger')
            return redirect(url_for('colados_league'))

        # Create the game
        cur.execute("""
            INSERT INTO league_games (division_id, round_number, home_team_id, away_team_id,
                                    home_team_name, away_team_name, game_date)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (division_id, round_number, home_team_id, away_team_id, home_team_name, away_team_name))

        game_id = cur.lastrowid

        db_helper.commit()

        flash(f'Game created: {home_team_name} vs {away_team_name}', 'success')
        return redirect(url_for('game_management', game_id=game_id))

    except Exception as e:
        app.logger.error(f"Error creating game: {e}")
        db_helper.get_connection().rollback()
        flash('Error creating game: ' + str(e), 'danger')
        return redirect(url_for('colados_league'))
    finally:
        cur.close()

@app.route('/colados_league/game/<int:game_id>')
@login_required
def game_management(game_id):
    """Game management page for setting up lineups and submitting results"""
    cur = db_helper.get_cursor()

    try:
        # Get game details
        cur.execute("""
            SELECT lg.*, d.name as division_name
            FROM league_games lg
            JOIN divisions d ON lg.division_id = d.id
            WHERE lg.id = ?
        """, (game_id,))
        game = cur.fetchone()

        if not game:
            flash('Game not found', 'danger')
            return redirect(url_for('colados_league'))

        division = {'name': game['division_name']}

        # Get player stats if game is played
        home_player_stats = []
        away_player_stats = []

        if game['is_played']:
            cur.execute("""
                SELECT pgs.player_name, pgs.goals, pgs.assists, pgs.minutes_played
                FROM player_game_stats pgs
                WHERE pgs.game_id = ? AND pgs.team_id = ?
                ORDER BY pgs.goals DESC, pgs.assists DESC
            """, (game_id, game['home_team_id']))
            home_player_stats = [dict(row) for row in cur.fetchall()]

            cur.execute("""
                SELECT pgs.player_name, pgs.goals, pgs.assists, pgs.minutes_played
                FROM player_game_stats pgs
                WHERE pgs.game_id = ? AND pgs.team_id = ?
                ORDER BY pgs.goals DESC, pgs.assists DESC
            """, (game_id, game['away_team_id']))
            away_player_stats = [dict(row) for row in cur.fetchall()]

        return render_template('game_management.html',
                             game=game,
                             division=division,
                             home_player_stats=home_player_stats,
                             away_player_stats=away_player_stats)

    except Exception as e:
        app.logger.error(f"Error in game_management: {e}")
        flash('Error loading game data', 'danger')
        return redirect(url_for('colados_league'))
    finally:
        cur.close()

@app.route('/colados_league/remove_all_teams', methods=['POST'])
@login_required
def remove_all_colados_teams():
    """Remove all teams from all divisions in Colados League and clean up related data"""
    cur = db_helper.get_cursor()

    try:
        # Get count of teams to be removed for flash message
        cur.execute("SELECT COUNT(*) FROM division_teams WHERE is_active = 1")
        teams_count = cur.fetchone()[0]

        # Remove all teams from all divisions
        cur.execute("UPDATE division_teams SET is_active = 0")

        # Clear division standings
        cur.execute("DELETE FROM division_standings")

        # Clear league games (since no teams are in divisions)
        cur.execute("DELETE FROM league_games")

        # Clear player game stats
        cur.execute("DELETE FROM player_game_stats")

        db_helper.commit()

        if teams_count > 0:
            flash(f'✅ Successfully removed {teams_count} teams from all Colados League divisions and cleaned up standings, games, and player stats!', 'success')
        else:
            flash('ℹ️ No teams were currently in any divisions. Standings and games have been cleaned up.', 'info')

        return redirect(url_for('colados_league'))

    except Exception as e:
        app.logger.error(f"Error removing teams from Colados League: {e}")
        db_helper.get_connection().rollback()
        flash(f'❌ Error removing teams: {str(e)}', 'error')
        return redirect(url_for('colados_league'))
    finally:
        cur.close()

@app.route('/colados_league/get_team_players/<int:team_id>')
@login_required
def get_team_players(team_id):
    """Get players for a specific team"""
    cur = db_helper.get_cursor()

    try:
        cur.execute("""
            SELECT p.id, p.player_name, p.registered_position, p.overall,
                   CASE p.registered_position
                       WHEN 0 THEN 'GK'
                       WHEN 2 THEN 'SW'
                       WHEN 3 THEN 'CB'
                       WHEN 4 THEN 'SB'
                       WHEN 5 THEN 'DMF'
                       WHEN 6 THEN 'WB'
                       WHEN 7 THEN 'CMF'
                       WHEN 8 THEN 'SMF'
                       WHEN 9 THEN 'AMF'
                       WHEN 10 THEN 'WF'
                       WHEN 11 THEN 'SS'
                       WHEN 12 THEN 'CF'
                       ELSE 'Unknown'
                   END as position
            FROM players p
            WHERE p.club_id = ?
            ORDER BY p.overall DESC, p.player_name
        """, (team_id,))
        players = cur.fetchall()

        # Convert Row objects to dictionaries for JSON serialization
        players_list = []
        for player in players:
            players_list.append({
                'id': player[0],
                'player_name': player[1],
                'registered_position': player[2],
                'overall': player[3],
                'position': player[4]
            })

        return jsonify({'players': players_list})

    except Exception as e:
        app.logger.error(f"Error getting team players: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@app.route('/colados_league/submit_match_result/<int:game_id>', methods=['POST'])
@login_required
def submit_match_result(game_id):
    """Submit match result with lineups and player stats"""
    cur = db_helper.get_cursor()

    try:
        data = request.get_json()
        home_score = data.get('home_score')
        away_score = data.get('away_score')
        match_date = data.get('match_date')
        home_lineup = data.get('home_lineup', [])
        away_lineup = data.get('away_lineup', [])
        player_stats = data.get('player_stats', [])

        if home_score is None or away_score is None:
            return jsonify({'error': 'Missing scores'}), 400

        # Get game details
        cur.execute("SELECT * FROM league_games WHERE id = ?", (game_id,))
        game = cur.fetchone()

        if not game:
            return jsonify({'error': 'Game not found'}), 404

        # If game was already played, rollback previous stats so we can update
        if game['is_played']:
            # Revert player career stats from previous submission
            cur.execute("""
                SELECT player_id, goals, assists
                FROM player_game_stats
                WHERE game_id = ?
            """, (game_id,))
            old_stats = cur.fetchall()

            for row in old_stats:
                cur.execute("""
                    UPDATE players
                    SET goals = goals - ?, assists = assists - ?,
                        games_played = CASE WHEN games_played > 0 THEN games_played - 1 ELSE 0 END
                    WHERE id = ?
                """, (row['goals'] or 0, row['assists'] or 0, row['player_id']))

            # Remove previous per-game stats
            cur.execute("DELETE FROM player_game_stats WHERE game_id = ?", (game_id,))

        # Update game with result
        cur.execute("""
            UPDATE league_games
            SET home_score = ?, away_score = ?, game_date = ?, is_played = 1
            WHERE id = ?
        """, (home_score, away_score, match_date, game_id))

        # Get player names for stats
        player_names = {}
        for stat in player_stats:
            cur.execute("SELECT player_name FROM players WHERE id = ?", (stat['player_id'],))
            player = cur.fetchone()
            if player:
                player_names[stat['player_id']] = player['player_name']

        # Insert player game stats
        for stat in player_stats:
            # Only insert stats for players who played
            if stat.get('played', True):
                cur.execute("""
                    INSERT INTO player_game_stats (game_id, player_id, team_id, player_name,
                                                 goals, assists, minutes_played, is_starter)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    game_id,
                    stat['player_id'],
                    stat['team_id'],
                    player_names.get(stat['player_id'], ''),
                    stat.get('goals', 0),
                    stat.get('assists', 0),
                    90,  # Default minutes played
                    1 if stat['player_id'] in home_lineup + away_lineup else 0
                ))

        # Update player career stats (only for players who played)
        for stat in player_stats:
            if stat.get('played', True):
                cur.execute("""
                    UPDATE players
                    SET goals = goals + ?, assists = assists + ?, games_played = games_played + 1
                    WHERE id = ?
                """, (stat.get('goals', 0), stat.get('assists', 0), stat['player_id']))

        # Update division standings
        update_division_standings(game['division_id'], game['home_team_id'], game['away_team_id'],
                                home_score, away_score)

        db_helper.commit()

        return jsonify({'success': True, 'message': 'Match result submitted successfully'})

    except Exception as e:
        app.logger.error(f"Error submitting match result: {e}")
        db_helper.get_connection().rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

def update_division_standings(division_id, home_team_id, away_team_id, home_score, away_score):
    """Recalculate division standings from all existing games"""
    cur = db_helper.get_cursor()

    try:
        # Get all teams in this division
        cur.execute("""
            SELECT dt.team_id, t.club_name as team_name
            FROM division_teams dt
            JOIN teams t ON dt.team_id = t.id
            WHERE dt.division_id = ? AND dt.is_active = 1
        """, (division_id,))
        teams = cur.fetchall()

        # Clear existing standings for this division
        cur.execute("DELETE FROM division_standings WHERE division_id = ?", (division_id,))

        # Initialize standings for all teams
        for team in teams:
            cur.execute("""
                INSERT INTO division_standings
                (division_id, team_id, team_name, games_played, wins, draws, losses,
                 goals_for, goals_against, goal_difference, points, updated_at)
                VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, datetime('now'))
            """, (division_id, team['team_id'], team['team_name']))

        # Get all played games for this division
        cur.execute("""
            SELECT home_team_id, away_team_id, home_score, away_score
            FROM league_games
            WHERE division_id = ? AND is_played = 1
        """, (division_id,))
        games = cur.fetchall()

        # Process each game
        for game in games:
            home_team_id = game['home_team_id']
            away_team_id = game['away_team_id']
            home_score = game['home_score']
            away_score = game['away_score']

            # Determine match result
            if home_score > away_score:
                # Home team wins
                home_wins = 1
                home_draws = 0
                home_losses = 0
                home_points = 3
                away_wins = 0
                away_draws = 0
                away_losses = 1
                away_points = 0
            elif away_score > home_score:
                # Away team wins
                home_wins = 0
                home_draws = 0
                home_losses = 1
                home_points = 0
                away_wins = 1
                away_draws = 0
                away_losses = 0
                away_points = 3
            else:
                # Draw
                home_wins = 0
                home_draws = 1
                home_losses = 0
                home_points = 1
                away_wins = 0
                away_draws = 1
                away_losses = 0
                away_points = 1

            # Update home team standings
            cur.execute("""
                UPDATE division_standings
                SET games_played = games_played + 1,
                    wins = wins + ?,
                    draws = draws + ?,
                    losses = losses + ?,
                    goals_for = goals_for + ?,
                    goals_against = goals_against + ?,
                    goal_difference = goal_difference + ? - ?,
                    points = points + ?,
                    updated_at = datetime('now')
                WHERE division_id = ? AND team_id = ?
            """, (home_wins, home_draws, home_losses, home_score, away_score,
                  home_score, away_score, home_points, division_id, home_team_id))

            # Update away team standings
            cur.execute("""
                UPDATE division_standings
                SET games_played = games_played + 1,
                    wins = wins + ?,
                    draws = draws + ?,
                    losses = losses + ?,
                    goals_for = goals_for + ?,
                    goals_against = goals_against + ?,
                    goal_difference = goal_difference + ? - ?,
                    points = points + ?,
                    updated_at = datetime('now')
                WHERE division_id = ? AND team_id = ?
            """, (away_wins, away_draws, away_losses, away_score, home_score,
                  away_score, home_score, away_points, division_id, away_team_id))

    except Exception as e:
        app.logger.error(f"Error updating division standings: {e}")
        raise

@app.route('/beginning_of_season', methods=['POST'])
@login_required
def beginning_of_season():
    """Generate beginning of season blog posts"""
    cur = db_helper.get_cursor()

    try:
        # First, recalculate overall ratings for all players to ensure accuracy
        from refresh_and_reimport import recalculate_all_overalls
        recalculate_all_overalls()

        # Post 1: Strength by Strength - Top 10 players per position
        strength_content = generate_strength_by_strength_post(cur)

        # Create the blog post
        post_transfer_news("🏆 Strength by Strength - Season Preview", strength_content, user_id=1)

        flash("✅ Strength by Strength blog post generated successfully!", "success")

    except Exception as e:
        app.logger.error(f"Error generating beginning of season posts: {e}")
        flash(f"❌ Error generating posts: {e}", "danger")
    finally:
        cur.close()

    return redirect(url_for('tools'))

def generate_strength_by_strength_post(cur):
    """Generate the Strength by Strength blog post"""
    content = "🏆 <strong>STRENGTH BY STRENGTH - SEASON PREVIEW</strong><br><br>"
    content += "As we kick off the new season, let's analyze the top talent across all positions:<br><br>"

    # Position mapping from numbers to names
    position_names = {
        0: "Goal-Keeper",
        2: "Sweeper",
        3: "Center-Back",
        4: "Side-Back",
        5: "Defensive Midfielder",
        6: "Wing-Back",
        7: "Central Midfielder",
        8: "Side Midfielder",
        9: "Attacking Midfielder",
        10: "Winger",
        11: "Shadow Striker",
        12: "Striker"
    }

    # Get all registered positions in the specified order (excluding "No club" players)
    ordered_positions = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    positions = [{'registered_position': pos} for pos in ordered_positions]

    for position_row in positions:
        position_num = int(position_row['registered_position'])
        position_name = position_names.get(position_num, f"Position {position_num}")

        # Get top 10 players for this position (excluding "No club" players)
        cur.execute("""
            SELECT p.player_name, p.overall, t.club_name
            FROM players p
            JOIN teams t ON p.club_id = t.id
            WHERE p.registered_position = ?
            AND t.club_name != 'No Club'
            ORDER BY p.overall DESC
            LIMIT 10
        """, (position_num,))

        players = cur.fetchall()

        if players:
            content += f"<strong>{position_name}:</strong><br>"
            for i, player in enumerate(players, 1):
                content += f"• {player['player_name']} ({player['overall']}) - {player['club_name']}<br>"
            content += "<br>"

    content += "---<br><em>Generated at the beginning of the season</em>"
    return content

def generate_user_status_post(cur):
    """Generate the User Status blog post"""
    content = "👥 **USER STATUS REPORT - SEASON START**\n\n"
    content += "Here's a comprehensive look at all user teams and their key players:\n\n"

    # Get all users with their teams
    cur.execute("""
        SELECT u.id, u.username, lt.id as team_id, lt.team_name, lt.budget
        FROM users u
        JOIN league_teams lt ON u.id = lt.user_id
        WHERE u.id != 1
        ORDER BY u.username, lt.team_name
    """)
    user_teams = cur.fetchall()

    # Group teams by user
    users_data = {}
    for team in user_teams:
        user_id = team['id']
        if user_id not in users_data:
            users_data[user_id] = {
                'username': team['username'],
                'teams': []
            }
        users_data[user_id]['teams'].append(team)

    for user_id, user_data in users_data.items():
        content += f"**{user_data['username']}:**\n"

        # Sort teams by market value and total salaries
        teams_with_stats = []
        for team in user_data['teams']:
            # Get team market value and total salaries
            cur.execute("""
                SELECT
                    SUM(p.market_value) as total_market_value,
                    SUM(p.salary) as total_salaries,
                    COUNT(p.id) as player_count
                FROM players p
                JOIN teams t ON p.club_id = t.id
                WHERE t.club_name = ?
            """, (team['team_name'],))

            stats = cur.fetchone()
            total_market_value = stats['total_market_value'] or 0
            total_salaries = stats['total_salaries'] or 0

            teams_with_stats.append({
                'team': team,
                'market_value': total_market_value,
                'salaries': total_salaries
            })

        # Sort by market value (descending)
        teams_with_stats.sort(key=lambda x: x['market_value'], reverse=True)

        for team_data in teams_with_stats:
            team = team_data['team']
            content += f"  • **{team['team_name']}** (Budget: €{team['budget']:,})\n"
            content += f"    Market Value: €{team_data['market_value']:,} | Salaries: €{team_data['salaries']:,}\n"

            # Get top 3 players by overall
            cur.execute("""
                SELECT p.player_name, p.overall, p.registered_position
                FROM players p
                JOIN teams t ON p.club_id = t.id
                WHERE t.club_name = ?
                ORDER BY p.overall DESC
                LIMIT 3
            """, (team['team_name'],))

            key_players = cur.fetchall()
            if key_players:
                content += "    Key Players: "
                player_list = []
                for player in key_players:
                    player_list.append(f"{player['player_name']} ({player['overall']}, {player['registered_position']})")
                content += " | ".join(player_list) + "\n"
            content += "\n"

    content += "---\n*Generated at the beginning of the season*\n"
    return content

@app.route('/draft')
@login_required
def draft():
    """View draft pool - all players with draftee=1"""
    cur = db_helper.get_cursor()
    
    cur.execute("""
        SELECT p.*, t.club_name
        FROM players p
        LEFT JOIN teams t ON p.club_id = t.id
        WHERE p.draftee = 1
        ORDER BY p.overall DESC, p.player_name
    """)
    
    draftees = []
    columns = [description[0] for description in cur.description]
    for row in cur.fetchall():
        player_dict = dict(zip(columns, row))
        draftees.append(player_dict)
    
    # Get all teams for draft dropdown
    cur.execute("""
        SELECT id, club_name 
        FROM teams 
        WHERE id != 141
        ORDER BY club_name
    """)
    all_teams = cur.fetchall()
    
    position_names = {
        0: "Goal-Keeper",
        2: "Sweeper",
        3: "Center-Back",
        4: "Side-Back",
        5: "Defensive Midfielder",
        6: "Wing-Back",
        7: "Central Midfielder",
        8: "Side Midfielder",
        9: "Attacking Midfielder",
        10: "Winger",
        11: "Shadow Striker",
        12: "Striker"
    }
    
    return render_template('draft.html', draftees=draftees, position_names=position_names, all_teams=all_teams)

@app.route('/draft_player/<int:player_id>/<int:team_id>', methods=['POST'])
@login_required
def draft_player(player_id, team_id):
    """Draft a player to a team"""
    # Get team_id from form if provided (from dropdown), otherwise use URL parameter
    team_id_from_form = request.form.get('team_id')
    if team_id_from_form:
        team_id = int(team_id_from_form)
    
    cur = db_helper.get_cursor()
    
    # Check if player is a draftee
    cur.execute("SELECT player_name, draftee FROM players WHERE id = ?", (player_id,))
    player = cur.fetchone()
    
    if not player:
        flash("❌ Player not found!", "error")
        return redirect(url_for('draft'))
    
    if not player['draftee']:
        flash("❌ This player is not eligible for drafting!", "error")
        return redirect(url_for('draft'))
    
    # Get team name
    cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
    team = cur.fetchone()
    
    if not team:
        flash("❌ Team not found!", "error")
        return redirect(url_for('draft'))
    
    try:
        # Transfer player to team and remove draftee status
        cur.execute("""
            UPDATE players 
            SET club_id = ?, draftee = 0
            WHERE id = ?
        """, (team_id, player_id))
        
        # Remove from blacklist
        cur.execute("DELETE FROM blacklist WHERE player_id = ?", (player_id,))
        
        db_helper.commit()
        flash(f"✅ {player['player_name']} has been drafted to {team['club_name']}!", "success")
        
        # Post blog news
        title = f"Draft: {player['player_name']} joins {team['club_name']}"
        content = f"{player['player_name']} has been drafted from the draft pool and will now play for {team['club_name']}!"
        post_transfer_news(title, content, current_user.id)
        
    except Exception as e:
        flash(f"❌ Error drafting player: {str(e)}", "error")
    
    return redirect(url_for('draft'))

@app.route('/tools/create_newcomers', methods=['GET', 'POST'])
@login_required
def create_newcomers():
    """Create new players by overwriting existing ones"""
    import random
    
    if request.method == 'GET':
        # Get unique nationalities from database
        cur = db_helper.get_cursor()
        cur.execute("""
            SELECT DISTINCT nationality 
            FROM players 
            WHERE nationality IS NOT NULL AND nationality != ''
            ORDER BY nationality
        """)
        nationalities = [row[0] for row in cur.fetchall()]
        
        return render_template('newcomers.html', nationalities=nationalities)
    
    elif request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'generate':
            # Find a player with matching overall and position, copy their skills
            name = request.form.get('name')
            
            if not name:
                return jsonify({'success': False, 'error': 'Player name is required'})
            
            target_overall = int(request.form.get('overall', 75))
            position = request.form.get('position', '7')
            
            # Find a random player with matching overall and position
            cur = db_helper.get_cursor()
            
            # Try to find exact match first
            template_player = None
            for overall_diff in range(0, 10):  # Search overall ±9 if exact not found
                for overall_delta in [0, overall_diff, -overall_diff]:
                    search_overall = target_overall + overall_delta
                    if search_overall < 40 or search_overall > 99:
                        continue
                    
                    cur.execute("""
                        SELECT * FROM players 
                        WHERE registered_position = ? 
                        AND CAST(overall AS INTEGER) = ?
                        ORDER BY RANDOM()
                        LIMIT 1
                    """, (position, search_overall))
                    
                    template_player = cur.fetchone()
                    if template_player:
                        break
                
                if template_player:
                    break
            
            if not template_player:
                return jsonify({'success': False, 'error': f'No template player found for position {position} and overall {target_overall}'})
            
            # Get column names
            column_names = [description[0] for description in cur.description]
            template_dict = dict(zip(column_names, template_player))
            
            # Define all fields to copy
            skills = [
                'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                'response', 'agility', 'dribble_accuracy', 'dribble_speed',
                'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
                'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy',
                'heading', 'swerve', 'jump', 'technique', 'aggression', 'mentality',
                'goal_keeping', 'team_work', 'consistency', 'condition_fitness'
            ]
            
            abilities = ['dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking', 
                       'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 
                       'middle_shooting', 'side', 'centre', 'penalties', 'one_touch_pass', 
                       'outside', 'marking', 'sliding', 'covering', 'd_line_control', 
                       'penalty_stopper', 'one_on_one_stopper', 'long_throw']
            
            styles = ['gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf']
            
            appearance = ['face_type', 'skin_color', 'strong_foot']
            
            # Copy data from template player
            generated_data = {}
            
            for skill in skills:
                generated_data[skill] = template_dict.get(skill, 50)
            
            for ability in abilities:
                generated_data[ability] = template_dict.get(ability, 0)
            
            for style in styles:
                generated_data[style] = template_dict.get(style, 0)
            
            for attr in appearance:
                if attr == 'strong_foot':
                    generated_data[attr] = template_dict.get(attr, 'R')
                else:
                    generated_data[attr] = template_dict.get(attr, 0)
            
            # Template player info
            template_name = template_dict.get('player_name', 'Unknown')
            template_overall = template_dict.get('overall', target_overall)
            
            return jsonify({
                'success': True, 
                'generated': True,
                'template_player': f"{template_name} (Overall {template_overall})",
                'data': generated_data
            })
        
        elif action == 'commit':
            # Create new player in No Club (free agency)
            cur = db_helper.get_cursor()
            
            name = request.form.get('name')
            
            if not name:
                flash("⚠️ Player name is required.", 'warning')
                return redirect(url_for('create_newcomers'))
            
            # Collect all form data for INSERT
            insert_fields = ['player_name', 'age', 'height', 'weight', 'registered_position', 'nationality', 
                           'contract_years_remaining', 'salary', 'yearly_wage_rise', 'draftee', 'club_id', 'career_earnings']
            insert_values = [
                name,
                request.form.get('age'),
                request.form.get('height'),
                request.form.get('weight'),
                request.form.get('position'),
                request.form.get('nationality', 'Portugal'),
                3,  # contract_years_remaining
                1000000,  # salary
                0.25,  # yearly_wage_rise
                1,  # draftee (marks as manually created)
                141,  # No Club (free agency)
                0  # career_earnings (start fresh)
            ]
            
            # Skills - collect all of them for bundled rating calculation
            skills = [
                'attack', 'defense', 'balance', 'stamina', 'top_speed', 'acceleration',
                'response', 'agility', 'dribble_accuracy', 'dribble_speed',
                'short_pass_accuracy', 'short_pass_speed', 'long_pass_accuracy', 'long_pass_speed',
                'shot_accuracy', 'shot_power', 'shot_technique', 'free_kick_accuracy',
                'heading', 'swerve', 'jump', 'technique', 'aggression', 'mentality',
                'goal_keeping', 'team_work', 'consistency', 'condition_fitness'
            ]
            
            skill_dict = {}
            for skill in skills:
                value = request.form.get(skill)
                if value:
                    skill_value = int(value)
                    insert_fields.append(skill)
                    insert_values.append(skill_value)
                    skill_dict[skill] = skill_value
                else:
                    # If skill not in form, use default of 50
                    insert_fields.append(skill)
                    insert_values.append(50)
                    skill_dict[skill] = 50
            
            # Appearance
            appearance_fields = ['face_type', 'skin_color', 'strong_foot']
            for field in appearance_fields:
                value = request.form.get(field)
                if value is not None:
                    insert_fields.append(field)
                    insert_values.append(value)
            
            # Special abilities (checkboxes)
            abilities = ['dribbling_skill', 'tactical_dribble', 'positioning', 'reaction', 'playmaking', 
                       'passing', 'scoring', 'one_one_scoring', 'post_player', 'lines', 
                       'middle_shooting', 'side', 'centre', 'penalties', 'one_touch_pass', 
                       'outside', 'marking', 'sliding', 'covering', 'd_line_control', 
                       'penalty_stopper', 'one_on_one_stopper', 'long_throw']
            
            for ability in abilities:
                value = 1 if request.form.get(ability) else 0
                insert_fields.append(ability)
                insert_values.append(value)
            
            # Playing styles (checkboxes)
            styles = ['gk', 'cwp', 'cbt', 'sb', 'dmf', 'wb', 'cmf', 'smf', 'amf', 'wf', 'ss', 'cf']
            for style in styles:
                value = 1 if request.form.get(style) else 0
                insert_fields.append(style)
                insert_values.append(value)
            
            # Calculate overall rating and bundled skill ratings based on skills and position
            from refresh_and_reimport import calculate_player_overall
            from game_mechanics import calculate_bundled_skill_ratings
            
            # Build temp player dict for overall calculation using all inserted data
            temp_player_data = {}
            for i, field in enumerate(insert_fields):
                temp_player_data[field] = insert_values[i]
            
            # Calculate overall
            overall = calculate_player_overall(temp_player_data)
            
            # Calculate bundled skill ratings using the skill_dict we already built
            try:
                bundled_ratings = calculate_bundled_skill_ratings(skill_dict)
                print(f"DEBUG: Calculated bundled ratings: {bundled_ratings}")
            except Exception as e:
                app.logger.error(f"Error calculating bundled ratings: {e}")
                app.logger.error(f"Skill dict: {skill_dict}")
                print(f"ERROR calculating bundled ratings: {e}")
                # Fallback to default values
                bundled_ratings = {
                    'attack_rating': 50,
                    'defense_rating': 50,
                    'physical_rating': 50,
                    'power_rating': 50,
                    'technique_rating': 50,
                    'goalkeeping_rating': 50
                }
            
            # Add overall and bundled ratings to insert
            insert_fields.append('overall')
            insert_values.append(overall)
            
            insert_fields.extend(['attack_rating', 'defense_rating', 'physical_rating', 
                                'power_rating', 'technique_rating', 'goalkeeping_rating'])
            insert_values.extend([
                bundled_ratings['attack_rating'],
                bundled_ratings['defense_rating'],
                bundled_ratings['physical_rating'],
                bundled_ratings['power_rating'],
                bundled_ratings['technique_rating'],
                bundled_ratings['goalkeeping_rating']
            ])
            
            print(f"DEBUG: Inserting bundled ratings - Attack: {bundled_ratings['attack_rating']}, Defense: {bundled_ratings['defense_rating']}, Physical: {bundled_ratings['physical_rating']}")
            
            # Build INSERT query
            fields_clause = ', '.join(insert_fields)
            placeholders = ', '.join(['?' for _ in insert_fields])
            
            try:
                cur.execute(f"""
                    INSERT INTO players ({fields_clause})
                    VALUES ({placeholders})
                """, insert_values)
                
                # Get the newly created player ID
                new_player_id = cur.lastrowid
                
                # Add player to blacklist (for all users, use user_id=1 as default)
                cur.execute("INSERT INTO blacklist (user_id, player_id) VALUES (1, ?)", (new_player_id,))
                
                db_helper.commit()
                flash(f"✅ Successfully created newcomer: {name}! (Overall: {overall}, Player ID: {new_player_id}, placed in No Club, blacklisted)", 'success')
            except Exception as e:
                flash(f"❌ Error creating player: {str(e)}", 'error')
            
            return redirect(url_for('create_newcomers'))
    
    return redirect(url_for('tools'))

if __name__ == '__main__':
    # For local development
    # app.run(debug=True)

    # For production with Waitress (if you decide to use it manually)
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000)
