import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort, jsonify, Response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
import json
import random
import time
import csv
from io import StringIO

from config import Config
import db_helper  # New helper module for SQLite access

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

            pes6_team_id = int(selected_team_ids[0])
            # Get the name of the selected PES6 team
            cur.execute("SELECT club_name FROM teams WHERE id = ?", (pes6_team_id,))
            pes6_team_name_result = cur.fetchone()
            if not pes6_team_name_result:
                raise Exception(f"Selected PES6 team with ID {pes6_team_id} not found.")
            pes6_team_name = pes6_team_name_result[0]

            # Always ensure the user gets a team in league_teams and the roster is populated
            cur.execute("SELECT id FROM league_teams WHERE team_name = ?", (pes6_team_name,))
            league_team = cur.fetchone()
            if league_team:
                league_team_id = league_team[0]
                cur.execute("UPDATE league_teams SET user_id = ? WHERE id = ?", (new_user_id, league_team_id))
            else:
                cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (?, ?)", (new_user_id, pes6_team_name))
                db_helper.commit()
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

    managed_teams_data = []
    total_salaries_user_teams = 0 # Initialize total salaries for financial summary
    user_total_budget = 0

    for team_meta in user_teams_meta:
        team_id = team_meta['id']
        team_name = team_meta['team_name']
        team_budget = team_meta['budget']
        user_total_budget += team_budget

        cur = db_helper.get_cursor()
        # Fetch players for this specific team, including financial info
        cur.execute("""
            SELECT
                p.id, p.player_name, p.registered_position, p.salary, p.contract_years_remaining, p.market_value
            FROM players p
            JOIN team_players tp ON p.id = tp.player_id
            WHERE tp.team_id = ?
            ORDER BY p.player_name ASC
        """, (team_id,))
        team_players_roster = cur.fetchall()
        cur.close()

        # Sum salaries for this team
        team_salary_sum = sum(p['salary'] for p in team_players_roster if p['salary'] is not None)
        total_salaries_user_teams += team_salary_sum

        managed_teams_data.append({
            'id': team_id,
            'name': team_name,
            'players': team_players_roster,
            'team_salary_sum': team_salary_sum # Optionally pass per-team salary sum
        })
    
    # Calculate financial summary for the user's managed teams
    TOTAL_LEAGUE_BUDGET = 450000000 # Define your total budget (same as admin page)
    free_cap_user_teams = TOTAL_LEAGUE_BUDGET - total_salaries_user_teams

    # Check if user can create more teams
    can_create_team = len(user_teams_meta) < 1

    return render_template('team_management.html', 
                           managed_teams=managed_teams_data, 
                           can_create_team=can_create_team,
                           coach_username=current_user.username,
                           total_budget_display=user_total_budget,
                           total_salaries_user_teams=total_salaries_user_teams,
                           free_cap_user_teams=free_cap_user_teams)

@app.route('/team_management/create', methods=['POST'])
@login_required
def create_team():
    cur = db_helper.get_cursor()
    cur.execute("SELECT COUNT(id) FROM league_teams WHERE user_id = ?", (current_user.id,))
    team_count = cur.fetchone()[0]
    cur.close()

    if team_count >= 2:
        flash('You can only manage a maximum of 1 team.', 'danger')
        return redirect(url_for('team_management'))

    team_name = request.form['team_name']
    user_id = current_user.id

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
    cur.execute("SELECT club_name FROM teams WHERE id = ?", (team_id,))
    team_name = cur.fetchone()
    if not team_name:
        flash("PES6 Team not found!", "danger")
        return redirect(url_for('pes6_game_teams'))
    team_name = team_name[0]

    cur.execute("""
        SELECT id, player_name, registered_position, age, height, strong_foot, attack
        FROM players
        WHERE club_id = ?
        ORDER BY player_name ASC
    """, (team_id,))
    players_in_team = cur.fetchall()
    cur.close()
    return render_template('pes6_team_details.html', team_name=team_name, players_in_team=players_in_team)


