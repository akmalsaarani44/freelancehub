from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from models import db, User, Client, Project, ClientTask, PersonalToDo
from datetime import datetime, timedelta
import os
import requests
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
# Allow HTTP for local testing of OAuth
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
database_url = os.environ.get('DATABASE_URL', 'sqlite:///freelancer.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
@login_required
def dashboard():
    today = datetime.now().date()
    soon = today + timedelta(days=7)
    
    personal_todos = PersonalToDo.query.filter_by(user_id=current_user.id, status='pending').order_by(PersonalToDo.due_date.asc().nullslast()).all()
    
    upcoming_tasks = ClientTask.query.join(Project).filter(
        Project.user_id == current_user.id,
        ClientTask.status != 'completed'
    ).filter(
        (ClientTask.due_date >= today) & (ClientTask.due_date <= soon)
    ).order_by(ClientTask.due_date.asc()).all()
    
    total_clients = Client.query.filter_by(user_id=current_user.id).count()
    active_projects = Project.query.filter_by(user_id=current_user.id, status='active').count()
    
    return render_template('dashboard.html', personal_todos=personal_todos, upcoming_tasks=upcoming_tasks, total_clients=total_clients, active_projects=active_projects, today=today)


@app.route('/todos/add', methods=['POST'])
@login_required
def add_todo():
    title = request.form.get('title')
    due_date = request.form.get('due_date')
    
    todo = PersonalToDo(
        user_id=current_user.id,
        title=title,
        due_date=datetime.strptime(due_date, '%Y-%m-%d') if due_date else None
    )
    db.session.add(todo)
    db.session.commit()
    flash('To-do added!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/todos/<int:todo_id>/delete', methods=['POST'])
@login_required
def delete_todo(todo_id):
    todo = PersonalToDo.query.filter_by(id=todo_id, user_id=current_user.id).first_or_404()
    db.session.delete(todo)
    db.session.commit()
    flash('To-do deleted!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/clients')
@login_required
def clients():
    client_list = Client.query.filter_by(user_id=current_user.id).all()
    return render_template('clients.html', clients=client_list)


@app.route('/clients/add', methods=['POST'])
@login_required
def add_client():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    company = request.form.get('company')
    notes = request.form.get('notes')
    
    client = Client(user_id=current_user.id, name=name, email=email, phone=phone, company=company, notes=notes)
    db.session.add(client)
    db.session.commit()
    flash('Client added successfully!', 'success')
    return redirect(url_for('clients'))


@app.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        client.name = request.form.get('name')
        client.email = request.form.get('email')
        client.phone = request.form.get('phone')
        client.company = request.form.get('company')
        client.notes = request.form.get('notes')
        db.session.commit()
        flash('Client updated successfully!', 'success')
        return redirect(url_for('clients'))
    
    return render_template('edit_client.html', client=client)


@app.route('/clients/<int:client_id>/delete', methods=['POST'])
@login_required
def delete_client(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    db.session.delete(client)
    db.session.commit()
    flash('Client deleted successfully!', 'success')
    return redirect(url_for('clients'))


@app.route('/client/<int:client_id>/projects')
@login_required
def client_projects(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    projects = Project.query.filter_by(client_id=client_id).all()
    return render_template('projects.html', client=client, projects=projects)


@app.route('/client/<int:client_id>/projects/add', methods=['POST'])
@login_required
def add_project(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    
    name = request.form.get('name')
    description = request.form.get('description')
    budget = request.form.get('budget')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    project = Project(
        user_id=current_user.id,
        client_id=client_id,
        name=name,
        description=description,
        budget=float(budget) if budget else None,
        start_date=datetime.strptime(start_date, '%Y-%m-%d') if start_date else None,
        end_date=datetime.strptime(end_date, '%Y-%m-%d') if end_date else None
    )
    db.session.add(project)
    db.session.commit()
    flash('Project added successfully!', 'success')
    return redirect(url_for('client_projects', client_id=client_id))


@app.route('/project/<int:project_id>/tasks')
@login_required
def project_tasks(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    tasks = ClientTask.query.filter_by(project_id=project_id).all()
    today = datetime.now().date()
    return render_template('tasks.html', project=project, tasks=tasks, today=today)


@app.route('/project/<int:project_id>/tasks/add', methods=['POST'])
@login_required
def add_task(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    
    title = request.form.get('title')
    description = request.form.get('description')
    priority = request.form.get('priority')
    due_date = request.form.get('due_date')
    
    task = ClientTask(
        project_id=project_id,
        title=title,
        description=description,
        priority=priority,
        due_date=datetime.strptime(due_date, '%Y-%m-%d') if due_date else None
    )
    db.session.add(task)
    db.session.commit()
    flash('Task added successfully!', 'success')
    return redirect(url_for('project_tasks', project_id=project_id))


@app.route('/task/<int:task_id>/update_status', methods=['POST'])
@login_required
def update_task_status(task_id):
    task = ClientTask.query.join(Project).filter(
        ClientTask.id == task_id,
        Project.user_id == current_user.id
    ).first_or_404()
    
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status in ['pending', 'in_progress', 'completed']:
        task.status = new_status
        db.session.commit()
        return jsonify({'success': True, 'status': new_status})
    
    return jsonify({'success': False, 'error': 'Invalid status'}), 400


@app.route('/api/ai/focus')
@login_required
def ai_focus():
    api_key = os.environ.get('VERCEL_GATEWAY_KEY')
    if not api_key:
        return jsonify({'error': 'AI Gateway API key not configured'}), 500
    
    tasks_text = "Your tasks: Complete project report, Review client feedback, Update portfolio website."
    
    prompt = f"You are a helpful assistant for a freelancer. Given my tasks, give me a very short 2-sentence focus advice for today. Tasks: {tasks_text}"
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': 'google/gemini-3-pro',
        'messages': [{'role': 'user', 'content': prompt}]
    }
    
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.post(
            'https://gateway.ai.vercel.ai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=10,
            verify=False
        )
        response.raise_for_status()
        data = response.json()
        advice = data['choices'][0]['message']['content']
        return jsonify({'advice': advice})
    except Exception as e:
        fallback_advice = "Focus on completing your most urgent client tasks today, and don't forget your personal to-do list!"
        return jsonify({'advice': fallback_advice})


@app.route('/project/<int:project_id>/ai_tasks', methods=['POST'])
@login_required
def generate_ai_tasks(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    
    api_key = os.environ.get('VERCEL_GATEWAY_KEY')
    if not api_key:
        flash('AI Gateway API key not configured. Please set VERCEL_GATEWAY_KEY environment variable.', 'danger')
        return redirect(url_for('project_tasks', project_id=project_id))
    
    description = project.description or "No description provided"
    prompt = f"""You are a helpful assistant for freelancers. Read this project description and return exactly 3 to 5 realistic milestone tasks for completing the project.

Project: {project.name}
Client: {project.client.name}
Description: {description}

Respond ONLY with a valid JSON array of strings (task titles). Example: ["Task 1", "Task 2", "Task 3"]"""
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': 'google/gemini-3-pro',
        'messages': [{'role': 'user', 'content': prompt}]
    }
    
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.post(
            'https://gateway.ai.vercel.ai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=30,
            verify=False
        )
        response.raise_for_status()
        data = response.json()
        content = data['choices'][0]['message']['content']
        
        import json
        import re
        
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            tasks = json.loads(json_match.group())
        else:
            tasks = json.loads(content)
        
        if not isinstance(tasks, list):
            raise ValueError("Response was not a JSON array")
        
        created_count = 0
        for task_title in tasks:
            task = ClientTask(
                project_id=project_id,
                title=task_title.strip(),
                description=f"Auto-generated task for {project.name}",
                priority='medium',
                status='pending'
            )
            db.session.add(task)
            created_count += 1
        
        db.session.commit()
        flash(f'Successfully generated {created_count} tasks with AI!', 'success')
        
    except Exception as e:
        tasks = [f"Phase 1: Setup {project.name}", f"Phase 2: Main Execution", f"Phase 3: Review and Delivery"]
        for task_title in tasks:
            task = ClientTask(
                project_id=project_id,
                title=task_title,
                description="Auto-generated structure (Fallback due to API Error)",
                priority='medium',
                status='pending'
            )
            db.session.add(task)
        db.session.commit()
        flash('Generated milestone tasks using smart fallback!', 'warning')
    
    return redirect(url_for('project_tasks', project_id=project_id))


@app.route('/calendar')
@login_required
def calendar():
    events = None
    calendar_connected = False
    
    if os.path.exists('credentials.json'):
        creds = session.get('google_creds')
        if creds:
            try:
                credentials = Credentials.from_authorized_user_info(creds)
                if credentials.valid:
                    calendar_connected = True
                    service = build('calendar', 'v3', credentials=credentials)
                    now = datetime.utcnow().isoformat() + 'Z'
                    events_result = service.events().list(
                        calendarId='primary',
                        timeMin=now,
                        maxResults=20,
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                    events = events_result.get('items', [])
            except Exception:
                calendar_connected = False
    
    return render_template('calendar.html', events=events, calendar_connected=calendar_connected)


@app.route('/calendar/authorize')
@login_required
def calendar_authorize():
    if not os.path.exists('credentials.json'):
        flash('Google Calendar credentials.json not found. Please download it from Google Cloud Console.', 'danger')
        return redirect(url_for('calendar'))
    
    flow = Flow.from_client_secrets_file(
        'credentials.json',
        scopes=['https://www.googleapis.com/auth/calendar.readonly']
    )
    flow.redirect_uri = url_for('calendar_callback', _external=True)
    
    authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['oauth_state'] = state
    
    return redirect(authorization_url)


@app.route('/calendar/callback')
@login_required
def calendar_callback():
    if not os.path.exists('credentials.json'):
        flash('Google Calendar credentials.json not found.', 'danger')
        return redirect(url_for('calendar'))
    
    state = session.get('oauth_state')
    if not state or state != request.args.get('state'):
        flash('OAuth state mismatch. Please try again.', 'danger')
        return redirect(url_for('calendar'))
    
    flow = Flow.from_client_secrets_file(
        'credentials.json',
        scopes=['https://www.googleapis.com/auth/calendar.readonly'],
        state=state
    )
    flow.redirect_uri = url_for('calendar_callback', _external=True)
    
    try:
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        session['google_creds'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        flash('Google Calendar connected successfully!', 'success')
    except Exception as e:
        flash(f'Failed to connect Google Calendar: {str(e)}', 'danger')
    
    return redirect(url_for('calendar'))


@app.route('/calendar/disconnect')
@login_required
def calendar_disconnect():
    session.pop('google_creds', None)
    flash('Google Calendar disconnected.', 'info')
    return redirect(url_for('calendar'))


def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@example.com')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created: admin / admin123")


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
