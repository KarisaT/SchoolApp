#!/usr/bin/env python3
"""
Utility script to generate a hashed password for ADMIN_PASSWORD_HASH.

Usage:
    python generate_password_hash.py

Then set the printed hash as your ADMIN_PASSWORD_HASH environment variable.
"""
import getpass
from werkzeug.security import generate_password_hash

password = getpass.getpass("Enter admin password: ")
confirm  = getpass.getpass("Confirm admin password: ")

if password != confirm:
    print("ERROR: Passwords do not match.")
else:
    print("\nAdd these to your environment (e.g. .env or shell profile):\n")
    print(f"  ADMIN_USERNAME=admin")
    print(f"  ADMIN_PASSWORD_HASH={generate_password_hash(password)}")
    print(f"\nAlso set a strong random secret key:")
    import secrets
    print(f"  SECRET_KEY={secrets.token_hex(32)}")
    print(f"\nFor M-Pesa callback protection:")
    print(f"  MPESA_CALLBACK_SECRET={secrets.token_hex(24)}")