@app.route('/pes6_player/<int:player_id>')
def pes6_player_details(player_id):
    cur = db_helper.get_cursor()
    cur.execute("SELECT * FROM players WHERE id = ?", (player_id,))
    player_data = cur.fetchone()
    cur.close()

    if not player_data:
        flash("PES6 Player not found!", "danger")
        return redirect(url_for('pes6_game_teams'))

    basic_info = {
        'Name': player_data['player_name'],
        'Age': player_data['age'],
        'Height': player_data['height'],
        'Weight': player_data['weight'],
        'Nationality': player_data['nationality'],
        'Strong Foot': player_data['strong_foot'],
        'Favoured Side': player_data['favoured_side'],
        'Registered Position': player_data['registered_position'],
        'Games': 0,    # Added empty field
        'Assists': 0,  # Added empty field
        'Goals': 0     # Added empty field
    }

    club_name = None
    if player_data['club_id']:
        temp_cur = db_helper.get_cursor()
        temp_cur.execute("SELECT club_name FROM teams WHERE id = ?", (player_data['club_id'],))
        club_name_result = temp_cur.fetchone()
        if club_name_result:
            club_name = club_name_result[0]
        temp_cur.close()
    basic_info['Club'] = club_name

    financial_info = {
        'Salary': player_data['salary'],
        'Contract Years': player_data['contract_years_remaining'],
        'Market Value': player_data['market_value'],
        'Yearly Wage Rise': player_data['yearly_wage_rise']
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


    return render_template('pes6_player_details.html',
                           player=player_data,
                           basic_info=basic_info,
                           financial_info=financial_info, # Pass new financial_info dictionary
                           skills_numeric=skills_numeric,
                           positional_skills=positional_skills,
                           special_skills=special_skills)

# --- NEW ROUTES FOR TOOLS PAGE AND CSV DOWNLOAD ---
@app.route('/tools')
def tools():
    cur = db_helper.get_cursor()
    cur.execute("SELECT id, player_name FROM players ORDER BY player_name ASC")
    players = cur.fetchall()
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    teams = cur.fetchall()
    cur.close()
    return render_template('tools.html', players=players, teams=teams)

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
        df_original = pd.read_csv(original_csv_path, encoding='utf-8')
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
                    WHEN t.club_name IS NULL OR t.club_name = 'No Club' THEN ''
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
                # For missing columns, copy from original CSV data
                if col in df_original.columns:
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
            # Common encoding fixes
            text = str(text)
            text = text.replace('ï¿½', 'ã')  # Fix ã
            text = text.replace('ï¿½', 'ç')  # Fix ç
            text = text.replace('ï¿½', 'õ')  # Fix õ
            text = text.replace('ï¿½', 'á')  # Fix á
            text = text.replace('ï¿½', 'é')  # Fix é
            text = text.replace('ï¿½', 'í')  # Fix í
            text = text.replace('ï¿½', 'ó')  # Fix ó
            text = text.replace('ï¿½', 'ú')  # Fix ú
            text = text.replace('ï¿½', 'à')  # Fix à
            text = text.replace('ï¿½', 'è')  # Fix è
            text = text.replace('ï¿½', 'ì')  # Fix ì
            text = text.replace('ï¿½', 'ò')  # Fix ò
            text = text.replace('ï¿½', 'ù')  # Fix ù
            text = text.replace('ï¿½', 'â')  # Fix â
            text = text.replace('ï¿½', 'ê')  # Fix ê
            text = text.replace('ï¿½', 'î')  # Fix î
            text = text.replace('ï¿½', 'ô')  # Fix ô
            text = text.replace('ï¿½', 'û')  # Fix û
            return text
        
        # Apply encoding fixes to text columns
        for col in ['NAME', 'SHIRT_NAME', 'NATIONALITY']:
            if col in df_output.columns:
                df_output[col] = df_output[col].apply(fix_encoding)

        # Export with the original header
        output_filename = 'pe6_player_data_updated.csv'
        output_filepath = os.path.join(DOWNLOAD_FOLDER, output_filename)
        
        # Write the CSV with the original header
        df_output.to_csv(output_filepath, index=False, encoding='utf-8')

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
        JOIN team_players tp ON p.id = tp.player_id
        JOIN league_teams lt ON tp.team_id = lt.id
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
                JOIN team_players tp ON p.id = tp.player_id
                JOIN league_teams lt ON tp.team_id = lt.id
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
    # Get sender and receiver league_team ids
    cur.execute("SELECT id FROM league_teams WHERE user_id = ?", (offer['sender_id'],))
    sender_team = cur.fetchone()
    cur.execute("SELECT id FROM league_teams WHERE user_id = ?", (offer['receiver_id'],))
    recipient_team = cur.fetchone()
    if not sender_team or not recipient_team:
        cur.close()
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Teams not found for one of the users.'}), 400
        flash('Teams not found for one of the users.', 'danger')
        return redirect(url_for('inbox'))
    sender_team_id = sender_team['id']
    recipient_team_id = recipient_team['id']
    # Transfer players: offered_players to recipient, requested_players to sender
    offered_players = json.loads(offer['offered_players'])
    requested_players = json.loads(offer['requested_players'])
    # Remove offered players from sender, add to recipient
    for pid in offered_players:
        cur.execute("DELETE FROM team_players WHERE team_id = ? AND player_id = ?", (sender_team_id, pid))
        cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (recipient_team_id, pid))
    # Remove requested players from recipient, add to sender
    for pid in requested_players:
        cur.execute("DELETE FROM team_players WHERE team_id = ? AND player_id = ?", (recipient_team_id, pid))
        cur.execute("INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)", (sender_team_id, pid))
    # Update budgets
    cur.execute("SELECT budget FROM league_teams WHERE id = ?", (sender_team_id,))
    sender_budget = cur.fetchone()['budget']
    cur.execute("SELECT budget FROM league_teams WHERE id = ?", (recipient_team_id,))
    recipient_budget = cur.fetchone()['budget']
    new_sender_budget = sender_budget - offer['offered_money'] + offer['requested_money']
    new_recipient_budget = recipient_budget + offer['offered_money'] - offer['requested_money']
    cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_sender_budget, sender_team_id))
    cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_recipient_budget, recipient_team_id))
    # Mark offer as accepted
    cur.execute("UPDATE offers SET status = 'accepted' WHERE id = ?", (offer_id,))
    
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
        return jsonify({'success': True, 'updated_budget': new_recipient_budget, 'message': 'Offer accepted and transfer completed!'})
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

