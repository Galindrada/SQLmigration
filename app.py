import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort, jsonify, Response
from flask_mysqldb import MySQL
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import MySQLdb.cursors
import pandas as pd
import json
import random
import time
import csv
from io import StringIO

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

mysql = MySQL(app)
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

# User model for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

    @staticmethod
    def get(user_id):
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, email FROM users WHERE id = %s", (user_id,))
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
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p.id, p.title, p.content, u.username, p.created_at, p.media_type, p.media_path
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC LIMIT 5
    """)
    recent_posts = cur.fetchall()
    cur.close()
    return render_template('index.html', recent_posts=recent_posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    pes6_teams_for_selection = cur.fetchall()
    cur.close()

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        selected_team_ids = request.form.getlist('selected_teams') # Get list of selected team IDs

        if len(selected_team_ids) != 1:
            flash('Please select exactly 1 team to manage.', 'danger')
            return render_template('register.html', teams=pes6_teams_for_selection, 
                                   old_username=username, old_email=email) # Pass back data

        new_user_id = None
        try:
            cur = mysql.connection.cursor()
            # Insert new user
            cur.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                        (username, email, hashed_password))
            mysql.connection.commit()
            new_user_id = cur.lastrowid # Get the ID of the newly created user

            pes6_team_id = int(selected_team_ids[0])
            # Get the name of the selected PES6 team
            cur.execute("SELECT club_name FROM teams WHERE id = %s", (pes6_team_id,))
            pes6_team_name_result = cur.fetchone()
            if not pes6_team_name_result:
                raise Exception(f"Selected PES6 team with ID {pes6_team_id} not found.")
            pes6_team_name = pes6_team_name_result[0]

            # Always ensure the user gets a team in league_teams and the roster is populated
            cur.execute("SELECT id FROM league_teams WHERE team_name = %s", (pes6_team_name,))
            league_team = cur.fetchone()
            if league_team:
                league_team_id = league_team[0]
                cur.execute("UPDATE league_teams SET user_id = %s WHERE id = %s", (new_user_id, league_team_id))
            else:
                cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (%s, %s)", (new_user_id, pes6_team_name))
                mysql.connection.commit()
                league_team_id = cur.lastrowid
            # Repopulate team_players for this team
            cur.execute("DELETE FROM team_players WHERE team_id = %s", (league_team_id,))
            cur.execute("SELECT id FROM players WHERE club_id = %s", (pes6_team_id,))
            players_in_pes6_team = cur.fetchall()
            if players_in_pes6_team:
                player_team_data = [(league_team_id, player[0]) for player in players_in_pes6_team]
                cur.executemany("INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)", player_team_data)
            mysql.connection.commit()

            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            mysql.connection.rollback()
            # If user was created but team creation failed, try to clean up user (optional, complex)
            if new_user_id:
                try:
                    cur.execute("DELETE FROM users WHERE id = %s", (new_user_id,))
                    mysql.connection.commit()
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

        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, password, email FROM users WHERE username = %s", (username,))
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
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p.id, p.title, p.content, u.username, p.created_at, p.media_type, p.media_path
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
    """)
    posts = cur.fetchall()
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

        cur = mysql.connection.cursor()
        try:
            cur.execute("INSERT INTO posts (user_id, title, content, media_type, media_path) VALUES (%s, %s, %s, %s, %s)",
                        (user_id, title, content, media_type, media_path))
            mysql.connection.commit()
            flash('Post created successfully!', 'success')
            return redirect(url_for('blog'))
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error creating post: {e}', 'danger')
        finally:
            cur.close()
    return render_template('create_post.html')

