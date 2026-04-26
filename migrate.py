"""
One-time migration script — adds columns that exist in the SQLAlchemy
model but are missing from the PostgreSQL database.

Run once from the project root:
    python migrate.py
"""

import os
import random
from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in your environment / .env file")

# psycopg2 needs postgresql:// not postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

MIGRATIONS = [
    # Add photo column to student table (stores base64-encoded image as text)
    """
    ALTER TABLE student
    ADD COLUMN IF NOT EXISTS photo TEXT;
    """,

    # Safety net: add fee_balance if it is also missing
    """
    ALTER TABLE student
    ADD COLUMN IF NOT EXISTS fee_balance FLOAT NOT NULL DEFAULT 0.0;
    """,

    # Safety net: add notes if it is also missing
    """
    ALTER TABLE student
    ADD COLUMN IF NOT EXISTS notes TEXT;
    """,

    # Add course_code column to course table
    """
    ALTER TABLE course
    ADD COLUMN IF NOT EXISTS course_code VARCHAR(20);
    """,

    # Add session_type column to course table
    """
    ALTER TABLE course
    ADD COLUMN IF NOT EXISTS session_type VARCHAR(20) NOT NULL DEFAULT 'session';
    """,

    # Add start_date column to course table
    """
    ALTER TABLE course
    ADD COLUMN IF NOT EXISTS start_date DATE;
    """,

    # Add subject_group column to course table
    """
    ALTER TABLE course
    ADD COLUMN IF NOT EXISTS subject_group VARCHAR(50);
    """,

    # Add term column to exam table
    """
    ALTER TABLE exam
    ADD COLUMN IF NOT EXISTS term VARCHAR(20) NOT NULL DEFAULT 'Term 1';
    """,
]

def backfill_course_codes(conn):
    """Assign a random ID-NNN code to any course that doesn't have one yet."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM course WHERE course_code IS NULL")
    rows = cur.fetchall()
    if not rows:
        print("  No courses need back-filling.")
        cur.close()
        return
    used = set()
    cur.execute("SELECT course_code FROM course WHERE course_code IS NOT NULL")
    for (code,) in cur.fetchall():
        used.add(code)
    for (course_id,) in rows:
        while True:
            code = f"ID-{random.randint(100, 999)}"
            if code not in used:
                used.add(code)
                break
        cur.execute("UPDATE course SET course_code = %s WHERE id = %s", (code, course_id))
        print(f"  Assigned {code} to course id={course_id}")
    conn.commit()
    cur.close()


# ── Subject → Group mapping ──────────────────────────────────────────────────
SUBJECT_GROUP_MAP = {
    # Group A – Languages
    "mathematics": "Group A", "maths": "Group A", "math": "Group A",
    "english":     "Group A",
    "kiswahili":   "Group A", "swahili": "Group A",
    # Group B – Sciences
    "biology":   "Group B", "bio": "Group B",
    "chemistry": "Group B", "chem": "Group B",
    "physics":   "Group B", "phy": "Group B",
    # Group C – Humanities
    "history":   "Group C", "hist": "Group C",
    "geography": "Group C", "geo": "Group C",
    # Group D – Business / CRE
    "cre":              "Group D", "christian": "Group D",
    "business studies": "Group D", "bst": "Group D", "business": "Group D",
}

def backfill_subject_groups(conn):
    """Auto-assign subject_group to existing courses that don't have one."""
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM course WHERE subject_group IS NULL")
    rows = cur.fetchall()
    if not rows:
        print("  No courses need group assignment.")
        cur.close()
        return
    updated = 0
    for (course_id, title) in rows:
        t = (title or "").lower()
        group = None
        for keyword, grp in SUBJECT_GROUP_MAP.items():
            if keyword in t:
                group = grp
                break
        if group:
            cur.execute(
                "UPDATE course SET subject_group = %s WHERE id = %s",
                (group, course_id)
            )
            print(f"  '{title}' → {group}")
            updated += 1
        else:
            print(f"  '{title}' → (no keyword match, left unassigned)")
    conn.commit()
    print(f"  {updated}/{len(rows)} courses assigned a group.")
    cur.close()


def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    for sql in MIGRATIONS:
        sql = sql.strip()
        print(f"Running: {sql[:60]}...")
        cur.execute(sql)
        print("  ✓ done")

    cur.close()

    conn.autocommit = False

    # Back-fill existing courses with random codes
    print("\nBack-filling course codes...")
    backfill_course_codes(conn)

    # Auto-assign subject groups based on course titles
    print("\nAuto-assigning subject groups...")
    backfill_subject_groups(conn)

    conn.close()
    print("\nAll migrations completed successfully.")

if __name__ == "__main__":
    run()
