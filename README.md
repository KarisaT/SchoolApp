# SchoolApp

A full-featured, web-based school administration system built with Flask and SQLAlchemy. SchoolApp lets administrators manage students, teachers, courses, fees, exams, attendance, and more — all from a clean, role-based browser dashboard deployed on Render with a PostgreSQL backend.

---

## Features

- **Dashboard** — At-a-glance stats: student count, teacher count, course enrolment chart, top students, fee collection rate, and today's attendance summary.
- **Students** — Add, edit, and delete student records with photo uploads (via Cloudinary), stream, year of study, status (Active / Graduated / Transferred), guardian info, notes, and fee balance tracking.
- **Teachers** — Manage teacher profiles including subject, email, phone, qualification, bio, and Active/On Leave status.
- **Courses** — Create and manage courses with assigned teachers, duration, and session type (lecture, lab, session).
- **Enrolment** — Enrol or remove students from individual courses via a modal checkbox interface.
- **Attendance** — Mark Present/Absent for each student by course and date; view historical records.
- **Exams & Results** — Create exams per course (Mid-Term, End-Term), record student marks, and auto-calculate letter grades.
- **Report Cards** — Per-student report cards summarising exam results across all enrolled courses.
- **Finance** — Fee structures, payments (Cash, M-Pesa, Bank Transfer), and per-student balance tracking with a payment history view.
- **M-Pesa Integration** — STK Push payments via Safaricom Daraja API with a callback webhook for real-time receipt reconciliation.
- **Library** — Book inventory, borrow/return tracking with due dates and overdue detection.
- **Announcements** — Post and pin school-wide announcements with author and date.
- **Disciplinary Records** — Log incidents with severity (low/medium/high), action taken, and status (open/resolved).
- **Timetable** — Weekly schedule entries per course with room assignment.
- **Users & Roles** — Multi-role accounts (Admin, Teacher, Bursar) with per-role route restrictions and password management.
- **CSRF Protection** — All state-changing forms are protected with CSRF tokens.
- **Authentication** — Session-based login supporting both env-var admin and database-backed AppUser accounts.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, Flask 3.1 |
| ORM / DB | Flask-SQLAlchemy 3.1, SQLAlchemy 2.0 |
| Default DB | SQLite (local), PostgreSQL (production) |
| Server | Gunicorn 25.3 |
| Templating | Jinja2 3.1 |
| Photo Storage | Cloudinary |
| Payments | Safaricom Daraja (M-Pesa STK Push) |
| Deployment | Render (web service + PostgreSQL) |
| Testing | pytest |

---

## Getting Started

### Prerequisites

- Python 3.11+
- pip

### Local Setup

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd SchoolApp

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the example env file and fill in your values
cp .env.example .env

# 5. Run the app
python app.py
```

The app will be available at `http://localhost:5000`.

On first run, the database is created automatically and seeded with sample students, teachers, courses, attendance, fees, payments, and exam results.

### Default Login

Set these in your `.env` file (see Configuration below). The app will not start correctly without `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH`.

To generate a password hash:

```bash
python generate_password_hash.py
```

---

## Configuration

All configuration is handled through environment variables (`.env` locally, Render environment variables in production):

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session secret key — **required in production** |
| `ADMIN_USERNAME` | Fallback admin login username |
| `ADMIN_PASSWORD_HASH` | Werkzeug password hash for the fallback admin |
| `DATABASE_URL` | Full database connection URL (defaults to SQLite `school.db` locally) |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name for student photo uploads |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `MPESA_CONSUMER_KEY` | Safaricom Daraja consumer key |
| `MPESA_CONSUMER_SECRET` | Safaricom Daraja consumer secret |
| `MPESA_SHORTCODE` | M-Pesa business short code |
| `MPESA_PASSKEY` | M-Pesa Lipa Na M-Pesa passkey |
| `MPESA_CALLBACK_URL` | Public URL for the M-Pesa STK Push callback |
| `MPESA_WEBHOOK_SECRET` | Optional secret to validate incoming M-Pesa callbacks |

---

## Deployment (Render)