@app.route('/blog/post/<int:post_id>', methods=['GET', 'POST'])
def view_post(post_id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p.id, p.title, p.content, u.username, p.created_at, p.media_type, p.media_path
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.id = %s
    """, (post_id,))
    post = cur.fetchone()

    if not post:
        flash('Post not found.', 'danger')
        return redirect(url_for('blog'))

    cur.execute("""
        SELECT c.content, u.username, c.created_at
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.post_id = %s
        ORDER BY c.created_at ASC
    """, (post_id,))
    comments = cur.fetchall()
    cur.close()

    if request.method == 'POST' and current_user.is_authenticated:
        comment_content = request.form['comment_content']
        user_id = current_user.id

        if not comment_content:
            flash('Comment cannot be empty.', 'danger')
            return redirect(url_for('view_post', post_id=post_id))

        cur = mysql.connection.cursor()
        try:
            cur.execute("INSERT INTO comments (post_id, user_id, content) VALUES (%s, %s, %s)",
                        (post_id, user_id, comment_content))
            mysql.connection.commit()
            flash('Comment added successfully!', 'success')
            return redirect(url_for('view_post', post_id=post_id))
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error adding comment: {e}', 'danger')
        finally:
            cur.close()
    return render_template('view_post.html', post=post, comments=comments)


@app.route('/team_management')
@login_required
def team_management():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id, team_name, budget FROM league_teams WHERE user_id = %s", (current_user.id,))
    user_teams_meta = cur.fetchall() # Fetch all teams this user manages
    cur.close()

    managed_teams_data = []
    total_salaries_user_teams = 0 # Initialize total salaries for financial summary
    user_total_budget = 0

    for team_meta in user_teams_meta:
        team_id = team_meta['id']
        team_name = team_meta['team_name']
        team_budget = team_meta.get('budget', 0)
        user_total_budget += team_budget

        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor) # New cursor for player data
        # Fetch players for this specific team, including financial info
        cur.execute("""
            SELECT
                p.id, p.player_name, p.registered_position, p.salary, p.contract_years_remaining, p.market_value
            FROM players p
            JOIN team_players tp ON p.id = tp.player_id
            WHERE tp.team_id = %s
            ORDER BY p.player_name ASC
        """, (team_id,))
        team_players_roster = cur.fetchall()
        cur.close()

        # Sum salaries for this team
        team_salary_sum = sum(p.get('salary', 0) for p in team_players_roster if p.get('salary') is not None)
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
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(id) FROM league_teams WHERE user_id = %s", (current_user.id,))
    team_count = cur.fetchone()[0]
    cur.close()

    if team_count >= 2:
        flash('You can only manage a maximum of 1 team.', 'danger')
        return redirect(url_for('team_management'))

    team_name = request.form['team_name']
    user_id = current_user.id

    cur = mysql.connection.cursor()
    try:
        cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (%s, %s)",
                    (user_id, team_name))
        mysql.connection.commit()
        flash(f'Team "{team_name}" created successfully!', 'success')
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error creating team: {e}', 'danger')
    finally:
        cur.close()
    return redirect(url_for('team_management'))

@app.route('/team_management/add_player', methods=['POST'])
@login_required
def add_player_to_team():
    player_id = request.form['player_id'] # This player_id comes from a form field, assuming user picked from a list
    team_id = request.form['team_id'] # New: need to know which of the user's teams to add to

    cur = mysql.connection.cursor()
    # Verify the team_id belongs to the current user
    cur.execute("SELECT id FROM league_teams WHERE id = %s AND user_id = %s", (team_id, current_user.id))
    user_team_check = cur.fetchone()
    cur.close()

    if not user_team_check:
        flash('Invalid team selected for adding player.', 'danger')
        return redirect(url_for('team_management'))

    cur = mysql.connection.cursor()
    try:
        # Optional: Check if player is already in ANY of the user's teams, or a specific team
        # For this design, let's allow a player to be in only ONE of a user's teams
        cur.execute("SELECT tp.player_id FROM team_players tp JOIN league_teams lt ON tp.team_id = lt.id WHERE lt.user_id = %s AND tp.player_id = %s", (current_user.id, player_id))
        player_already_in_user_teams = cur.fetchone()
        if player_already_in_user_teams:
            flash("This player is already in one of your managed teams!", "warning")
            return redirect(url_for('team_management'))

        # Insert player into the specified team
        cur.execute("INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)",
                    (team_id, player_id))
        mysql.connection.commit()
        flash('Player added to your team!', 'success')
    except Exception as e:
            mysql.connection.rollback()
            flash(f'Error adding player: {e}', 'danger')
    finally:
            cur.close()
    return redirect(url_for('team_management'))

@app.route('/team_management/remove_player/<int:team_id>/<int:player_id>', methods=['POST'])
@login_required
def remove_player_from_team(team_id, player_id): # Team ID added to parameters
    # Verify the team_id belongs to the current user
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM league_teams WHERE id = %s AND user_id = %s", (team_id, current_user.id))
    user_team_check = cur.fetchone()
    cur.close()

    if not user_team_check:
        flash('Invalid team selected for removing player.', 'danger')
        return redirect(url_for('team_management'))

    cur = mysql.connection.cursor()
    try:
        cur.execute("DELETE FROM team_players WHERE team_id = %s AND player_id = %s",
                    (team_id, player_id))
        mysql.connection.commit()
        flash('Player removed from your team!', 'success')
    except Exception as e:
            mysql.connection.rollback()
            flash(f'Error removing player: {e}', 'danger')
    finally:
            cur.close()
    return redirect(url_for('team_management'))

# --- New Routes for PES6 Game Data ---

@app.route('/pes6_game_teams')
def pes6_game_teams():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, club_name FROM teams ORDER BY club_name ASC")
    game_teams = cur.fetchall()
    # Get all team names from league_teams that are managed by a real user (user_id != 1)
    cur.execute("SELECT team_name FROM league_teams WHERE user_id != 1")
    user_assigned_team_names = set(row[0] for row in cur.fetchall())
    cur.close()
    return render_template('pes6_teams.html', game_teams=game_teams, user_assigned_team_names=user_assigned_team_names)

@app.route('/pes6_game_teams/<int:team_id>')
def pes6_team_details(team_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT club_name FROM teams WHERE id = %s", (team_id,))
    team_name = cur.fetchone()
    if not team_name:
        flash("PES6 Team not found!", "danger")
        return redirect(url_for('pes6_game_teams'))
    team_name = team_name[0]

    cur.execute("""
        SELECT id, player_name, registered_position, age, height, strong_foot, attack
        FROM players
        WHERE club_id = %s
        ORDER BY player_name ASC
    """, (team_id,))
    players_in_team = cur.fetchall()
    cur.close()
    return render_template('pes6_team_details.html', team_name=team_name, players_in_team=players_in_team)


@app.route('/pes6_player/<int:player_id>')
def pes6_player_details(player_id):
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM players WHERE id = %s", (player_id,))
    player_data = cur.fetchone()
    cur.close()

    if not player_data:
        flash("PES6 Player not found!", "danger")
        return redirect(url_for('pes6_game_teams'))

    basic_info = {
        'Name': player_data.get('player_name'),
        'Age': player_data.get('age'),
        'Height': player_data.get('height'),
        'Weight': player_data.get('weight'),
        'Nationality': player_data.get('nationality'),
        'Strong Foot': player_data.get('strong_foot'),
        'Favoured Side': player_data.get('favoured_side'),
        'Registered Position': player_data.get('registered_position'),
        'Games': 0,    # Added empty field
        'Assists': 0,  # Added empty field
        'Goals': 0     # Added empty field
    }

    club_name = None
    if player_data.get('club_id'):
        temp_cur = mysql.connection.cursor()
        temp_cur.execute("SELECT club_name FROM teams WHERE id = %s", (player_data['club_id'],))
        club_name_result = temp_cur.fetchone()
        if club_name_result:
            club_name = club_name_result[0]
        temp_cur.close()
    basic_info['Club'] = club_name

    financial_info = {
        'Salary': player_data.get('salary'),
        'Contract Years': player_data.get('contract_years_remaining'),
        'Market Value': player_data.get('market_value'),
        'Yearly Wage Rise': player_data.get('yearly_wage_rise')
    }

    skills_numeric = {
        'Attack': player_data.get('attack'),
        'Defense': player_data.get('defense'),
        'Balance': player_data.get('balance'),
        'Stamina': player_data.get('stamina'),
        'Top Speed': player_data.get('top_speed'),
        'Acceleration': player_data.get('acceleration'),
        'Response': player_data.get('response'),
        'Agility': player_data.get('agility'),
        'Dribble Accuracy': player_data.get('dribble_accuracy'),
        'Dribble Speed': player_data.get('dribble_speed'),
        'Short Pass Accuracy': player_data.get('short_pass_accuracy'),
        'Short Pass Speed': player_data.get('short_pass_speed'),
        'Long Pass Accuracy': player_data.get('long_pass_accuracy'),
        'Long Pass Speed': player_data.get('long_pass_speed'),
        'Shot Accuracy': player_data.get('shot_accuracy'),
        'Shot Power': player_data.get('shot_power'),
        'Shot Technique': player_data.get('shot_technique'),
        'Free Kick Accuracy': player_data.get('free_kick_accuracy'),
        'Swerve': player_data.get('swerve'),
        'Heading': player_data.get('heading'),
        'Jump': player_data.get('jump'),
        'Technique': player_data.get('technique'),
        'Aggression': player_data.get('aggression'),
        'Mentality': player_data.get('mentality'),
        'Goal Keeping': player_data.get('goal_keeping'),
        'Team Work': player_data.get('team_work'),
        'Consistency': player_data.get('consistency'),
        'Condition / Fitness': player_data.get('condition_fitness'),
    }

    positional_skills = {
        'GK': player_data.get('gk'), 'CWP': player_data.get('cwp'), 'CBT': player_data.get('cbt'),
        'SB': player_data.get('sb'), 'DMF': player_data.get('dmf'), 'WB': player_data.get('wb'),
        'CMF': player_data.get('cmf'), 'SMF': player_data.get('smf'), 'AMF': player_data.get('amf'),
        'WF': player_data.get('wf'), 'SS': player_data.get('ss'), 'CF': player_data.get('cf')
    }

    special_skills = {
        'Dribbling': player_data.get('dribbling_skill'),
        'Tactical Dribble': player_data.get('tactical_dribble'),
        'Positioning': player_data.get('positioning'),
        'Reaction': player_data.get('reaction'),
        'Playmaking': player_data.get('playmaking'),
        'Passing': player_data.get('passing'),
        'Scoring': player_data.get('scoring'),
        '1-on-1 Scoring': player_data.get('one_one_scoring'),
        'Post Player': player_data.get('post_player'),
        'Lines': player_data.get('lines'),
        'Middle Shooting': player_data.get('middle_shooting'),
        'Side': player_data.get('side'),
        'Centre': player_data.get('centre'),
        'Penalties': player_data.get('penalties'),
        '1-Touch Pass': player_data.get('one_touch_pass'),
        'Outside': player_data.get('outside'),
        'Marking': player_data.get('marking'),
        'Sliding': player_data.get('sliding'),
        'Covering': player_data.get('covering'),
        'D-Line Control': player_data.get('d_line_control'),
        'Penalty Stopper': player_data.get('penalty_stopper'),
        '1-on-1 Stopper': player_data.get('one_on_one_stopper'),
        'Long Throw': player_data.get('long_throw'),
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
    return render_template('tools.html')

@app.route('/download_updated_csv')
@login_required # Often good to require login for tools/downloads
def download_updated_csv():
    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        # Fetch all player data, including financial info
        cur.execute("""
            SELECT
                p.id, p.player_name, p.shirt_name, t.club_name AS club_team_raw,
                p.registered_position, p.age, p.height, p.weight, p.nationality,
                p.strong_foot, p.favoured_side, p.gk, p.cwp, p.cbt, p.sb, p.dmf, p.wb,
                p.cmf, p.smf, p.amf, p.wf, p.ss, p.cf, p.attack, p.defense, p.balance,
                p.stamina, p.top_speed, p.acceleration, p.response, p.agility,
                p.dribble_accuracy, p.dribble_speed, p.short_pass_accuracy,
                p.short_pass_speed, p.long_pass_accuracy, p.long_pass_speed,
                p.shot_accuracy, p.shot_power, p.shot_technique,
                p.free_kick_accuracy, p.swerve, p.heading, p.jump, p.technique,
                p.aggression, p.mentality, p.goal_keeping, p.team_work, p.consistency,
                p.condition_fitness, p.dribbling_skill, p.tactical_dribble, p.positioning,
                p.reaction, p.playmaking, p.passing, p.scoring, p.one_one_scoring,
                p.post_player, p.lines, p.middle_shooting, p.side, p.centre, p.penalties,
                p.one_touch_pass, p.outside, p.marking, p.sliding, p.covering,
                p.d_line_control, p.penalty_stopper, p.one_on_one_stopper, p.long_throw,
                p.injury_tolerance, p.dribble_style, p.free_kick_style, p.pk_style,
                p.drop_kick_style, p.skin_color, p.face_type, p.preset_face_number,
                p.head_width, p.neck_length, p.neck_width, p.shoulder_height,
                p.shoulder_width, p.chest_measurement, p.waist_circumference,
                p.arm_circumference, p.leg_circumference, p.calf_circumference,
                p.leg_length, p.wristband, p.wristband_color, p.international_number,
                p.classic_number, p.club_number,
                p.salary, p.contract_years_remaining, p.market_value, p.yearly_wage_rise
            FROM players p
            LEFT JOIN teams t ON p.club_id = t.id
            ORDER BY p.id
        """)
        players_data = cur.fetchall()
        cur.close()

        if not players_data:
            flash("No player data available to export.", "warning")
            return redirect(url_for('tools'))

        # Define the desired column order and original CSV headers
        csv_header_map = {
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
            'weak_foot_accuracy': 'WEAK FOOT ACCURACY',
            'weak_foot_frequency': 'WEAK FOOT FREQUENCY',
            'attack': 'ATTACK', 'defense': 'DEFENSE', 'balance': 'BALANCE',
            'stamina': 'STAMINA', 'top_speed': 'TOP SPEED', 'acceleration': 'ACCELERATION',
            'response': 'RESPONSE', 'agility': 'AGILITY', 'dribble_accuracy': 'DRIBBLE ACCURACY',
            'dribble_speed': 'DRIBBLE SPEED', 'short_pass_accuracy': 'SHORT PASS ACCURACY',
            'short_pass_speed': 'SHORT PASS SPEED', 'long_pass_accuracy': 'LONG PASS ACCURACY',
            'long_pass_speed': 'LONG PASS SPEED', 'shot_accuracy': 'SHOT ACCURACY',
            'shot_power': 'SHOT POWER', 'shot_technique': 'SHOT TECHNIQUE',
            'free_kick_accuracy': 'FREE KICK ACCURACY', 'swerve': 'SWERVE', 'heading': 'HEADING',
            'jump': 'JUMP', 'technique': 'TECHNIQUE', 'aggression': 'AGGRESSION',
            'mentality': 'MENTALITY', 'goal_keeping': 'GOAL KEEPING', 'team_work': 'TEAM WORK',
            'consistency': 'CONSISTENCY', 'condition_fitness': 'CONDITION / FITNESS',
            'dribbling_skill': 'DRIBBLING', 'tactical_dribble': 'TACTIAL DRIBBLE',
            'positioning': 'POSITIONING', 'reaction': 'REACTION', 'playmaking': 'PLAYMAKING',
            'passing': 'PASSING', 'scoring': 'SCORING', 'one_one_scoring': '1-1 SCORING',
            'post_player': 'POST PLAYER', 'lines': 'LINES', 'middle_shooting': 'MIDDLE SHOOTING',
            'side': 'SIDE', 'centre': 'CENTRE', 'penalties': 'PENALTIES',
            'one_touch_pass': '1-TOUCH PASS', 'outside': 'OUTSIDE', 'marking': 'MARKING',
            'sliding': 'SLIDING', 'covering': 'COVERING', 'd_line_control': 'D-LINE CONTROL',
            'penalty_stopper': 'PENALTY STOPPER', 'one_on_one_stopper': '1-ON-1 STOPPER',
            'long_throw': 'LONG THROW', 'injury_tolerance': 'INJURY TOLERANCE',
            'dribble_style': 'DRIBBLE STYLE', 'free_kick_style': 'FREE KICK STYLE',
            'pk_style': 'PK STYLE', 'drop_kick_style': 'DROP KICK STYLE',
            'age': 'AGE', 'weight': 'WEIGHT', 'nationality': 'NATIONALITY',
            'skin_color': 'SKIN COLOR', 'face_type': 'FACE TYPE', 'preset_face_number': 'PRESET FACE NUMBER',
            'head_width': 'HEAD WIDTH', 'neck_length': 'NECK LENGTH', 'neck_width': 'NECK WIDTH',
            'shoulder_height': 'SHOULDER HEIGHT', 'shoulder_width': 'SHOULDER WIDTH',
            'chest_measurement': 'CHEST MEASUREMENT', 'waist_circumference': 'WAIST CIRCUMFERENCE',
            'arm_circumference': 'ARM CIRCUMFERENCE', 'leg_circumference': 'LEG CIRCUMFERENCE',
            'calf_circumference': 'CALF CIRCUMFERENCE', 'leg_length': 'LEG LENGTH',
            'wristband': 'WRISTBAND', 'wristband_color': 'WRISTBAND COLOR',
            'international_number': 'INTERNATIONAL NUMBER', 'classic_number': 'CLASSIC NUMBER',
            'club_number': 'CLUB NUMBER',
            'club_team_raw': 'CLUB TEAM', # Ensure this maps back to original 'CLUB TEAM'
            # New financial fields
            'salary': 'SALARY',
            'contract_years_remaining': 'CONTRACT YEARS REMAINING',
            'market_value': 'MARKET VALUE',
            'yearly_wage_rise': 'YEARLY WAGE RISE'
        }

        df_players = pd.DataFrame(players_data)

        current_to_desired_map = {sql_col: csv_header_map[sql_col] for sql_col in csv_header_map if sql_col in df_players.columns}
        df_players_output = df_players.rename(columns=current_to_desired_map)

        # Correct the list of original CSV headers provided (100 headers)
        original_csv_headers_exact = [
            'ID', 'NAME', 'SHIRT_NAME', 'GK  0', 'CWP  2', 'CBT  3', 'SB  4', 'DMF  5', 'WB  6', 'CMF  7', 'SMF  8', 'AMF  9', 'WF 10', 'SS  11', 'CF  12', 'REGISTERED POSITION', 'HEIGHT', 'STRONG FOOT', 'FAVOURED SIDE', 'WEAK FOOT ACCURACY', 'WEAK FOOT FREQUENCY', 'ATTACK', 'DEFENSE', 'BALANCE', 'STAMINA', 'TOP SPEED', 'ACCELERATION', 'RESPONSE', 'AGILITY', 'DRIBBLE ACCURACY', 'DRIBBLE SPEED', 'SHORT PASS ACCURACY', 'SHORT PASS SPEED', 'LONG PASS ACCURACY', 'LONG PASS SPEED', 'SHOT ACCURACY', 'SHOT POWER', 'SHOT TECHNIQUE', 'FREE KICK ACCURACY', 'SWERVE', 'HEADING', 'JUMP', 'TECHNIQUE', 'AGGRESSION', 'MENTALITY', 'GOAL KEEPING', 'TEAM WORK', 'CONSISTENCY', 'CONDITION / FITNESS', 'DRIBBLING', 'TACTIAL DRIBBLE', 'POSITIONING', 'REACTION', 'PLAYMAKING', 'PASSING', 'SCORING', '1-1 SCORING', 'POST PLAYER', 'LINES', 'MIDDLE SHOOTING', 'SIDE', 'CENTRE', 'PENALTIES', '1-TOUCH PASS', 'OUTSIDE', 'MARKING', 'SLIDING', 'COVERING', 'D-LINE CONTROL', 'PENALTY STOPPER', '1-ON-1 STOPPER', 'LONG THROW', 'INJURY TOLERANCE', 'DRIBBLE STYLE', 'FREE KICK STYLE', 'PK STYLE', 'DROP KICK STYLE', 'AGE', 'WEIGHT', 'NATIONALITY', 'SKIN COLOR', 'FACE TYPE', 'PRESET FACE NUMBER', 'HEAD WIDTH', 'NECK LENGTH', 'NECK WIDTH', 'SHOULDER HEIGHT', 'SHOULDER WIDTH', 'CHEST MEASUREMENT', 'WAIST CIRCUMFERENCE', 'ARM CIRCUMFERENCE', 'LEG CIRCUMFERENCE', 'CALF CIRCUMFERENCE', 'LEG LENGTH', 'WRISTBAND', 'WRISTBAND COLOR', 'INTERNATIONAL NUMBER', 'CLASSIC NUMBER', 'CLUB TEAM', 'CLUB NUMBER'
        ]
        
        # Append new financial headers to the exact original list
        financial_headers = ['SALARY', 'CONTRACT YEARS REMAINING', 'MARKET VALUE', 'YEARLY WAGE RISE']
        final_column_order = original_csv_headers_exact + financial_headers

        df_players_output = df_players_output.reindex(columns=final_column_order)

        for col in df_players_output.columns:
            if df_players_output[col].dtype == 'object':
                df_players_output[col] = df_players_output[col].fillna('')
            else:
                df_players_output[col] = df_players_output[col].fillna(0)

        output_filename = 'pe6_player_data_updated.csv'
        output_filepath = os.path.join(DOWNLOAD_FOLDER, output_filename)

        df_players_output.to_csv(output_filepath, index=False, encoding='utf-8')

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
#     cur = mysql.connection.cursor()
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
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT m.*, u.username AS sender_username
        FROM messages m
        LEFT JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = %s
        ORDER BY m.created_at DESC
    """, (current_user.id,))
    messages = cur.fetchall()
    # Fetch offers for this user
    cur.execute("""
        SELECT o.*, u.username AS sender_username
        FROM offers o
        JOIN users u ON o.sender_id = u.id
        WHERE o.recipient_id = %s
        ORDER BY o.created_at DESC
    """, (current_user.id,))
    offers = cur.fetchall()
    # Parse JSON fields and fetch player names for template
    for offer in offers:
        offer['offered_players'] = json.loads(offer['offered_players'])
        offer['requested_players'] = json.loads(offer['requested_players'])
        # Fetch player names for both sides
        if offer['offered_players']:
            cur.execute("SELECT id, player_name FROM players WHERE id IN %s", (tuple(offer['offered_players']),))
            offer['offered_player_names'] = [row['player_name'] for row in cur.fetchall()]
        else:
            offer['offered_player_names'] = []
        if offer['requested_players']:
            cur.execute("SELECT id, player_name FROM players WHERE id IN %s", (tuple(offer['requested_players']),))
            offer['requested_player_names'] = [row['player_name'] for row in cur.fetchall()]
    cur.close()
    return render_template('inbox.html', messages=messages, offers=offers)