@app.route('/negotiate_with_cpu/<int:player_id>', methods=['POST'])
@login_required
def negotiate_with_cpu(player_id):
    data = request.get_json()
    action = data.get('action')
    current_deal = data.get('current_deal')
    user_team_players = data.get('user_team_players', [])  # List of dicts with at least 'id', 'NAME', 'Market Value'

    # Only check/add blacklist on the initial negotiation request
    if current_deal is None:
        # Check if player is blacklisted for this user
        if is_blacklisted(current_user.id, player_id):
            return jsonify({'error': 'This player is no longer available for negotiation with you.'}), 403
        # Blacklist the player as soon as negotiation is started (only on initial negotiation)
        add_to_blacklist(current_user.id, player_id)

    # Fetch player info from DB
    cur = db_helper.get_cursor()
    cur.execute("SELECT * FROM players WHERE id = ?", (player_id,))
    player = cur.fetchone()
    if not player:
        cur.close()
        return jsonify({'error': 'Player not found'}), 404
    market_value = player['market_value']
    player_name = player['player_name']
    selling_club_id = player['club_id']
    # Get selling club name
    club_name = None
    if selling_club_id:
        cur.execute("SELECT club_name FROM teams WHERE id = ?", (selling_club_id,))
        club_row = cur.fetchone()
        if club_row:
            club_name = club_row['club_name']
    # Get selling CPU league_team (if any)
    cpu_league_team_id = None
    cur.execute("SELECT id FROM league_teams WHERE team_name = ?", (club_name,))
    cpu_league_team = cur.fetchone()
    if cpu_league_team:
        cpu_league_team_id = cpu_league_team['id']
    else:
        # Create a CPU league team if missing (user_id=1 is the special CPU user)
        app.logger.info(f"Creating CPU league_team for club_name: {club_name}")
        cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (?, ?)", (1, club_name))
        db_helper.commit()
        cpu_league_team_id = cur.lastrowid
    # Get user's league_team
    cur = db_helper.get_cursor()
    cur.execute("SELECT id FROM league_teams WHERE user_id = ?", (current_user.id,))
    user_team_row = cur.fetchone()
    if not user_team_row:
        cur.close()
        return jsonify({'error': 'You do not manage a team.'}), 400
    user_league_team_id = user_team_row['id']

    # Initial negotiation step
    if not current_deal:
        initial_asking_price = int(market_value * random.uniform(1.25, 1.75))
        negotiation_prob = 0.75
        cur.close()
        return jsonify({
            'deal': {
                'cash_paid': initial_asking_price,
                'player_given': None,
                'cpu_player_given': None,
                'negotiation_prob': negotiation_prob,
                'club_name': club_name
            },
            'player_name': player_name,
            'market_value': market_value,
            'club_name': club_name,
            'step': 'initial'
        })

    # Accepting the deal
    if action == 'accept':
        # Don't create an offer - just return success for AJAX confirmation
        return jsonify({'success': True, 'message': 'Deal accepted! Please confirm the transfer.'})

    # Counter-offer logic (CPU responds)
    if action == 'counter':
        negotiation_prob = current_deal.get('negotiation_prob', 0.75)
        negotiation_prob = max(0, negotiation_prob - random.uniform(0.05, 0.15))
        if random.random() > negotiation_prob:
            cur.close()
            return jsonify({'deal': None, 'step': 'cpu_quit', 'message': 'The CPU has ended negotiations. They are firm on their price.'})
        cash_demand = current_deal.get('cash_paid', 0)
        player_demand = current_deal.get('player_given')
        player_demand_mv = player_demand.get('Market Value', 0) if player_demand else 0
        current_total_demand_value = cash_demand + player_demand_mv
        new_total_demand_value = int(current_total_demand_value * (1 - random.uniform(0.05, 0.15)))
        # Only sometimes ask for a player from user's team if any are available
        if user_team_players and random.random() < 0.5:
            # 1. Get CPU team position counts
            cpu_position_counts = {}
            if cpu_league_team_id:
                cur.execute("SELECT registered_position FROM players p JOIN team_players tp ON p.id = tp.player_id WHERE tp.team_id = ?", (cpu_league_team_id,))
                cpu_positions = [row['registered_position'] for row in cur.fetchall() if row['registered_position']]
                for pos in cpu_positions:
                    cpu_position_counts[pos] = cpu_position_counts.get(pos, 0) + 1
            # 2. Find the least common position(s)
            min_count = None
            lacking_positions = set()
            if cpu_position_counts:
                min_count = min(cpu_position_counts.values())
                lacking_positions = {pos for pos, count in cpu_position_counts.items() if count == min_count}
            # 3. Try to get a user player in a lacking position, else any user player
            lacking_position_players = [p for p in user_team_players if p['registered_position'] in lacking_positions] if lacking_positions else []
            if lacking_position_players:
                player_request = random.choice(lacking_position_players)
            else:
                player_request = random.choice(user_team_players)
            new_cash_demand = max(0, new_total_demand_value - player_request['Market Value'])
            cur.close()
            return jsonify({'deal': {'cash_paid': new_cash_demand, 'player_given': player_request, 'cpu_player_given': None, 'negotiation_prob': negotiation_prob, 'club_name': club_name}, 'step': 'cpu_counter'})
        # Otherwise, just lower cash
        cur.close()
        return jsonify({'deal': {'cash_paid': new_total_demand_value, 'player_given': None, 'cpu_player_given': None, 'negotiation_prob': negotiation_prob, 'club_name': club_name}, 'step': 'cpu_counter'})

    cur.close()
    return jsonify({'error': 'Invalid action'}), 400

