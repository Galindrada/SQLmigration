from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

mysql = MySQL(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirect to login page if not logged in

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

# --- Routes ---

@app.route('/')
def index():
    # Fetch some recent posts for the homepage
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p.id, p.title, p.content, u.username, p.created_at
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

# --- Blog Routes ---
@app.route('/blog')
def blog():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p.id, p.title, p.content, u.username, p.created_at
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

        if not title or not content:
            flash('Title and content are required.', 'danger')
            return redirect(url_for('create_post'))

        cur = mysql.connection.cursor()
        try:
            cur.execute("INSERT INTO posts (user_id, title, content) VALUES (%s, %s, %s)",
                        (user_id, title, content))
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

    # Fetch post details
    cur.execute("""
        SELECT p.id, p.title, p.content, u.username, p.created_at
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.id = %s
    """, (post_id,))
    post = cur.fetchone()

    if not post:
        flash('Post not found.', 'danger')
        return redirect(url_for('blog'))

    # Fetch comments for the post
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


# --- Team Management Routes ---
@app.route('/team_management')
@login_required
def team_management():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, team_name FROM teams WHERE user_id = %s", (current_user.id,))
    user_team = cur.fetchone()
    cur.close()

    team_players = []
    available_players = []

    if user_team:
        team_id = user_team[0]
        # Fetch players currently in the user's team
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT p.id, p.name, p.overall_rating, p.position
            FROM players p
            JOIN team_players tp ON p.id = tp.player_id
            WHERE tp.team_id = %s
        """, (team_id,))
        team_players = cur.fetchall()
        cur.close()

        # Fetch players not in the user's team (available to sign)
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT id, name, overall_rating, position
            FROM players
            WHERE id NOT IN (SELECT player_id FROM team_players WHERE team_id = %s)
        """, (team_id,))
        available_players = cur.fetchall()
        cur.close()
    else:
        # If no team exists, fetch all players for new team creation
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, name, overall_rating, position FROM players")
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
        cur.execute("INSERT INTO teams (user_id, team_name) VALUES (%s, %s)",
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
    cur.execute("SELECT id FROM teams WHERE user_id = %s", (user_id,))
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
    cur.execute("SELECT id FROM teams WHERE user_id = %s", (user_id,))
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


if __name__ == '__main__':
    app.run(debug=True)