@app.route('/inbox/<int:msg_id>')
@login_required
def view_message(msg_id):
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM messages WHERE id = %s AND recipient_id = %s", (msg_id, current_user.id))
    message = cur.fetchone()
    if not message:
        cur.close()
        abort(404)
    # Mark as read if not already
    if not message['is_read']:
        cur2 = mysql.connection.cursor()
        cur2.execute("UPDATE messages SET is_read = TRUE WHERE id = %s", (msg_id,))
        mysql.connection.commit()
        cur2.close()
    sender_username = None
    if message['type'] == 'user' and message['sender_id']:
        cur.execute("SELECT username FROM users WHERE id = %s", (message['sender_id'],))
        sender = cur.fetchone()
        if sender:
            sender_username = sender['username']
    cur.close()
    return render_template('view_message.html', message=message, sender_username=sender_username)

@app.route('/inbox/send', methods=['GET', 'POST'])
@login_required
def send_message():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id, username FROM users WHERE id != %s ORDER BY username ASC", (current_user.id,))
    users = cur.fetchall()
    cur.close()
    subject = ''
    body = ''
    selected_recipient_id = None
    reply_to = request.args.get('reply_to')
    # If replying, pre-fill subject/body
    if reply_to:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT * FROM messages WHERE id = %s AND recipient_id = %s", (reply_to, current_user.id))
        orig = cur.fetchone()
        cur.close()
        if orig:
            subject = 'Re: ' + orig['subject']
            selected_recipient_id = orig['sender_id']
    if request.method == 'POST':
        recipient_id = request.form['recipient_id']
        subject = request.form['subject']
        body = request.form['body']
        if not recipient_id or not subject or not body:
            flash('All fields are required.', 'danger')
        else:
            cur = mysql.connection.cursor()
            cur.execute("INSERT INTO messages (sender_id, recipient_id, subject, body, type) VALUES (%s, %s, %s, %s, 'user')",
                        (current_user.id, recipient_id, subject, body))
            mysql.connection.commit()
            cur.close()
            flash('Message sent!', 'success')
            return redirect(url_for('inbox'))
    return render_template('send_message.html', users=users, subject=subject, body=body, selected_recipient_id=selected_recipient_id)

