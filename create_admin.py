"""
Bootstrap script: create or promote a user to Admin role.

Run from the SchoolApp folder:
    python create_admin.py

No need to be logged in — run this directly on the server.
"""
import getpass
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from app import app, db, AppUser

def main():
    username = input("Admin username: ").strip()
    if not username:
        print("Error: username cannot be empty.")
        sys.exit(1)

    password = getpass.getpass("Password: ")
    if not password:
        print("Error: password cannot be empty.")
        sys.exit(1)

    with app.app_context():
        user = AppUser.query.filter_by(username=username).first()
        if user:
            user.role = "Admin"
            user.set_password(password)
            db.session.commit()
            print(f"✓ User '{username}' updated — role set to Admin, password reset.")
        else:
            user = AppUser(username=username, role="Admin")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            print(f"✓ Admin user '{username}' created successfully.")

if __name__ == "__main__":
    main()
