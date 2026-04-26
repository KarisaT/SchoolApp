"""
add_mpesa_columns.py
--------------------
One-time migration to add M-Pesa-related columns to the payment table.
Run once: python add_mpesa_columns.py

Safe to run multiple times — uses ALTER TABLE ... IF NOT EXISTS style checks.
"""

import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "school.db")


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    migrations = [
        ("payment", "mpesa_checkout_id", "VARCHAR(100)"),
        ("payment", "phone",             "VARCHAR(20)"),
        # Widen the reference column (SQLite doesn't enforce length, so this is informational)
        # ("payment", "reference", "VARCHAR(100)"),  # already exists
    ]

    for table, col, coltype in migrations:
        if not column_exists(cur, table, col):
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
            print(f"  ✓ Added column: {table}.{col}")
        else:
            print(f"  — Already exists: {table}.{col}")

    # Also add phone to student table if it doesn't exist (useful for auto-filling parent portal)
    if not column_exists(cur, "student", "parent_phone"):
        cur.execute("ALTER TABLE student ADD COLUMN parent_phone VARCHAR(20)")
        print("  ✓ Added column: student.parent_phone")
    else:
        print("  — Already exists: student.parent_phone")

    conn.commit()
    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    print(f"Migrating database: {DB_PATH}")
    migrate()