@app.route('/get_team_players/<int:user_id>')
@login_required
def get_team_players(user_id):
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT p.id, p.player_name FROM players p
        JOIN team_players tp ON p.id = tp.player_id
        JOIN league_teams lt ON tp.team_id = lt.id
        WHERE lt.user_id = %s
        ORDER BY p.player_name ASC
    """, (user_id,))
    players = cur.fetchall()
    cur.close()
    return jsonify(players)

@app.route('/send_offer', methods=['GET', 'POST'])
@login_required
def send_offer():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id, username FROM users WHERE id != %s ORDER BY username ASC", (current_user.id,))
    users = cur.fetchall()
    cur.execute("""
        SELECT p.id, p.player_name FROM players p
        JOIN team_players tp ON p.id = tp.player_id
        JOIN league_teams lt ON tp.team_id = lt.id
        WHERE lt.user_id = %s
        ORDER BY p.player_name ASC
    """, (current_user.id,))
    my_players = cur.fetchall()
    recipient_players = []
    selected_recipient_id = request.form.get('recipient_id') if request.method == 'POST' else request.args.get('recipient_id')
    if selected_recipient_id:
        try:
            selected_recipient_id_int = int(selected_recipient_id)
            cur.execute("""
                SELECT p.id, p.player_name FROM players p
                JOIN team_players tp ON p.id = tp.player_id
                JOIN league_teams lt ON tp.team_id = lt.id
                WHERE lt.user_id = %s
                ORDER BY p.player_name ASC
            """, (selected_recipient_id_int,))
            recipient_players = cur.fetchall()
        except ValueError:
            recipient_players = []
    cur.close()

    if request.method == 'POST':
        recipient_id = request.form['recipient_id']
        offered_players = request.form.getlist('offered_players')
        offered_money = request.form.get('offered_money', 0)
        requested_players = request.form.getlist('requested_players')
        requested_money = request.form.get('requested_money', 0)
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO offers (sender_id, recipient_id, offered_players, offered_money, requested_players, requested_money)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            current_user.id,
            recipient_id,
            json.dumps([int(pid) for pid in offered_players]),
            int(offered_money),
            json.dumps([int(pid) for pid in requested_players]),
            int(requested_money)
        ))
        mysql.connection.commit()
        cur.close()
        flash('Offer sent!', 'success')
        return redirect(url_for('inbox'))

    return render_template('send_offer.html', users=users, my_players=my_players, recipient_players=recipient_players, selected_recipient_id=selected_recipient_id)

@app.route('/offer/<int:offer_id>/accept', methods=['POST'])
@login_required
def accept_offer(offer_id):
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    # Get offer details
    cur.execute("SELECT * FROM offers WHERE id = %s AND recipient_id = %s AND status = 'pending'", (offer_id, current_user.id))
    offer = cur.fetchone()
    if not offer:
        cur.close()
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Offer not found or already handled.'}), 404
        flash('Offer not found or already handled.', 'danger')
        return redirect(url_for('inbox'))
    # Get sender and recipient league_team ids
    cur.execute("SELECT id FROM league_teams WHERE user_id = %s", (offer['sender_id'],))
    sender_team = cur.fetchone()
    cur.execute("SELECT id FROM league_teams WHERE user_id = %s", (offer['recipient_id'],))
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
        cur.execute("DELETE FROM team_players WHERE team_id = %s AND player_id = %s", (sender_team_id, pid))
        cur.execute("INSERT IGNORE INTO team_players (team_id, player_id) VALUES (%s, %s)", (recipient_team_id, pid))
    # Remove requested players from recipient, add to sender
    for pid in requested_players:
        cur.execute("DELETE FROM team_players WHERE team_id = %s AND player_id = %s", (recipient_team_id, pid))
        cur.execute("INSERT IGNORE INTO team_players (team_id, player_id) VALUES (%s, %s)", (sender_team_id, pid))
    # Update budgets
    cur.execute("SELECT budget FROM league_teams WHERE id = %s", (sender_team_id,))
    sender_budget = cur.fetchone()['budget']
    cur.execute("SELECT budget FROM league_teams WHERE id = %s", (recipient_team_id,))
    recipient_budget = cur.fetchone()['budget']
    new_sender_budget = sender_budget - offer['offered_money'] + offer['requested_money']
    new_recipient_budget = recipient_budget + offer['offered_money'] - offer['requested_money']
    cur.execute("UPDATE league_teams SET budget = %s WHERE id = %s", (new_sender_budget, sender_team_id))
    cur.execute("UPDATE league_teams SET budget = %s WHERE id = %s", (new_recipient_budget, recipient_team_id))
    # Mark offer as accepted
    cur.execute("UPDATE offers SET status = 'accepted' WHERE id = %s", (offer_id,))
    mysql.connection.commit()
    cur.close()
    # --- Daily Mail blog post for user-to-user deals ---
    try:
        # Fetch team names
        cur2 = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur2.execute("SELECT team_name FROM league_teams WHERE id = %s", (sender_team_id,))
        sender_team_name = cur2.fetchone()['team_name']
        cur2.execute("SELECT team_name FROM league_teams WHERE id = %s", (recipient_team_id,))
        recipient_team_name = cur2.fetchone()['team_name']
        # Fetch player names
        offered_player_names = []
        if offered_players:
            cur2.execute("SELECT player_name FROM players WHERE id IN %s", (tuple(offered_players),))
            offered_player_names = [row['player_name'] for row in cur2.fetchall()]
        requested_player_names = []
        if requested_players:
            cur2.execute("SELECT player_name FROM players WHERE id IN %s", (tuple(requested_players),))
            requested_player_names = [row['player_name'] for row in cur2.fetchall()]
        # Compose summary
        summary = f"Daily Mail: Transfer agreed between {sender_team_name} and {recipient_team_name}. "
        if offered_player_names:
            summary += f"{sender_team_name} sends: {', '.join(offered_player_names)}. "
        if offer['offered_money']:
            summary += f"+ €{offer['offered_money']:,} cash. "
        if requested_player_names:
            summary += f"{recipient_team_name} sends: {', '.join(requested_player_names)}. "
        if offer['requested_money']:
            summary += f"+ €{offer['requested_money']:,} cash. "
        summary += "The negotiation is pending ultimate details."
        cur2.execute("INSERT INTO posts (user_id, title, content, media_type) VALUES (%s, %s, %s, %s)", (1, 'Daily Mail Transfer', summary, 'none'))
        mysql.connection.commit()
        cur2.close()
    except Exception as e:
        app.logger.error(f'Error creating Daily Mail post for user-to-user deal: {str(e)}', exc_info=True)
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'updated_budget': new_recipient_budget, 'message': 'Offer accepted and transfer completed!'})
    flash('Offer accepted and transfer completed!', 'success')
    return redirect(url_for('inbox'))

@app.route('/offer/<int:offer_id>/reject', methods=['POST'])
@login_required
def reject_offer(offer_id):
    cur = mysql.connection.cursor()
    cur.execute("UPDATE offers SET status = 'rejected' WHERE id = %s AND recipient_id = %s", (offer_id, current_user.id))
    mysql.connection.commit()
    cur.close()
    flash('Offer rejected.', 'info')
    return redirect(url_for('inbox'))

@app.route('/negotiate_with_cpu/<int:player_id>', methods=['POST'])
def negotiate_with_cpu(player_id):
    data = request.get_json()
    action = data.get('action')
    current_deal = data.get('current_deal')
    user_team_players = data.get('user_team_players', [])  # List of dicts with at least 'id', 'NAME', 'Market Value'

    # Fetch player info from DB
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM players WHERE id = %s", (player_id,))
    player = cur.fetchone()
    if not player:
        cur.close()
        return jsonify({'error': 'Player not found'}), 404
    market_value = player.get('market_value', 0)
    player_name = player.get('player_name', 'Unknown')
    selling_club_id = player.get('club_id')
    # Get selling club name
    club_name = None
    if selling_club_id:
        cur.execute("SELECT club_name FROM teams WHERE id = %s", (selling_club_id,))
        club_row = cur.fetchone()
        if club_row:
            club_name = club_row['club_name']
    # Get selling CPU league_team (if any)
    cpu_league_team_id = None
    cur.execute("SELECT id FROM league_teams WHERE team_name = %s", (club_name,))
    cpu_league_team = cur.fetchone()
    if cpu_league_team:
        cpu_league_team_id = cpu_league_team['id']
    else:
        # Create a CPU league team if missing (user_id=1 is the special CPU user)
        app.logger.info(f"Creating CPU league_team for club_name: {club_name}")
        cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (%s, %s)", (1, club_name))
        mysql.connection.commit()
        cpu_league_team_id = cur.lastrowid
    # Get user's league_team
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id FROM league_teams WHERE user_id = %s", (current_user.id,))
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
        try:
            # Compose offer details
            cash_paid = current_deal.get('cash_paid', 0)
            player_given = current_deal.get('player_given')
            cpu_player_given = current_deal.get('cpu_player_given')
            # Prepare offered/requested players for the offer
            offered_players = []
            if cpu_player_given:
                offered_players.append(cpu_player_given.get('id'))
            offered_players.append(player_id)  # The main player CPU is offering
            requested_players = []
            if player_given:
                requested_players.append(player_given.get('id'))
            # Insert offer into offers table (CPU user_id=1)
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO offers (sender_id, recipient_id, offered_players, offered_money, requested_players, requested_money)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                1,  # CPU user
                current_user.id,
                json.dumps([pid for pid in offered_players if pid]),
                0,  # CPU is not offering money
                json.dumps([pid for pid in requested_players if pid]),
                cash_paid  # User pays this to CPU
            ))
            # Compose summary for blog
            cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            cur.execute("SELECT team_name FROM league_teams WHERE user_id = %s", (current_user.id,))
            user_team_row = cur.fetchone()
            user_team_name = user_team_row['team_name'] if user_team_row else 'your team'
            summary = f"Daily Mail: {player_name} has been transferred from {club_name} to {user_team_name} for €{cash_paid:,.0f}. The negotiation is pending ultimate details."
            if player_given:
                summary += f", with {player_given.get('NAME')} going the other way."
            if cpu_player_given:
                summary += f" ({club_name} also included {cpu_player_given.get('NAME')})"
            summary += "."
            cur.execute("INSERT INTO posts (user_id, title, content, media_type) VALUES (%s, %s, %s, %s)", (1, 'Daily Mail Transfer', summary, 'none'))
            mysql.connection.commit()
            cur.close()
            return jsonify({'success': True, 'message': 'The Offer is on your mail for acceptance.'})
        except Exception as e:
            app.logger.error(f'Exception in accept deal: {str(e)}', exc_info=True)
            mysql.connection.rollback()
            cur.close()
            return jsonify({'error': f'Error creating offer: {str(e)}'}), 500

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
                cur.execute("SELECT registered_position FROM players p JOIN team_players tp ON p.id = tp.player_id WHERE tp.team_id = %s", (cpu_league_team_id,))
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
            lacking_position_players = [p for p in user_team_players if p.get('registered_position') in lacking_positions] if lacking_positions else []
            if lacking_position_players:
                player_request = random.choice(lacking_position_players)
            else:
                player_request = random.choice(user_team_players)
            new_cash_demand = max(0, new_total_demand_value - player_request.get('Market Value', 0))
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
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT p.id, p.player_name AS NAME, p.market_value AS `Market Value`, p.registered_position
        FROM players p
        JOIN team_players tp ON p.id = tp.player_id
        JOIN league_teams lt ON tp.team_id = lt.id
        WHERE lt.user_id = %s
        ORDER BY p.player_name ASC
    """, (user_id,))
    players = cur.fetchall()
    cur.close()
    return jsonify(players)

