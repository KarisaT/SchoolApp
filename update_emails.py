"""
Run this script once to update teacher emails from school.ac.ke to myapp.io
Usage: python update_emails.py
"""

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "school.db")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class Teacher(db.Model):
    id      = db.Column(db.Integer, primary_key=True)
    name    = db.Column(db.String(50), unique=True, nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    email   = db.Column(db.String(100), nullable=False)
    status  = db.Column(db.String(20), nullable=False, default="Active")

with app.app_context():
    teachers = Teacher.query.filter(Teacher.email.like("%@school.ac.ke")).all()
    
    if not teachers:
        print("No teachers found with @school.ac.ke emails.")
    else:
        for teacher in teachers:
            old_email = teacher.email
            teacher.email = teacher.email.replace("school.ac.ke", "myapp.io")
            print(f"Updated: {old_email} → {teacher.email}")
        
        db.session.commit()
        print(f"\n✅ Done — {len(teachers)} teacher email(s) updated successfully.")
