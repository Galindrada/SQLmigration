import os
import MySQLdb.cursors 
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
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

# User model for Flask-Login (remains the same)
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

# --- Helper function for file uploads (remains the same) ---
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


# --- Routes (existing routes remain the same) ---

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

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        # FIX: Changed 'pbk2:sha256' to 'pbkdf2:sha256'
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        cur = mysql.connection.cursor()
        try:
            cur.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                        (username, email, hashed_password))
            mysql.connection.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Registration failed: {e}', 'danger')
        finally:
            cur.close()
    return render_template('register.html')

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
    cur = mysql.connection.cursor()
    # Assuming 'teams' here refers to the user-created teams from your league (now 'league_teams')
    cur.execute("SELECT id, team_name FROM league_teams WHERE user_id = %s", (current_user.id,))
    user_team = cur.fetchone()
    cur.close()

    team_players = []
    available_players = []

    if user_team:
        team_id = user_team[0]
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT p.id, p.player_name, p.registered_position, p.attack, p.defense, p.stamina, p.top_speed
            FROM players p
            JOIN team_players tp ON p.id = tp.player_id
            WHERE tp.team_id = %s
            ORDER BY p.player_name ASC
        """, (team_id,))
        team_players = cur.fetchall()
        cur.close()

        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT id, player_name, registered_position, attack, defense, stamina, top_speed
            FROM players
            WHERE id NOT IN (SELECT player_id FROM team_players WHERE team_id = %s)
            ORDER BY player_name ASC
        """, (team_id,))
        available_players = cur.fetchall()
        cur.close()
    else:
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, player_name, registered_position, attack, defense, stamina, top_speed FROM players ORDER BY player_name ASC")
        available_players = cur.fetchall()
        cur.close()

    return render_template('team_management.html', user_team=user_team, team_players=team_players, available_players=available_players)

@app.route('/team_management/create', methods=['POST'])
@login_required
def create_team():
    team_name = request.form['team_name']
    user_id = current_user.id

    cur = mysql.connection.cursor()
    try:
        # Insert into 'league_teams'
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
    player_id = request.form['player_id']
    user_id = current_user.id

    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM league_teams WHERE user_id = %s", (user_id,))
    team_id_data = cur.fetchone()
    cur.close()

    if not team_id_data:
        flash('You must create a team first!', 'danger')
        return redirect(url_for('team_management'))

    team_id = team_id_data[0]

    cur = mysql.connection.cursor()
    try:
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

@app.route('/team_management/remove_player/<int:player_id>', methods=['POST'])
@login_required
def remove_player_from_team(player_id):
    user_id = current_user.id

    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM league_teams WHERE user_id = %s", (user_id,))
    team_id_data = cur.fetchone()
    cur.close()

    if not team_id_data:
        flash('You do not have a team.', 'danger')
        return redirect(url_for('team_management'))

    team_id = team_id_data[0]

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
    cur.close()
    return render_template('pes6_teams.html', game_teams=game_teams)

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
        SELECT id, player_name, registered_position, age, height, strong_foot
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
        # 'Club' needs to be fetched via a join or another query if not in player_data directly
        'Age': player_data.get('age'),
        'Height': player_data.get('height'),
        'Weight': player_data.get('weight'),
        'Nationality': player_data.get('nationality'),
        'Strong Foot': player_data.get('strong_foot'),
        'Favoured Side': player_data.get('favoured_side'),
        'Registered Position': player_data.get('registered_position'),
    }

    # Fetch club name for the player
    club_name = None
    if player_data.get('club_id'):
        cur = mysql.connection.cursor()
        cur.execute("SELECT club_name FROM teams WHERE id = %s", (player_data['club_id'],))
        club_name_result = cur.fetchone()
        if club_name_result:
            club_name = club_name_result[0]
        cur.close()
    basic_info['Club'] = club_name


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
        # 'Weak Foot Accuracy': player_data.get('weak_foot_accuracy'), # REMOVED
        # 'Weak Foot Frequency': player_data.get('weak_foot_frequency'), # REMOVED
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
                           skills_numeric=skills_numeric,
                           positional_skills=positional_skills,
                           special_skills=special_skills)

if __name__ == '__main__':
    app.run(debug=True)