@app.route('/select_team', methods=['GET', 'POST'])
@login_required
def select_team():
    # Only allow if user has no team
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT COUNT(*) as count FROM league_teams WHERE user_id = %s", (current_user.id,))
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
        cur.execute("SELECT club_name FROM teams WHERE id = %s", (selected_team_id,))
        team_row = cur.fetchone()
        if not team_row:
            flash('Selected team not found.', 'danger')
            return render_template('team_management.html', managed_teams=[], available_teams=available_teams, coach_username=current_user.username, total_budget_display=450000000, total_salaries_user_teams=0, free_cap_user_teams=450000000)
        team_name = team_row['club_name']
        cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (%s, %s)", (current_user.id, team_name))
        mysql.connection.commit()
        new_league_team_id = cur.lastrowid
        # Populate roster
        cur.execute("SELECT id FROM players WHERE club_id = %s", (selected_team_id,))
        players_in_team = cur.fetchall()
        if players_in_team:
            player_team_data = [(new_league_team_id, player['id']) for player in players_in_team]
            cur.executemany("INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)", player_team_data)
            mysql.connection.commit()
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
    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        # Get selling club name and league_team ids
        cur.execute("SELECT * FROM players WHERE id = %s", (player_id,))
        player = cur.fetchone()
        if not player:
            cur.close()
            return jsonify({'error': 'Player not found'}), 404
        club_name = None
        if player.get('club_id'):
            cur.execute("SELECT club_name FROM teams WHERE id = %s", (player['club_id'],))
            club_row = cur.fetchone()
            if club_row:
                club_name = club_row['club_name']
        cpu_league_team_id = None
        cur.execute("SELECT id FROM league_teams WHERE team_name = %s", (club_name,))
        cpu_league_team = cur.fetchone()
        if cpu_league_team:
            cpu_league_team_id = cpu_league_team['id']
        else:
            cur.execute("INSERT INTO league_teams (user_id, team_name) VALUES (%s, %s)", (1, club_name))
            mysql.connection.commit()
            cpu_league_team_id = cur.lastrowid
        cur.execute("SELECT id FROM league_teams WHERE user_id = %s", (current_user.id,))
        user_league_team = cur.fetchone()
        if not user_league_team:
            cur.close()
            return jsonify({'error': 'You do not manage a team.'}), 400
        user_league_team_id = user_league_team['id']
        # Transfer the main player from CPU to user
        cur.execute("DELETE FROM team_players WHERE player_id = %s", (player_id,))
        cur.execute("INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)", (user_league_team_id, player_id))
        # If user gives a player, transfer from user to CPU
        player_given = current_deal.get('player_given')
        if player_given:
            given_id = player_given.get('id')
            if not given_id:
                cur.close()
                return jsonify({'error': 'No player ID found for player_given.'}), 400
            cur.execute("DELETE FROM team_players WHERE player_id = %s", (given_id,))
            cur.execute("INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)", (cpu_league_team_id, given_id))
        # If CPU gives a player, transfer from CPU to user
        cpu_player_given = current_deal.get('cpu_player_given')
        if cpu_player_given:
            cpu_given_id = cpu_player_given.get('id')
            if not cpu_given_id:
                cur.close()
                return jsonify({'error': 'No player ID found for cpu_player_given.'}), 400
            cur.execute("DELETE FROM team_players WHERE player_id = %s", (cpu_given_id,))
            cur.execute("INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)", (user_league_team_id, cpu_given_id))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True, 'message': 'Transfer confirmed and players swapped.'})
    except Exception as e:
        mysql.connection.rollback()
        cur.close()
        return jsonify({'error': f'Error confirming transfer: {str(e)}'}), 500

