# File: app.py
import os
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from model_handler import generate_offset_report as create_validation_report
# app.py

# ... (other imports)

# Import the new burn function from model_handler

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-very-secret-key-that-should-be-changed'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    wallet_address = db.Column(db.String(42), nullable=True)
    validations = db.relationship('Validation', backref='user', lazy=True)

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Validation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.String(10), nullable=False)
    end_date = db.Column(db.String(10), nullable=False)
    offset_megatons = db.Column(db.Float, nullable=False)
    offset_value = db.Column(db.Float, nullable=False)
    transaction_hash = db.Column(db.String(66), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

# --- Main Page Routes ---
@app.route('/')
def home(): return render_template('home.html')

@app.route('/map')
@login_required
def map_tool():
    if current_user.role != 'farmer':
        flash('The validation tool is for Farmer accounts only.')
        return redirect(url_for('dashboard'))
    return render_template('map_tool.html')

# --- Authentication Routes ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email, password, role, wallet = request.form.get('email'), request.form.get('password'), request.form.get('role'), request.form.get('wallet_address')
        if User.query.filter_by(email=email).first():
            flash('Email address already exists.')
            return redirect(url_for('signup'))
        new_user = User(email=email, role=role, wallet_address=wallet)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email, password = request.form.get('email'), request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Please check your login details and try again.')
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# --- Dashboard Route ---
@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'farmer':
        return render_template('farmer_dashboard.html', user=current_user)
    elif current_user.role == 'company':
        return render_template('company_dashboard.html', user=current_user)
    elif current_user.role == 'admin':
        all_validations = Validation.query.order_by(Validation.timestamp.desc()).all()
        return render_template('admin_dashboard.html', user=current_user, validations=all_validations)
    return redirect(url_for('home'))
# app.py

# ... (Dashboard Route remains the same) ...

# --- NEW: Retirement Endpoint ---
@app.route('/retire_credits', methods=['POST'])
@login_required
def retire_credits():
    if current_user.role != 'company':
        flash('Only Company accounts can retire credits.')
        return redirect(url_for('dashboard'))

    try:
        data = request.get_json()
        amount_to_burn = data.get('amount')
        
        if not amount_to_burn or amount_to_burn <= 0:
            return jsonify({'error': 'Invalid amount specified.'}), 400
        
        # NOTE: This assumes the Company user has sufficient tokens in their wallet_address 
        # and has approved the server (contract owner) to burn tokens on their behalf 
        # (via ERC-1155's setApprovalForAll, which happens outside this app).
        company_wallet = current_user.wallet_address
        
        # Call the blockchain handler function
        burn_tx_hash = execute_burn_transaction(company_wallet, amount_to_burn)
        
        # Log the retirement in the database if necessary
        
        return jsonify({
            'message': f"Successfully retired {amount_to_burn} carbon credits.",
            'transaction_hash': burn_tx_hash
        }), 200

    except Exception as e:
        print(f"Burn error: {e}")
        return jsonify({'error': f"Blockchain retirement failed: {str(e)}"}), 500


# --- API Endpoint ---
@app.route('/predict', methods=['POST'])
@login_required
def predict():
    try:
        data = request.get_json()
        coords, start_date, end_date = data.get('coords'), data.get('start_date'), data.get('end_date')
        if not all([coords, start_date, end_date]):
            return jsonify({'error': 'Missing required data.'}), 400
        
        flat_coords = [coords[0][0], coords[0][1], coords[1][0], coords[1][1]]
        farmer_wallet = current_user.wallet_address
        
        prediction_results = create_validation_report(flat_coords, start_date, end_date, farmer_wallet)
        
        new_validation = Validation(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            offset_megatons=prediction_results.get('carbon_offset_megatons'),
            offset_value=prediction_results.get('offset_value'),
            transaction_hash=prediction_results.get('transaction_hash')
        )
        db.session.add(new_validation)
        db.session.commit()
        
        return jsonify(prediction_results)
    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({'error': str(e)}), 500

# app.py (Replace the bottom section)

if __name__ == '__main__':
    # Use this block for local testing
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)