1. Push your code to GitHub.
2. Create a new **Web Service** on [Render](https://render.com) pointing to your repo.
3. Create a **PostgreSQL** database on Render and copy the **External Database URL**.
4. Add all environment variables from the table above in the Render dashboard under **Environment**.
5. Set the **Start Command** to:
   ```
   gunicorn app:app
   ```
6. On every push to `main`, Render will redeploy automatically.

The app handles the `postgres://` → `postgresql://` URL prefix conversion automatically.

### Adding a new column to the production database

If you add a new column to a model and need to apply it to the live database without running a full migration tool, you can use the Python/psycopg2 approach:

```bash
python3 -c "
import psycopg2
conn = psycopg2.connect('YOUR_EXTERNAL_DATABASE_URL')
cur = conn.cursor()
cur.execute('ALTER TABLE student ADD COLUMN IF NOT EXISTS photo TEXT;')
conn.commit()
conn.close()
print('Done.')
"
```

---

## Project Structure

```
SchoolApp/
├── app.py                      # Models, routes, CSRF, auth, seeding
├── mpesa.py                    # M-Pesa STK Push helpers
├── migrate.py                  # Manual migration helper
├── add_mpesa_columns.py        # One-off migration for M-Pesa columns
├── generate_password_hash.py   # CLI tool to generate admin password hash
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Dev/test dependencies
├── render.yaml                 # Render deployment config
├── school.db                   # SQLite database (local only, not committed)
├── .env.example                # Example environment variables
└── templates/
    ├── base.html
    ├── login.html
    ├── dashboard.html
    ├── students.html
    ├── edit_student.html
    ├── teachers.html
    ├── edit_teacher.html
    ├── view_teacher.html
    ├── courses.html
    ├── edit_course.html
    ├── enrollment.html
    ├── attendance.html
    ├── exams.html
    ├── exam_results.html
    ├── report_cards.html
    ├── student_report.html
    ├── finance.html
    ├── student_finance.html
    ├── fee_receipt.html
    ├── library.html
    ├── announcements.html
    ├── disciplinary.html
    ├── timetable.html
    ├── academic_calendar.html
    ├── users.html
    ├── mpesa_dashboard.html
    ├── mpesa_parent_portal.html
    ├── mpesa_status.html
    ├── parent_portal.html
    ├── student_portal.html
    └── terms.html
```

---

## Database Models

| Model | Key Fields |
|---|---|
| **Student** | `id`, `first_name`, `surname`, `id_number`, `email`, `phone`, `guardian`, `stream`, `year_of_study`, `status`, `notes`, `fee_balance`, `photo` |
| **Teacher** | `id`, `name`, `subject`, `email`, `phone`, `qualification`, `bio`, `status` |
| **Course** | `id`, `title`, `teacher_id`, `duration`, `session_type`, `start_date` |
| **Enrollment** | `student_id`, `course_id` (join table) |
| **Attendance** | `id`, `student_id`, `course_id`, `status`, `date` |
| **Exam** | `id`, `title`, `course_id`, `exam_date`, `total_marks`, `exam_type` |
| **ExamResult** | `id`, `exam_id`, `student_id`, `marks`, `grade`, `remarks` |
| **FeeStructure** | `id`, `name`, `amount`, `category`, `term`, `year` |
| **Payment** | `id`, `student_id`, `fee_id`, `amount_paid`, `payment_date`, `method`, `reference` |
| **TimetableEntry** | `id`, `course_id`, `day`, `start_time`, `end_time`, `room` |
| **Announcement** | `id`, `title`, `body`, `author`, `created_at`, `pinned` |
| **Book** | `id`, `title`, `author`, `isbn`, `category`, `copies_total`, `copies_avail` |
| **BorrowRecord** | `id`, `book_id`, `student_id`, `borrow_date`, `due_date`, `return_date` |
| **DisciplinaryRecord** | `id`, `student_id`, `incident_date`, `severity`, `description`, `action_taken`, `status` |
| **AppUser** | `id`, `username`, `password_hash`, `role`, `teacher_id` |

---

## Roles & Permissions

| Role | Access |
|---|---|
| **Admin** | Full access to all pages and actions |
| **Teacher** | Attendance, exam results, disciplinary records, library borrows/returns |
| **Bursar** | Finance pages and fee payments only |

---

## License

This project is for educational purposes.