@app.route('/sell_player/<int:player_id>', methods=['POST'])
@login_required
def sell_player(player_id):
    # Fetch player info
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM players WHERE id = %s", (player_id,))
    player = cur.fetchone()
    if not player:
        cur.close()
        return jsonify({'error': 'Player not found'}), 404
    player_name = player.get('player_name', 'Unknown')
    market_value = player.get('market_value', 0)
    salary = player.get('salary', 0)
    age = player.get('age', 0)
    # Get user's team
    cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = %s", (current_user.id,))
    user_team = cur.fetchone()
    if not user_team:
        cur.close()
        return jsonify({'error': 'You do not manage a team.'}), 400
    user_team_id = user_team['id']
    user_team_name = user_team['team_name']
    # Get all possible CPU clubs (not user-managed)
    cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = 1 AND team_name != %s", (user_team_name,))
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
        cur.execute("SELECT id FROM teams WHERE club_name = %s", (cpu_team_name,))
        team_row = cur.fetchone()
        club_id = team_row['id'] if team_row else None
        # Generate initial offer (cash or swap)
        bidding_club_squad = []
        if club_id:
            cur.execute("SELECT id, player_name, market_value FROM players WHERE club_id = %s", (club_id,))
            bidding_club_squad = cur.fetchall()
        target_offer_value = int(market_value * random.uniform(0.25, 0.65))
        offer = {'proposal_id': idx+1, 'cpu_team': cpu_team_name, 'cash': target_offer_value, 'player_swap': None}
        # 70% chance of player swap if squad available
        if bidding_club_squad and random.random() < 0.7:
            # Allow swaps for players up to 120% of the offer value
            suitable = [p for p in bidding_club_squad if p.get('market_value', 0) <= int(target_offer_value * 1.2)]
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
    # Find the CPU team id
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id FROM league_teams WHERE team_name = %s AND user_id = 1", (cpu_team_name,))
    cpu_team = cur.fetchone()
    if not cpu_team:
        cur.close()
        return jsonify({'error': 'CPU team not found.'}), 404
    cpu_team_id = cpu_team['id']
    # Get the squad for that club
    cur.execute("SELECT p.id, p.player_name, p.market_value FROM players p JOIN team_players tp ON p.id = tp.player_id WHERE tp.team_id = %s", (cpu_team_id,))
    bidding_club_squad = cur.fetchall()
    # 20% chance the team quits negotiation
    if random.random() < 0.2:
        cur.close()
        return jsonify({'quit': True, 'message': f'{cpu_team_name} has quit negotiations.'})
    # Otherwise, improve the offer (increase cash or offer a better swap)
    new_cash = int(cash * random.uniform(1.05, 1.15))
    new_player_swap = None
    # 70% chance to offer a swap if not already, or improve swap
    if bidding_club_squad and (not player_swap or random.random() < 0.7):
        suitable = [p for p in bidding_club_squad if p.get('market_value', 0) <= int(new_cash * 1.2)]
        if suitable:
            exchange_player = random.choice(suitable)
            # If the swap player is worth more than the offer value, demand compensation from the user
            if exchange_player['market_value'] > new_cash:
                compensation = exchange_player['market_value'] - new_cash
                new_cash = -compensation  # Negative means user must pay
            else:
                new_cash = new_cash - exchange_player['market_value']
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
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    # Ensure the team belongs to the current user
    cur.execute("SELECT id FROM league_teams WHERE id = %s AND user_id = %s", (team_id, current_user.id))
    team_check = cur.fetchone()
    if not team_check:
        cur.close()
        return abort(403)
    # Fetch all players for this team
    cur.execute("""
        SELECT p.id, p.player_name, p.registered_position, p.age, p.nationality, p.salary, p.contract_years_remaining, p.market_value
        FROM players p
        JOIN team_players tp ON p.id = tp.player_id
        WHERE tp.team_id = %s
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
    # Find the CPU team id
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id FROM league_teams WHERE team_name = %s AND user_id = 1", (cpu_team_name,))
    cpu_team = cur.fetchone()
    if not cpu_team:
        cur.close()
        return jsonify({'error': 'CPU team not found.'}), 404
    cpu_team_id = cpu_team['id']
    # Get user's team
    cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = %s", (current_user.id,))
    user_team = cur.fetchone()
    if not user_team:
        cur.close()
        return jsonify({'error': 'You do not manage a team.'}), 400
    user_team_id = user_team['id']
    user_team_name = user_team['team_name']
    # Compose offer details for actionable inbox offer (CPU as sender, user as recipient)
    offered_players = []
    if player_swap:
        offered_players.append(player_swap['id'])
    offered_money = cash if cash > 0 else 0
    requested_players = [player_id]
    requested_money = abs(cash) if cash < 0 else 0
    # Insert offer into offers table (CPU as sender, user as recipient)
    cur.execute("""
        INSERT INTO offers (sender_id, recipient_id, offered_players, offered_money, requested_players, requested_money)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        1,  # CPU user
        current_user.id,
        json.dumps([pid for pid in offered_players if pid]),
        offered_money,
        json.dumps([pid for pid in requested_players if pid]),
        requested_money
    ))
    offer_id = cur.lastrowid
    # Compose summary for blog
    cur2 = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur2.execute("SELECT player_name FROM players WHERE id = %s", (player_id,))
    player_name = cur2.fetchone()['player_name']
    summary = f"Daily Mail: {player_name} has been sold by {user_team_name} to {cpu_team_name} for €{cash:,.0f}. The negotiation is pending confirmation."
    if player_swap:
        summary += f" {cpu_team_name} sends {player_swap['NAME']} in exchange."
    summary += "."
    cur2.execute("INSERT INTO posts (user_id, title, content, media_type) VALUES (%s, %s, %s, %s)", (1, 'Daily Mail Transfer', summary, 'none'))
    mysql.connection.commit()
    cur.close()
    cur2.close()
    return jsonify({'success': True, 'message': 'The Offer is on your mail for confirmation.', 'offer_id': offer_id})