@app.route('/get_team_players_full/<int:user_id>')
@login_required
def get_team_players_full(user_id):
    cur = db_helper.get_cursor()
    cur.execute("""
        SELECT p.id, p.player_name AS NAME, p.market_value AS `Market Value`, p.registered_position
        FROM players p
        JOIN team_players tp ON p.id = tp.player_id
        JOIN league_teams lt ON tp.team_id = lt.id
        WHERE lt.user_id = ?
        ORDER BY p.player_name ASC
    """, (user_id,))
    players = cur.fetchall()
    cur.close()
    return jsonify([dict(row) for row in players])

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
        
        # Update budgets
        cash_paid = current_deal.get('cash_paid', 0)
        if cash_paid != 0:
            cur.execute("SELECT budget FROM league_teams WHERE id = ?", (user_league_team_id,))
            user_budget = cur.fetchone()['budget']
            cur.execute("SELECT budget FROM league_teams WHERE id = ?", (cpu_league_team_id,))
            cpu_budget = cur.fetchone()['budget']
            
            new_user_budget = user_budget - cash_paid
            new_cpu_budget = cpu_budget + cash_paid
            
            cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_user_budget, user_league_team_id))
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
            'updated_budget': new_user_budget if cash_paid != 0 else None
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
    cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = 1 AND team_name != ?", (user_team_name,))
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
    # Generate CSV
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID', 'Player Name', 'Position', 'Age', 'Nationality', 'Salary', 'Contract Years', 'Market Value'])
    for p in players:
        writer.writerow([
            p['id'], p['player_name'], p['registered_position'], p['age'], p['nationality'], p['salary'], p['contract_years_remaining'], p['market_value']
        ])
    output = si.getvalue()
    si.close()
    return Response(
        output,
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
        
        # Update budgets
        if cash != 0:
            cur.execute("SELECT budget FROM league_teams WHERE id = ?", (user_team_id,))
            user_budget = cur.fetchone()['budget']
            cur.execute("SELECT budget FROM league_teams WHERE id = ?", (cpu_team_id,))
            cpu_budget = cur.fetchone()['budget']
            
            new_user_budget = user_budget + cash
            new_cpu_budget = cpu_budget - cash
            
            cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_user_budget, user_team_id))
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
            'updated_budget': new_user_budget if cash != 0 else None,
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

    # Update budgets as before
    cur.execute("SELECT budget FROM league_teams WHERE id = ?", (user_team_id,))
    user_budget = cur.fetchone()['budget']
    cur.execute("SELECT budget FROM league_teams WHERE id = ?", (cpu_team_id,))
    cpu_budget = cur.fetchone()['budget']
    
    old_user_budget = user_budget
    if 'offered_money' in offer and 'requested_money' in offer:
        new_user_budget = user_budget + offer['requested_money'] - offer['offered_money']
        new_cpu_budget = cpu_budget - offer['requested_money'] + offer['offered_money']
        if offer['offered_money'] > 0:
            asset_changes.append(f"✅ €{offer['offered_money']:,} received")
        if offer['requested_money'] > 0:
            asset_changes.append(f"❌ €{offer['requested_money']:,} paid")
    else:
        # CPU offer: user gets offer_amount
        new_user_budget = user_budget + offer['offer_amount']
        new_cpu_budget = cpu_budget - offer['offer_amount']
        asset_changes.append(f"✅ €{offer['offer_amount']:,} received")
    
    cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_user_budget, user_team_id))
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
        'updated_budget': new_user_budget,
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

    # Update budgets
    cur.execute("SELECT budget FROM league_teams WHERE id = ?", (user_team_id,))
    user_budget = cur.fetchone()['budget']
    cur.execute("SELECT budget FROM league_teams WHERE id = ?", (cpu_team_id,))
    cpu_budget = cur.fetchone()['budget']
    
    if 'offered_money' in offer and 'requested_money' in offer:
        new_user_budget = user_budget - offer['offered_money'] + offer['requested_money']
        new_cpu_budget = cpu_budget + offer['offered_money'] - offer['requested_money']
        if offer['offered_money'] > 0:
            asset_changes.append(f"❌ €{offer['offered_money']:,} paid")
        if offer['requested_money'] > 0:
            asset_changes.append(f"✅ €{offer['requested_money']:,} received")
    else:
        # CPU offer: user pays offer_amount
        new_user_budget = user_budget - offer['offer_amount']
        new_cpu_budget = cpu_budget + offer['offer_amount']
        asset_changes.append(f"❌ €{offer['offer_amount']:,} paid")
    
    cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_user_budget, user_team_id))
    cur.execute("UPDATE league_teams SET budget = ? WHERE id = ?", (new_cpu_budget, cpu_team_id))
    cur.execute("UPDATE offers SET status = 'accepted' WHERE id = ?", (offer_id,))
    db_helper.commit()
    cur.close()
    
    return jsonify({
        'success': True, 
        'message': 'Purchase confirmed and transfer completed!',
        'updated_budget': new_user_budget,
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

# --- Clear Blacklist Tool ---
@app.route('/clear_blacklist', methods=['POST'])
def clear_blacklist_route():
    clear_blacklist()
    flash('Blacklist cleared successfully!', 'success')
    return redirect(url_for('tools'))

# --- Blacklist Helper Functions ---
def add_to_blacklist(user_id, player_id):
    """Add a player to user's blacklist"""
    cur = db_helper.get_cursor()
    try:
        cur.execute("INSERT INTO blacklist (user_id, player_id) VALUES (?, ?)", (user_id, player_id))
        db_helper.commit()
        return True
    except Exception as e:
        # Player already blacklisted (UNIQUE constraint)
        return False
    finally:
        cur.close()

def is_blacklisted(user_id, player_id):
    """Check if a player is blacklisted for a user"""
    cur = db_helper.get_cursor()
    cur.execute("SELECT 1 FROM blacklist WHERE user_id = ? AND player_id = ?", (user_id, player_id))
    result = cur.fetchone()
    cur.close()
    return result is not None

def clear_blacklist():
    """Clear all blacklist entries"""
    cur = db_helper.get_cursor()
    cur.execute("DELETE FROM blacklist")
    db_helper.commit()
    cur.close()

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

def post_transfer_news(title, content, user_id=1):
    """
    Post transfer news to the blog.
    user_id=1 is the CPU user, used for system-generated news.
    """
    cur = db_helper.get_cursor()
    try:
        cur.execute("INSERT INTO posts (user_id, title, content, media_type, media_path) VALUES (?, ?, ?, 'none', NULL)",
                    (user_id, title, content))
        db_helper.commit()
        app.logger.info(f"Transfer news posted: {title}")
    except Exception as e:
        db_helper.get_connection().rollback()
        app.logger.error(f"Error posting transfer news: {e}")
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
        'offered_money': offer.get('offered_money', 0),
        'requested_money': offer.get('requested_money', 0),
        'offered_players': offered_players,
        'requested_players': requested_players,
        'is_cpu_offer': offer['offer_type'] == 'cpu'
    })

if __name__ == '__main__':
    # For local development
    # app.run(debug=True)

    # For production with Waitress (if you decide to use it manually)
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000)
