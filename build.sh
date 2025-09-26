#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

python -c "from app import app, db, User; app.app_context().push(); db.create_all(); admin = User.query.filter_by(role='admin').first(); \
if not admin: \
  admin_user = User(email='palapalaprasanth@gmial.com', role='admin'); \
  admin_user.set_password('12345678'); \
  db.session.add(admin_user); \
  db.session.commit(); \
  print('Admin user created.')"