@app.route('/offer/<int:offer_id>/confirm_sell', methods=['POST'])
@login_required
def confirm_sell_offer(offer_id):
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    # Get offer details
    cur.execute("SELECT * FROM offers WHERE id = %s AND sender_id = %s AND status = 'pending'", (offer_id, current_user.id))
    offer = cur.fetchone()
    if not offer:
        cur.close()
        return jsonify({'error': 'Offer not found or already handled.'}), 404
    # Get user and CPU league_team ids
    cur.execute("SELECT id FROM league_teams WHERE user_id = %s", (current_user.id,))
    user_team = cur.fetchone()
    cur.execute("SELECT id FROM league_teams WHERE user_id = 1 AND team_name = %s", (offer['recipient_id'],))
    cpu_team = cur.fetchone()
    if not user_team or not cpu_team:
        cur.close()
        return jsonify({'error': 'Teams not found for one of the users.'}), 400
    user_team_id = user_team['id']
    cpu_team_id = cpu_team['id']
    # Transfer players: requested_players to CPU, offered_players to user
    offered_players = json.loads(offer['offered_players'])
    requested_players = json.loads(offer['requested_players'])
    for pid in requested_players:
        cur.execute("DELETE FROM team_players WHERE team_id = %s AND player_id = %s", (user_team_id, pid))
        cur.execute("INSERT IGNORE INTO team_players (team_id, player_id) VALUES (%s, %s)", (cpu_team_id, pid))
    for pid in offered_players:
        cur.execute("DELETE FROM team_players WHERE team_id = %s AND player_id = %s", (cpu_team_id, pid))
        cur.execute("INSERT IGNORE INTO team_players (team_id, player_id) VALUES (%s, %s)", (user_team_id, pid))
    # Update budgets
    cur.execute("SELECT budget FROM league_teams WHERE id = %s", (user_team_id,))
    user_budget = cur.fetchone()['budget']
    cur.execute("SELECT budget FROM league_teams WHERE id = %s", (cpu_team_id,))
    cpu_budget = cur.fetchone()['budget']
    new_user_budget = user_budget + offer['requested_money'] - offer['offered_money']
    new_cpu_budget = cpu_budget - offer['requested_money'] + offer['offered_money']
    cur.execute("UPDATE league_teams SET budget = %s WHERE id = %s", (new_user_budget, user_team_id))
    cur.execute("UPDATE league_teams SET budget = %s WHERE id = %s", (new_cpu_budget, cpu_team_id))
    # Mark offer as accepted
    cur.execute("UPDATE offers SET status = 'accepted' WHERE id = %s", (offer_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True, 'updated_budget': new_user_budget, 'message': 'Sale confirmed and transfer completed!'})

if __name__ == '__main__':
    # For local development
    # app.run(debug=True)

    # For production with Waitress (if you decide to use it manually)
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000)
