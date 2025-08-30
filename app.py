# app.py (updated)
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from pymongo import MongoClient
from bson import ObjectId
import json
import os
import uuid
from datetime import datetime, timedelta
import logging

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
CORS(app)  # Enable CORS for all routes

# Initialize extensions
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client['buildforge']
users_collection = db['users']
projects_collection = db['projects']
components_collection = db['components']

# Helper functions
def generate_id():
    return str(uuid.uuid4())

def get_timestamp():
    return datetime.now().isoformat()

def serialize_doc(doc):
    if not doc:
        return None
    doc['_id'] = str(doc['_id'])
    return doc

# Serve the main page
@app.route('/')
def index():
    return render_template('index.html')

# Auth Routes
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        name = data.get('name')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Check if user already exists
        if users_collection.find_one({'email': email}):
            return jsonify({'error': 'User already exists'}), 409
        
        # Hash password
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Create user
        user_id = generate_id()
        user = {
            'user_id': user_id,
            'email': email,
            'password': hashed_password,
            'name': name,
            'created_at': get_timestamp(),
            'updated_at': get_timestamp()
        }
        
        users_collection.insert_one(user)
        
        # Create access token
        access_token = create_access_token(identity=user_id)
        
        return jsonify({
            'message': 'User created successfully',
            'access_token': access_token,
            'user': {
                'user_id': user_id,
                'email': email,
                'name': name
            }
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Find user
        user = users_collection.find_one({'email': email})
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Check password
        if not bcrypt.check_password_hash(user['password'], password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Create access token
        access_token = create_access_token(identity=user['user_id'])
        
        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'user': {
                'user_id': user['user_id'],
                'email': user['email'],
                'name': user.get('name', '')
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API Routes
@app.route('/api/projects', methods=['GET', 'POST'])
@jwt_required()
def handle_projects():
    try:
        user_id = get_jwt_identity()
        
        if request.method == 'GET':
            # Get all projects for the user
            projects = list(projects_collection.find({'user_id': user_id}))
            for project in projects:
                project['_id'] = str(project['_id'])
            return jsonify(projects)
        
        elif request.method == 'POST':
            data = request.json
            project_id = generate_id()
            
            project = {
                'project_id': project_id,
                'user_id': user_id,
                'name': data.get('name', 'Untitled Project'),
                'description': data.get('description', ''),
                'created_at': get_timestamp(),
                'updated_at': get_timestamp(),
                'components': []
            }
            
            projects_collection.insert_one(project)
            return jsonify(serialize_doc(project)), 201
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_id>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def handle_project(project_id):
    try:
        user_id = get_jwt_identity()
        project = projects_collection.find_one({'project_id': project_id, 'user_id': user_id})
        
        if not project:
            return jsonify({'error': 'Project not found'}), 404
        
        if request.method == 'GET':
            return jsonify(serialize_doc(project))
        
        elif request.method == 'PUT':
            data = request.json
            update_data = {
                'name': data.get('name', project['name']),
                'description': data.get('description', project.get('description', '')),
                'updated_at': get_timestamp()
            }
            
            projects_collection.update_one(
                {'project_id': project_id}, 
                {'$set': update_data}
            )
            
            updated_project = projects_collection.find_one({'project_id': project_id})
            return jsonify(serialize_doc(updated_project))
        
        elif request.method == 'DELETE':
            projects_collection.delete_one({'project_id': project_id})
            # Also delete all components associated with this project
            components_collection.delete_many({'project_id': project_id})
            return jsonify({'message': 'Project deleted successfully'})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_id>/components', methods=['POST'])
@jwt_required()
def add_component(project_id):
    try:
        user_id = get_jwt_identity()
        project = projects_collection.find_one({'project_id': project_id, 'user_id': user_id})
        
        if not project:
            return jsonify({'error': 'Project not found'}), 404
        
        data = request.json
        component_id = generate_id()
        
        component = {
            'component_id': component_id,
            'project_id': project_id,
            'type': data.get('type'),
            'properties': data.get('properties', {}),
            'content': data.get('content', ''),
            'position': data.get('position', {'x': 0, 'y': 0}),
            'created_at': get_timestamp(),
            'updated_at': get_timestamp()
        }
        
        components_collection.insert_one(component)
        
        # Add component to project's components array
        projects_collection.update_one(
            {'project_id': project_id},
            {'$push': {'components': component_id}, '$set': {'updated_at': get_timestamp()}}
        )
        
        return jsonify(serialize_doc(component)), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_id>/components/<component_id>', methods=['PUT', 'DELETE'])
@jwt_required()
def handle_component(project_id, component_id):
    try:
        user_id = get_jwt_identity()
        project = projects_collection.find_one({'project_id': project_id, 'user_id': user_id})
        
        if not project:
            return jsonify({'error': 'Project not found'}), 404
        
        component = components_collection.find_one({'component_id': component_id, 'project_id': project_id})
        
        if not component:
            return jsonify({'error': 'Component not found'}), 404
        
        if request.method == 'PUT':
            data = request.json
            update_data = {
                'properties': data.get('properties', component['properties']),
                'content': data.get('content', component.get('content', '')),
                'position': data.get('position', component.get('position', {'x': 0, 'y': 0})),
                'updated_at': get_timestamp()
            }
            
            components_collection.update_one(
                {'component_id': component_id},
                {'$set': update_data}
            )
            
            updated_component = components_collection.find_one({'component_id': component_id})
            return jsonify(serialize_doc(updated_component))
        
        elif request.method == 'DELETE':
            components_collection.delete_one({'component_id': component_id})
            
            # Remove component from project's components array
            projects_collection.update_one(
                {'project_id': project_id},
                {'$pull': {'components': component_id}, '$set': {'updated_at': get_timestamp()}}
            )
            
            return jsonify({'message': 'Component deleted successfully'})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-code', methods=['POST'])
@jwt_required()
def generate_code():
    try:
        user_id = get_jwt_identity()
        data = request.json
        project_id = data.get('project_id')
        
        project = projects_collection.find_one({'project_id': project_id, 'user_id': user_id})
        if not project:
            return jsonify({'error': 'Project not found'}), 404
        
        # Get all components for this project
        components = list(components_collection.find({'project_id': project_id}))
        
        # Generate HTML code
        html_code = generate_html(components)
        css_code = generate_css(components)
        js_code = generate_js(components)
        
        # Generate backend code (Flask API)
        python_code = generate_python_api(project, components)
        
        # Generate database schema
        db_schema = generate_db_schema(components)
        
        return jsonify({
            'frontend': {
                'html': html_code,
                'css': css_code,
                'js': js_code
            },
            'backend': {
                'python': python_code
            },
            'database': {
                'schema': db_schema
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deploy', methods=['POST'])
@jwt_required()
def deploy_project():
    try:
        user_id = get_jwt_identity()
        data = request.json
        project_id = data.get('project_id')
        platform = data.get('platform', 'vercel')
        
        project = projects_collection.find_one({'project_id': project_id, 'user_id': user_id})
        if not project:
            return jsonify({'error': 'Project not found'}), 404
        
        # In a real implementation, this would handle actual deployment
        # For this example, we'll just return a mock response
        return jsonify({
            'status': 'success',
            'message': f'Project deployed to {platform} successfully',
            'url': f'https://{project_id}.{platform}.app'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-assistant', methods=['POST'])
@jwt_required()
def ai_assistant():
    try:
        user_id = get_jwt_identity()
        data = request.json
        prompt = data.get('prompt')
        project_id = data.get('project_id')
        
        # In a real implementation, this would integrate with an AI service like OpenAI
        # For this example, we'll simulate an AI response
        ai_response = simulate_ai_response(prompt, project_id)
        
        return jsonify({
            'response': ai_response
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Helper functions for code generation
def generate_html(components):
    html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generated Website</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
'''
    
    for component in components:
        comp_type = component.get('type', '').lower()
        props = component.get('properties', {})
        content = component.get('content', '')
        
        if comp_type == 'header':
            html += f'    <header>\n        <h1>{content}</h1>\n    </header>\n'
        elif comp_type == 'hero':
            html += f'    <section class="hero">\n        <h2>{props.get("title", "Hero Title")}</h2>\n        <p>{props.get("subtitle", "Hero subtitle")}</p>\n        <button>{props.get("buttonText", "Get Started")}</button>\n    </section>\n'
        elif comp_type == 'text':
            html += f'    <section>\n        <p>{content}</p>\n    </section>\n'
        elif comp_type == 'form':
            html += f'    <form>\n        <input type="text" placeholder="Your Name">\n        <input type="email" placeholder="Your Email">\n        <textarea placeholder="Your Message"></textarea>\n        <button type="submit">Submit</button>\n    </form>\n'
    
    html += '''    <script src="script.js"></script>
</body>
</html>'''
    
    return html

def generate_css(components):
    return '''body {
    font-family: Arial, sans-serif;
    line-height: 1.6;
    margin: 0;
    padding: 0;
    color: #333;
}

.hero {
    background: linear-gradient(120deg, #6366f1, #8b5cf6);
    color: white;
    padding: 3rem 2rem;
    text-align: center;
}

.hero button {
    background: white;
    color: #6366f1;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 0.375rem;
    font-weight: bold;
    cursor: pointer;
    margin-top: 1rem;
}

form {
    display: grid;
    gap: 1rem;
    max-width: 400px;
    margin: 2rem auto;
    padding: 2rem;
}

input, textarea {
    padding: 0.75rem;
    border: 1px solid #ddd;
    border-radius: 0.375rem;
}

button[type="submit"] {
    background: #6366f1;
    color: white;
    border: none;
    padding: 0.75rem;
    border-radius: 0.375rem;
    cursor: pointer;
}'''

def generate_js(components):
    return '''// Generated JavaScript code
document.addEventListener('DOMContentLoaded', function() {
    console.log('Website loaded successfully');
    
    // Form submission handler
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            alert('Form submitted! (This is a demo)');
        });
    }
});'''

def generate_python_api(project, components):
    return f'''# Generated Flask API for {project['name']}
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/api/data', methods=['GET'])
def get_data():
    return jsonify({{"message": "Hello from {project['name']} API"}})

if __name__ == '__main__':
    app.run(debug=True)'''

def generate_db_schema(components):
    return f'''-- Generated database schema
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Additional tables based on your components...'''

def simulate_ai_response(prompt, project_id):
    prompt_lower = prompt.lower()
    
    if 'header' in prompt_lower:
        return "I've added a header component to your project. You can customize the text and style in the properties panel."
    elif 'hero' in prompt_lower:
        return "I've created a hero section for your website. You can adjust the title, subtitle, and button text in the properties panel."
    elif 'form' in prompt_lower:
        return "I've added a contact form to your project. You can configure the form fields and submission behavior in the properties panel."
    elif 'button' in prompt_lower:
        return "I've created a button component. You can customize the text, color, and action in the properties panel."
    else:
        return f"I've processed your request: '{prompt}'. In a real implementation, I would generate components or fix issues based on your prompt."

if __name__ == '__main__':
    app.run(debug=True, port=5000)