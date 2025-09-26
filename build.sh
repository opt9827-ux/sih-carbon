#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

python -c "
from app import app, db, User

print('--- Initializing Database ---')
with app.app_context():
    db.create_all()
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        print('--- Creating Admin User ---')
        admin_user = User(email='palapalaprasanth@gmial.com', role='admin')
        admin_user.set_password('12345678')
        db.session.add(admin_user)
        db.session.commit()
        print('Admin user created successfully.')
    else:
        print('Admin user already exists.')
"
