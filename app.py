from datetime import date, timedelta, datetime
from functools import wraps
import os
import random
import secrets

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, session, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# ── App Init ─────────────────────────────────
app = Flask(__name__)

# Secret key: must be set via SECRET_KEY env var for production.
# If missing, we generate a random one per-process (sessions won't survive
# restarts – intentional so developers notice and fix it).
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    import sys
    if "pytest" not in sys.modules:
        print(
            "WARNING: SECRET_KEY env var not set. "
            "A random key is being used – sessions will reset on every restart. "
            "Set SECRET_KEY in your environment.",
            flush=True,
        )
    _secret = secrets.token_hex(32)
app.secret_key = _secret

# ── Database Config ───────────────────────────
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

# ── CSRF Protection ───────────────────────────
def _generate_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]

app.jinja_env.globals["csrf_token"] = _generate_csrf_token

def csrf_protect(f):
    """Validates the CSRF token on every state-changing request."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            token      = session.get("_csrf_token")
            form_token = request.form.get("_csrf_token")
            if not token or not form_token or not secrets.compare_digest(token, form_token):
                abort(403)
        return f(*args, **kwargs)
    return decorated

# ── Auth Decorator ────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated

def roles_required(*roles):
    """Abort with 403 if the logged-in user's role is not in the allowed list.
    Admin always has full access regardless of the roles specified."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            role = session.get("role")
            if role != "Admin" and role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator

def admin_required(f):
    """Shortcut: Admin only.""";
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "Admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated

# ── Models ────────────────────────────────────
class Student(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    first_name    = db.Column(db.String(50), nullable=False)
    surname       = db.Column(db.String(50), nullable=False)
    id_number     = db.Column(db.String(20), unique=True, nullable=False)
    email         = db.Column(db.String(100), nullable=True)
    phone         = db.Column(db.String(20),  nullable=True)
    guardian      = db.Column(db.String(100), nullable=True)
    stream        = db.Column(db.String(30),  nullable=True)
    year_of_study = db.Column(db.Integer,     nullable=True, default=1)
    status        = db.Column(db.String(20),  nullable=False, default="Active")  # Active | Graduated | Transferred
    notes         = db.Column(db.Text,        nullable=True)
    fee_balance   = db.Column(db.Float,       nullable=False, default=0.0)
    photo         = db.Column(db.Text,        nullable=True)  # base64-encoded image

    @property
    def name(self):
        return f"{self.first_name} {self.surname}"


class Teacher(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(50),  unique=True, nullable=False)
    subject       = db.Column(db.String(50),  nullable=False)
    email         = db.Column(db.String(100), nullable=False)
    phone         = db.Column(db.String(20),  nullable=True)
    qualification = db.Column(db.String(100), nullable=True)
    bio           = db.Column(db.Text,        nullable=True)
    status        = db.Column(db.String(20),  nullable=False, default="Active")


def _generate_course_code():
    """Generate a unique course code like ID-482."""
    while True:
        code = f"ID-{random.randint(100, 999)}"
        if not Course.query.filter_by(course_code=code).first():
            return code

class Course(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    course_code  = db.Column(db.String(20), unique=True, nullable=True)
    title        = db.Column(db.String(100), unique=True, nullable=False)
    teacher_id   = db.Column(db.Integer, db.ForeignKey("teacher.id", ondelete="SET NULL"), nullable=True)
    teacher_name = db.Column(db.String(100), nullable=True)  # legacy fallback
    duration     = db.Column(db.Integer, default=60, nullable=False)
    session_type  = db.Column(db.String(20), default="session", nullable=False)
    subject_group = db.Column(db.String(50), nullable=True)
    start_date    = db.Column(db.Date, nullable=True)
    teacher      = db.relationship("Teacher", backref=db.backref("courses", passive_deletes=True))
    students     = db.relationship(
        "Student", secondary="enrollment",
        backref=db.backref("courses", passive_deletes=True)
    )

    @property
    def student_count(self):
        return len(self.students)

    @property
    def assigned_teacher_name(self):
        if self.teacher:
            return self.teacher.name
        return self.teacher_name or ""

    @property
    def teacher_initials(self):
        name = self.assigned_teacher_name
        if not name:
            return ""
        parts = name.strip().split()
        return "".join(p[0].upper() for p in parts[:2])


class Enrollment(db.Model):
    __tablename__ = "enrollment"
    student_id = db.Column(db.Integer, db.ForeignKey("student.id", ondelete="CASCADE"), primary_key=True)
    course_id  = db.Column(db.Integer, db.ForeignKey("course.id",  ondelete="CASCADE"), primary_key=True)


class Attendance(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    course_id  = db.Column(db.Integer, db.ForeignKey("course.id",  ondelete="CASCADE"), nullable=True)
    status     = db.Column(db.String(10), nullable=False)
    date       = db.Column(db.Date, default=date.today, nullable=False)
    student    = db.relationship("Student", backref=db.backref("attendances", passive_deletes=True))
    course     = db.relationship("Course",  backref=db.backref("attendances", passive_deletes=True))


class FeeStructure(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False)
    amount   = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False, default="Tuition")
    term     = db.Column(db.String(20), nullable=False, default="Term 1")
    year     = db.Column(db.Integer, nullable=False, default=2025)


class Payment(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    student_id   = db.Column(db.Integer, db.ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    fee_id       = db.Column(db.Integer, db.ForeignKey("fee_structure.id", ondelete="CASCADE"), nullable=False)
    amount_paid  = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, default=date.today, nullable=False)
    method       = db.Column(db.String(30), default="Cash")
    reference    = db.Column(db.String(50), nullable=True)
    student      = db.relationship("Student", backref=db.backref("payments", passive_deletes=True))
    fee          = db.relationship("FeeStructure", backref=db.backref("payments", passive_deletes=True))


class Exam(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(100), nullable=False)
    course_id   = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), nullable=False)
    exam_date   = db.Column(db.Date, nullable=False)
    total_marks = db.Column(db.Integer, default=100)
    exam_type   = db.Column(db.String(30), default="Mid-Term")
    term        = db.Column(db.String(20), default="Term 1")
    course      = db.relationship("Course", backref=db.backref("exams", passive_deletes=True))


class ExamResult(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    exam_id    = db.Column(db.Integer, db.ForeignKey("exam.id",    ondelete="CASCADE"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    marks      = db.Column(db.Float, nullable=False)
    grade      = db.Column(db.String(5), nullable=True)
    remarks    = db.Column(db.String(200), nullable=True)
    exam       = db.relationship("Exam",    backref=db.backref("results",      passive_deletes=True))
    student    = db.relationship("Student", backref=db.backref("exam_results", passive_deletes=True))


class TimetableEntry(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    course_id  = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), nullable=False)
    day        = db.Column(db.String(10), nullable=False)
    start_time = db.Column(db.String(5),  nullable=False)
    end_time   = db.Column(db.String(5),  nullable=False)
    room       = db.Column(db.String(50), nullable=True)
    course     = db.relationship("Course", backref=db.backref("timetable", passive_deletes=True))


class Announcement(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(150), nullable=False)
    body       = db.Column(db.Text, nullable=False)
    author     = db.Column(db.String(80), nullable=False, default="Admin")
    created_at = db.Column(db.Date, default=lambda: __import__("datetime").date.today(), nullable=False)
    pinned     = db.Column(db.Boolean, default=False)


class AppUser(db.Model):
    """Multi-role login accounts (Admin, Teacher, Bursar)."""
    __tablename__ = "app_user"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), nullable=False, default="Teacher")  # Admin | Teacher | Bursar
    teacher_id    = db.Column(db.Integer, db.ForeignKey("teacher.id", ondelete="SET NULL"), nullable=True)
    teacher_link  = db.relationship("Teacher", backref=db.backref("user_account", uselist=False))

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)


class Book(db.Model):
    """Library book inventory."""
    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(150), nullable=False)
    author       = db.Column(db.String(100), nullable=True)
    isbn         = db.Column(db.String(30),  nullable=True)
    category     = db.Column(db.String(50),  nullable=True)
    copies_total = db.Column(db.Integer, nullable=False, default=1)
    copies_avail = db.Column(db.Integer, nullable=False, default=1)

    @property
    def status(self):
        return "Available" if self.copies_avail > 0 else "Out"


class BorrowRecord(db.Model):
    """Tracks who borrowed which book."""
    id          = db.Column(db.Integer, primary_key=True)
    book_id     = db.Column(db.Integer, db.ForeignKey("book.id",    ondelete="CASCADE"), nullable=False)
    student_id  = db.Column(db.Integer, db.ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    borrow_date = db.Column(db.Date, default=date.today, nullable=False)
    due_date    = db.Column(db.Date, nullable=False)
    return_date = db.Column(db.Date, nullable=True)
    book        = db.relationship("Book",    backref=db.backref("borrow_records", passive_deletes=True))
    student     = db.relationship("Student", backref=db.backref("borrow_records", passive_deletes=True))

    @property
    def is_overdue(self):
        if self.return_date:
            return False
        return date.today() > self.due_date


class DisciplinaryRecord(db.Model):
    __tablename__ = "disciplinary_record"
    id            = db.Column(db.Integer, primary_key=True)
    student_id    = db.Column(db.Integer, db.ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    incident_date = db.Column(db.Date, nullable=False)
    severity      = db.Column(db.String(20), nullable=False, default="medium")
    description   = db.Column(db.Text, nullable=False)
    action_taken  = db.Column(db.Text)
    status        = db.Column(db.String(20), nullable=False, default="open")
    created_at    = db.Column(db.Date, default=date.today)

    student = db.relationship("Student", backref=db.backref("disciplinary_records", passive_deletes=True))


# ── Student Portal User ───────────────────────
class StudentPortalUser(db.Model):
    """Login credentials for the student self-service portal."""
    __tablename__ = "student_portal_user"
    id            = db.Column(db.Integer, primary_key=True)
    student_id    = db.Column(db.Integer, db.ForeignKey("student.id", ondelete="CASCADE"), unique=True, nullable=False)
    username      = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    last_login    = db.Column(db.DateTime, nullable=True)
    student       = db.relationship("Student", backref=db.backref("portal_user", uselist=False, passive_deletes=True))

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)


# ── Teacher Attendance ────────────────────────
class TeacherAttendance(db.Model):
    __tablename__ = "teacher_attendance"
    id         = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id", ondelete="CASCADE"), nullable=False)
    date       = db.Column(db.Date, default=date.today, nullable=False)
    status     = db.Column(db.String(20), nullable=False, default="Present")  # Present | Absent | Late | On Leave
    notes      = db.Column(db.String(200), nullable=True)
    teacher    = db.relationship("Teacher", backref=db.backref("attendances", passive_deletes=True))
    __table_args__ = (db.UniqueConstraint("teacher_id", "date", name="uq_teacher_date"),)


# ── Helpers ───────────────────────────────────
def compute_grade(marks, total):
    pct = (marks / total) * 100 if total > 0 else 0
    if pct >= 80: return "A"
    if pct >= 70: return "B"
    if pct >= 60: return "C"
    if pct >= 50: return "D"
    return "E"


def parse_attendance():
    present = Attendance.query.filter_by(status="Present").count()
    absent  = Attendance.query.filter_by(status="Absent").count()
    return present, absent


# ── Seed Data ─────────────────────────────────
def seed_db():
    if Student.query.first():
        return

    random.seed(42)

    teachers_data = [
        ("Alice Mwangi",   "Mathematics",  "alice@school.ac.ke",  "Active"),
        ("Brian Otieno",   "English",      "brian@school.ac.ke",  "Active"),
        ("Carol Njeri",    "Science",      "carol@school.ac.ke",  "Active"),
        ("David Kimani",   "History",      "david@school.ac.ke",  "Active"),
        ("Esther Wanjiku", "Computer Sc.", "esther@school.ac.ke", "Active"),
    ]
    teachers = []
    for name, subject, email, status in teachers_data:
        t = Teacher(name=name, subject=subject, email=email, status=status)
        db.session.add(t)
        teachers.append(t)

    courses_data = [
        ("Mathematics 101",    "Alice Mwangi",   90, "lecture"),
        ("English Grammar",    "Brian Otieno",   60, "session"),
        ("Biology Basics",     "Carol Njeri",    75, "lab"),
        ("World History",      "David Kimani",   60, "lecture"),
        ("Intro to Computers", "Esther Wanjiku", 90, "lab"),
    ]
    courses = []
    for title, teacher_name, duration, session_type in courses_data:
        c = Course(title=title, teacher_name=teacher_name, duration=duration, session_type=session_type)
        db.session.add(c)
        courses.append(c)

    students_data = [
        ("James",    "Kariuki",  "STU001"),
        ("Mary",     "Achieng",  "STU002"),
        ("Peter",    "Mutua",    "STU003"),
        ("Grace",    "Wambua",   "STU004"),
        ("Kevin",    "Odhiambo", "STU005"),
        ("Faith",    "Chebet",   "STU006"),
        ("Samuel",   "Njoroge",  "STU007"),
        ("Lydia",    "Moraa",    "STU008"),
        ("Daniel",   "Kipchoge", "STU009"),
        ("Patience", "Adhiambo", "STU010"),
    ]
    students = []
    for first_name, surname, id_number in students_data:
        s = Student(first_name=first_name, surname=surname, id_number=id_number)
        db.session.add(s)
        students.append(s)

    db.session.commit()

    for student in students:
        enrolled = random.sample(courses, k=random.randint(2, 4))
        for course in enrolled:
            if not Enrollment.query.filter_by(student_id=student.id, course_id=course.id).first():
                db.session.add(Enrollment(student_id=student.id, course_id=course.id))
    db.session.commit()

    today = date.today()
    for days_ago in range(7):
        att_date = today - timedelta(days=days_ago)
        for student in students:
            for course in student.courses:
                status = "Present" if random.random() > 0.2 else "Absent"
                db.session.add(Attendance(
                    student_id=student.id, course_id=course.id,
                    status=status, date=att_date,
                ))
    db.session.commit()

    fees_data = [
        ("Tuition Fee - Term 1", 12000, "Tuition",  "Term 1", 2025),
        ("Tuition Fee - Term 2", 12000, "Tuition",  "Term 2", 2025),
        ("Exam Fee - Term 1",     1500, "Exam",     "Term 1", 2025),
        ("Library Fee",            500, "Library",  "Term 1", 2025),
        ("Activity Fee",           800, "Activity", "Term 1", 2025),
    ]
    fees = []
    for name, amount, cat, term, year in fees_data:
        f = FeeStructure(name=name, amount=amount, category=cat, term=term, year=year)
        db.session.add(f)
        fees.append(f)
    db.session.commit()

    methods = ["Cash", "M-Pesa", "Bank Transfer"]
    for student in students:
        for fee in fees:
            if random.random() > 0.3:
                db.session.add(Payment(
                    student_id=student.id, fee_id=fee.id,
                    amount_paid=fee.amount,
                    payment_date=today - timedelta(days=random.randint(0, 30)),
                    method=random.choice(methods),
                    reference=f"REF{random.randint(10000, 99999)}",
                ))
    db.session.commit()

    exams = []
    for course in courses:
        for etype in ["Mid-Term", "End-Term"]:
            e = Exam(
                title=f"{course.title} - {etype}",
                course_id=course.id,
                exam_date=today - timedelta(days=random.randint(5, 20)),
                total_marks=100, exam_type=etype,
            )
            db.session.add(e)
            exams.append(e)
    db.session.commit()

    for exam in exams:
        course = Course.query.get(exam.course_id)
        for student in course.students:
            marks = round(random.uniform(35, 98), 1)
            grade = compute_grade(marks, exam.total_marks)
            db.session.add(ExamResult(
                exam_id=exam.id, student_id=student.id, marks=marks, grade=grade,
                remarks="Good effort" if marks >= 50 else "Needs improvement",
            ))
    db.session.commit()
    print("Database seeded with sample data.")


# ── Routes ────────────────────────────────────

@app.route("/")
def home():
    return redirect(url_for("login_page"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        token      = session.get("_csrf_token")
        form_token = request.form.get("_csrf_token")
        if not token or not form_token or not secrets.compare_digest(token, form_token):
            abort(403)

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin_user = os.environ.get("ADMIN_USERNAME", "").strip()
        admin_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")

        if not admin_user or not admin_hash:
            return render_template(
                "login.html",
                error="Server is not configured. Set ADMIN_USERNAME and ADMIN_PASSWORD_HASH.",
            )

        # Check AppUser table first
        app_user = AppUser.query.filter_by(username=username).first()
        if app_user and app_user.check_password(password):
            session.clear()
            session["user"]     = app_user.username
            session["role"]     = app_user.role
            session["user_id"]  = app_user.id
            session.pop("_csrf_token", None)
            return redirect(url_for("dashboard"))

        # Fallback: env-var admin
        if admin_user and admin_hash and username == admin_user and check_password_hash(admin_hash, password):
            session.clear()
            session["user"] = username
            session["role"] = "Admin"
            session.pop("_csrf_token", None)
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    present, absent = parse_attendance()
    courses  = Course.query.all()
    students = Student.query.all()

    exam_avgs = []
    for c in courses:
        results = ExamResult.query.join(Exam).filter(Exam.course_id == c.id).all()
        avg = round(sum(r.marks for r in results) / len(results), 1) if results else 0
        exam_avgs.append(avg)

    student_avgs = []
    for s in students:
        results = ExamResult.query.filter_by(student_id=s.id).all()
        if results:
            avg = sum(r.marks for r in results) / len(results)
            student_avgs.append((s, round(avg, 1)))
    student_avgs.sort(key=lambda x: x[1], reverse=True)
    top_students = student_avgs[:5]

    fees            = FeeStructure.query.all()
    payments        = Payment.query.all()
    total_expected  = sum(f.amount for f in fees) * len(students)
    total_collected = sum(p.amount_paid for p in payments)
    fee_rate        = round((total_collected / total_expected * 100) if total_expected > 0 else 0, 1)

    announcements = Announcement.query.order_by(
        Announcement.pinned.desc(), Announcement.created_at.desc()
    ).limit(3).all()

    today_att     = Attendance.query.filter_by(date=date.today()).all()
    today_present = sum(1 for a in today_att if a.status == "Present")
    today_total   = len(today_att)
    today_rate    = round(today_present / today_total * 100) if today_total > 0 else 0

    return render_template(
        "dashboard.html",
        student_count=Student.query.count(),
        teacher_count=Teacher.query.count(),
        course_count=Course.query.count(),
        attendance_count=Attendance.query.count(),
        present_count=present, absent_count=absent,
        course_labels=[c.title for c in courses],
        course_enrollments=[len(c.students) for c in courses],
        exam_avgs=exam_avgs, top_students=top_students,
        total_expected=total_expected, total_collected=total_collected,
        fee_rate=fee_rate, announcements=announcements,
        today_rate=today_rate, today_present=today_present, today_total=today_total,
        now=datetime.now(),
    )


# ── Students ──────────────────────────────────
@app.route("/students")
@login_required
def students_page():
    students = Student.query.all()
    fees     = FeeStructure.query.all()
    total_fees = sum(f.amount for f in fees)
    payments   = Payment.query.all()
    # Build a dict: student_id -> amount_paid
    paid_map = {}
    for p in payments:
        paid_map[p.student_id] = paid_map.get(p.student_id, 0) + p.amount_paid
    fee_info = {s.id: {
        'total': total_fees,
        'paid':  paid_map.get(s.id, 0),
        'balance': total_fees - paid_map.get(s.id, 0)
    } for s in students}
    first_fee = fees[0] if fees else None
    return render_template("students.html",
        students=students,
        courses=Course.query.all(),
        fee_info=fee_info,
        first_fee=first_fee,
        today=date.today().isoformat()
    )


@app.route("/students/<int:student_id>/enroll", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def enroll_student(student_id):
    student      = Student.query.get_or_404(student_id)
    selected_ids = {int(i) for i in request.form.getlist("course_ids")}
    for course in list(student.courses):
        if course.id not in selected_ids:
            student.courses.remove(course)
    for course_id in selected_ids:
        course = Course.query.get(course_id)
        if course and course not in student.courses:
            student.courses.append(course)
    db.session.commit()
    return redirect(url_for("students_page") + "#enrollments")


@app.route("/students/<int:student_id>/mark-paid", methods=["POST"])
@login_required
@roles_required("Admin", "Bursar")
@csrf_protect
def mark_fee_paid(student_id):
    student = Student.query.get_or_404(student_id)
    fees    = FeeStructure.query.all()
    if not fees:
        return redirect(url_for("students_page"))
    raw_date   = request.form.get("payment_date", date.today().isoformat())
    try:
        pay_date = date.fromisoformat(raw_date)
    except ValueError:
        pay_date = date.today()
    amount_paid = float(request.form.get("amount_paid", 0))
    method      = request.form.get("method", "Cash")
    reference   = request.form.get("reference", "")
    # Record payment against first fee structure (general payment)
    fee_id = int(request.form.get("fee_id", fees[0].id))
    db.session.add(Payment(
        student_id   = student.id,
        fee_id       = fee_id,
        amount_paid  = amount_paid,
        payment_date = pay_date,
        method       = method,
        reference    = reference or None,
    ))
    db.session.commit()
    return redirect(url_for("students_page"))

@app.route("/students/add", methods=["GET", "POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def add_student():
    if request.method == "POST":
        last     = Student.query.order_by(Student.id.desc()).first()
        next_num = (last.id + 1) if last else 1
        auto_id  = f"STU{next_num:03d}"
        while Student.query.filter_by(id_number=auto_id).first():
            next_num += 1
            auto_id = f"STU{next_num:03d}"

        # Handle photo upload
        photo_data = None
        photo_file = request.files.get("photo")
        if photo_file and photo_file.filename:
            import base64
            allowed = {"image/jpeg", "image/png", "image/gif", "image/webp"}
            if photo_file.content_type in allowed:
                raw = photo_file.read(2 * 1024 * 1024)  # max 2 MB
                encoded = base64.b64encode(raw).decode("utf-8")
                photo_data = f"data:{photo_file.content_type};base64,{encoded}"

        db.session.add(Student(
            first_name=request.form["first_name"][:50],
            surname=request.form["surname"][:50],
            id_number=auto_id,
            stream=request.form.get("stream", "")[:30] or None,
            photo=photo_data,
        ))
        db.session.commit()
        return redirect(url_for("students_page"))
    return render_template("add_student.html")


@app.route("/students/edit/<int:id>", methods=["GET", "POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def edit_student(id):
    student = Student.query.get_or_404(id)
    if request.method == "POST":
        student.first_name = request.form["first_name"][:50]
        student.surname    = request.form["surname"][:50]
        student.email      = request.form.get("email", "")[:100]
        student.phone      = request.form.get("phone", "")[:20]
        student.guardian   = request.form.get("guardian", "")[:100]
        student.stream     = request.form.get("stream", "")[:30]
        student.notes      = request.form.get("notes", "")
        db.session.commit()
        return redirect(url_for("students_page"))
    return render_template("edit_student.html", student=student)


@app.route("/students/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_student(id):
    db.session.delete(Student.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for("students_page"))


@app.route("/students/<int:id>/promote", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def promote_student(id):
    student = Student.query.get_or_404(id)
    action  = request.form.get("action")
    if action == "promote":
        student.year_of_study = (student.year_of_study or 1) + 1
    elif action == "graduate":
        student.status = "Graduated"
    elif action == "transfer":
        student.status = "Transferred"
    elif action == "reactivate":
        student.status = "Active"
    student.stream = request.form.get("stream", student.stream or "")
    db.session.commit()
    return redirect(url_for("students_page"))


@app.route("/students/bulk-promote", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def bulk_promote():
    """Promote all active students in a stream by 1 year."""
    stream = request.form.get("stream", "").strip()
    q = Student.query.filter_by(status="Active")
    if stream:
        q = q.filter_by(stream=stream)
    for s in q.all():
        s.year_of_study = (s.year_of_study or 1) + 1
    db.session.commit()
    return redirect(url_for("students_page"))


# ── Teachers ──────────────────────────────────
@app.route("/teachers")
@login_required
@admin_required
def teachers_page():
    teachers = Teacher.query.all()
    return render_template("teachers.html", teachers=teachers,
        total=len(teachers),
        active=sum(1 for t in teachers if t.status == "Active"),
        on_leave=sum(1 for t in teachers if t.status == "On Leave"))


@app.route("/teachers/add", methods=["GET", "POST"])
@login_required
@admin_required
@csrf_protect
def add_teacher():
    if request.method == "POST":
        db.session.add(Teacher(
            name=request.form["name"][:50],
            subject=request.form["subject"][:50],
            email=request.form["email"][:100],
            status=request.form.get("status", "Active"),
        ))
        db.session.commit()
        return redirect(url_for("teachers_page"))
    return render_template("add_teacher.html")


@app.route("/teachers/edit/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
@csrf_protect
def edit_teacher(id):
    teacher = Teacher.query.get_or_404(id)
    # ADD THIS LINE: Fetch courses to populate the dropdown
    courses = Course.query.all() 
    
    if request.method == "POST":
        teacher.name          = request.form["name"][:50]
        teacher.subject       = request.form.get("subject", "")[:50]
        teacher.email         = request.form["email"][:100]
        teacher.phone         = request.form.get("phone", "")[:20]
        teacher.qualification = request.form.get("qualification", "")[:100]
        teacher.bio           = request.form.get("bio", "")
        teacher.status        = request.form.get("status", "Active")

        db.session.commit()
        return redirect(url_for("teachers_page"))

    return render_template("edit_teacher.html", teacher=teacher, courses=courses)

@app.route("/teachers/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_teacher(id):
    db.session.delete(Teacher.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for("teachers_page"))


@app.route("/teachers/view/<int:id>")
@login_required
@admin_required
def view_teacher(id):
    return render_template("view_teacher.html", teacher=Teacher.query.get_or_404(id))

# ── Courses ───────────────────────────────────
@app.route("/courses")
@login_required
def courses_page():
    # Explicitly fetch all required lists
    courses = Course.query.all()
    teachers = Teacher.query.all()
    exams = Exam.query.order_by(Exam.exam_date.desc()).all()
    
    return render_template("courses.html",
        courses=courses, 
        teachers=teachers,
        exams=exams)

@app.route("/courses/add", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def add_course():
    teacher_id = request.form.get("teacher_id") or None
    teacher    = Teacher.query.get(teacher_id) if teacher_id else None
    new_course = Course(
        title=request.form["title"][:100],
        teacher_id=teacher.id if teacher else None,
        teacher_name=teacher.name if teacher else None,
        duration=int(request.form.get("duration") or 60),
        session_type=request.form.get("session_type", "In-person"),
        subject_group=request.form.get("subject_group") or None
    )
    new_course.course_code = _generate_course_code()
    db.session.add(new_course)
    db.session.commit()
    return redirect(url_for("courses_page"))

@app.route("/courses/edit/<int:id>", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def edit_course(id):
    course = Course.query.get_or_404(id)
    course.title = request.form["title"][:100]
    if "subject_group" in request.form:
        course.subject_group = request.form.get("subject_group") or None
    db.session.commit()
    return redirect(url_for("courses_page"))

# ... (rest of the file)

@app.route("/courses/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_course(id):
    db.session.delete(Course.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for("courses_page"))


# ── Enrollment ────────────────────────────────
@app.route("/enrollment/course/<int:course_id>")
@login_required
def enrollment_page(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template("enrollment.html", course=course,
        students=Student.query.all(),
        enrolled_ids={s.id for s in course.students})


@app.route("/courses/<int:course_id>/students")
@login_required
def course_students_page(course_id):
    course = Course.query.get_or_404(course_id)
    enrolled = course.students
    return render_template("course_students.html", course=course, students=enrolled)


@app.route("/enrollment/course/<int:course_id>/save", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def enroll_students(course_id):
    course       = Course.query.get_or_404(course_id)
    selected_ids = {int(i) for i in request.form.getlist("student_ids")}
    for student in list(course.students):
        if student.id not in selected_ids:
            course.students.remove(student)
    for student_id in selected_ids:
        student = Student.query.get(student_id)
        if student and student not in course.students:
            course.students.append(student)
    db.session.commit()
    return redirect(url_for("courses_page"))


# ── Attendance ────────────────────────────────
@app.route("/attendance")
@login_required
def attendance_page():
    selected_date_str = request.args.get("date", date.today().isoformat())
    try:
        selected_date = date.fromisoformat(selected_date_str)
    except ValueError:
        selected_date = date.today()

    all_courses        = Course.query.all()
    selected_course_id = request.args.get("course_id", "", type=str)
    selected_course    = None
    if selected_course_id:
        try:
            selected_course = Course.query.get(int(selected_course_id))
        except (ValueError, TypeError):
            selected_course = None

    students  = selected_course.students if selected_course else Student.query.all()
    att_query = Attendance.query.filter_by(date=selected_date)
    if selected_course:
        att_query = att_query.filter_by(course_id=selected_course.id)
    attendance = att_query.all()

    status_map    = {a.student_id: a.status for a in attendance}
    present_count = sum(1 for s in status_map.values() if s == "Present")
    absent_count  = sum(1 for s in status_map.values() if s == "Absent")
    unmarked      = len(students) - len(status_map)

    attendance_summary = []
    for student in Student.query.all():
        for course in student.courses:
            records = Attendance.query.filter_by(student_id=student.id, course_id=course.id).all()
            present = sum(1 for r in records if r.status == "Present")
            absent  = sum(1 for r in records if r.status == "Absent")
            attendance_summary.append({
                "name": student.name, "id_number": student.id_number,
                "course": course.title,
                "present": present, "absent": absent, "total": present + absent,
            })

    selected_teacher   = None
    course_teacher_map = {}
    if selected_course and selected_course.teacher_name:
        selected_teacher = Teacher.query.filter_by(name=selected_course.teacher_name).first()
    for course in all_courses:
        if course.teacher_name:
            course_teacher_map[course.id] = Teacher.query.filter_by(name=course.teacher_name).first()

    return render_template("attendance.html",
        students=students, attendance=attendance, status_map=status_map,
        selected_date=selected_date.isoformat(),
        present_count=present_count, absent_count=absent_count, unmarked=unmarked,
        attendance_summary=attendance_summary, all_courses=all_courses,
        selected_course=selected_course, selected_course_id=selected_course_id,
        selected_teacher=selected_teacher, course_teacher_map=course_teacher_map)


@app.route("/attendance/mark", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def mark_attendance():
    date_str = request.form.get("date", date.today().isoformat())
    try:
        mark_date = date.fromisoformat(date_str)
    except ValueError:
        mark_date = date.today()

    course_id_str = request.form.get("course_id", "")
    course_id     = int(course_id_str) if course_id_str else None
    course        = Course.query.get(course_id) if course_id else None
    students      = course.students if course else Student.query.all()

    for student in students:
        status = request.form.get(f"status_{student.id}", "Absent")
        record = Attendance.query.filter_by(
            student_id=student.id, course_id=course_id, date=mark_date
        ).first()
        if record:
            record.status = status
        else:
            db.session.add(Attendance(
                student_id=student.id, course_id=course_id,
                status=status, date=mark_date,
            ))
    db.session.commit()
    return redirect(url_for("attendance_page", date=date_str, course_id=course_id or ""))


@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ── Finance ───────────────────────────────────
@app.route("/finance")
@login_required
@roles_required("Admin", "Bursar")
def finance_page():
    fees     = FeeStructure.query.all()
    students = Student.query.order_by(Student.surname).all()
    payments = Payment.query.all()

    # Build per-student finance_data tuples: (student, total_fees, paid, balance)
    finance_data = []
    for student in students:
        total_fees = sum(f.amount for f in fees)
        paid       = sum(p.amount_paid for p in payments if p.student_id == student.id)
        balance    = total_fees - paid
        finance_data.append((student, total_fees, paid, balance))

    # Aggregate stats object expected by the template
    total_expected  = sum(row[1] for row in finance_data)
    total_collected = sum(row[2] for row in finance_data)
    total_balance   = sum(row[3] for row in finance_data)

    class _Stats:
        pass
    stats = _Stats()
    stats.total_expected  = total_expected
    stats.total_collected = total_collected
    stats.total_balance   = total_balance

    return render_template("finance.html",
        finance_data=finance_data,
        stats=stats,
        fees=fees,
        students=students,
        payments=payments,
    )


@app.route("/finance/fee/add", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def add_fee():
    db.session.add(FeeStructure(
        name=request.form["name"][:100],
        amount=float(request.form["amount"]),
        category=request.form.get("category", "Tuition"),
        term=request.form.get("term", "Term 1"),
        year=int(request.form.get("year", 2025)),
    ))
    db.session.commit()
    return redirect(url_for("finance_page"))


@app.route("/finance/fee/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_fee(id):
    db.session.delete(FeeStructure.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for("finance_page"))


@app.route("/finance/payment/add", methods=["POST"])
@login_required
@roles_required("Admin", "Bursar")
@csrf_protect
def add_payment():
    raw_date = request.form.get("payment_date", date.today().isoformat())
    try:
        pay_date = date.fromisoformat(raw_date)
    except ValueError:
        pay_date = date.today()
    db.session.add(Payment(
        student_id=int(request.form["student_id"]),
        fee_id=int(request.form["fee_id"]),
        amount_paid=float(request.form["amount_paid"]),
        payment_date=pay_date,
        method=request.form.get("method", "Cash"),
        reference=request.form.get("reference", "")[:50],
    ))
    db.session.commit()
    return redirect(url_for("finance_page"))


@app.route("/finance/payment/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_payment(id):
    db.session.delete(Payment.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for("finance_page"))


# ── Exams ─────────────────────────────────────
@app.route("/exams")
@login_required
def exams_page():
    return render_template("exams.html",
        exams=Exam.query.order_by(Exam.exam_date.desc()).all(),
        courses=Course.query.all())


@app.route("/exams/add", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def add_exam():
    raw_date = request.form.get("exam_date", date.today().isoformat())
    try:
        exam_date = date.fromisoformat(raw_date)
    except ValueError:
        exam_date = date.today()
    db.session.add(Exam(
        title=request.form["title"][:100],
        course_id=int(request.form["course_id"]),
        exam_date=exam_date,
        total_marks=int(request.form.get("total_marks", 100)),
        exam_type=request.form.get("exam_type", "Mid-Term"),
        term=request.form.get("term", "Term 1"),
    ))
    db.session.commit()
    return redirect(url_for("exams_page"))


@app.route("/exams/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_exam(id):
    db.session.delete(Exam.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for("exams_page"))


@app.route("/exams/<int:exam_id>/results", methods=["GET", "POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def exam_results(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if request.method == "POST":
        for student in exam.course.students:
            marks_str = request.form.get(f"marks_{student.id}", "")
            if not marks_str:
                continue
            marks  = float(marks_str)
            grade  = compute_grade(marks, exam.total_marks)
            result = ExamResult.query.filter_by(exam_id=exam.id, student_id=student.id).first()
            if result:
                result.marks   = marks
                result.grade   = grade
                result.remarks = request.form.get(f"remarks_{student.id}", "")
            else:
                db.session.add(ExamResult(
                    exam_id=exam.id, student_id=student.id, marks=marks, grade=grade,
                    remarks=request.form.get(f"remarks_{student.id}", ""),
                ))
        db.session.commit()
        return redirect(url_for("exam_results", exam_id=exam_id))
    return render_template("exam_results.html", exam=exam,
        results_map={r.student_id: r for r in exam.results})


# ── Report Cards ──────────────────────────────
@app.route("/report-cards")
@login_required
def report_cards():
    return render_template("report_cards.html", students=Student.query.all())


@app.route("/report-cards/<int:student_id>")
@login_required
def student_report(student_id):
    student     = Student.query.get_or_404(student_id)
    course_data = []
    for course in student.courses:
        results = ExamResult.query.join(Exam).filter(
            Exam.course_id == course.id, ExamResult.student_id == student.id
        ).all()
        avg, grade = (None, "N/A")
        if results:
            avg   = sum(r.marks for r in results) / len(results)
            grade = compute_grade(avg, 100)
        total_att = Attendance.query.filter_by(student_id=student.id, course_id=course.id).count()
        present   = Attendance.query.filter_by(student_id=student.id, course_id=course.id, status="Present").count()
        course_data.append({
            "course": course, "results": results,
            "average": round(avg, 1) if avg is not None else None,
            "grade": grade, "present": present, "total_att": total_att,
        })
    fees       = FeeStructure.query.all()
    total_fees = sum(f.amount for f in fees)
    paid       = sum(p.amount_paid for p in student.payments)
    return render_template("student_report.html", student=student, course_data=course_data,
        total_fees=total_fees, paid=paid, balance=total_fees - paid, today=date.today())


# ── Timetable ─────────────────────────────────
@app.route("/timetable")
@login_required
def timetable_page():
    entries = TimetableEntry.query.all()
    days    = ["Monday","Tuesday","Wednesday","Thursday","Friday"]
    times   = ["07:00","08:00","09:00","10:00","11:00","12:00","13:00","14:00","15:00","16:00"]
    grid    = {day: {} for day in days}
    for e in entries:
        grid[e.day][e.start_time] = e
    return render_template("timetable.html", entries=entries, courses=Course.query.all(),
        days=days, times=times, grid=grid)


@app.route("/timetable/add", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def add_timetable():
    db.session.add(TimetableEntry(
        course_id=int(request.form["course_id"]),
        day=request.form["day"],
        start_time=request.form["start_time"],
        end_time=request.form["end_time"],
        room=request.form.get("room", "")[:50],
    ))
    db.session.commit()
    return redirect(url_for("timetable_page"))


@app.route("/timetable/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_timetable(id):
    db.session.delete(TimetableEntry.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for("timetable_page"))


# ── Announcements ─────────────────────────────
@app.route("/announcements")
@login_required
def announcements_page():
    announcements = Announcement.query.order_by(
        Announcement.pinned.desc(), Announcement.created_at.desc()
    ).all()
    return render_template("announcements.html", announcements=announcements)


@app.route("/announcements/add", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def add_announcement():
    db.session.add(Announcement(
        title=request.form["title"][:150],
        body=request.form["body"],
        author=session.get("user", "Admin"),
        pinned="pinned" in request.form,
    ))
    db.session.commit()
    return redirect(url_for("announcements_page"))


@app.route("/announcements/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_announcement(id):
    db.session.delete(Announcement.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for("announcements_page"))


@app.route("/announcements/pin/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def pin_announcement(id):
    a = Announcement.query.get_or_404(id)
    a.pinned = not a.pinned
    db.session.commit()
    return redirect(url_for("announcements_page"))


# ── Per-Student Finance ───────────────────────
@app.route("/students/<int:student_id>/finance")
@login_required
def student_finance(student_id):
    student    = Student.query.get_or_404(student_id)
    fees       = FeeStructure.query.all()
    payments   = Payment.query.filter_by(student_id=student_id).order_by(Payment.payment_date.desc()).all()
    total_fees = sum(f.amount for f in fees)
    paid       = sum(p.amount_paid for p in payments)
    return render_template("student_finance.html", student=student, fees=fees,
        payments=payments, total_fees=total_fees, paid=paid, balance=total_fees - paid)


@app.route("/finance/receipt/<int:payment_id>")
@login_required
def fee_receipt(payment_id):
    return render_template("fee_receipt.html",
        payment=Payment.query.get_or_404(payment_id), today=date.today())


# ── M-Pesa ────────────────────────────────────
@app.route("/mpesa/dashboard")
@login_required
@roles_required("Admin", "Bursar")
def mpesa_dashboard():
    payments = Payment.query.filter(Payment.method == "M-Pesa").order_by(Payment.payment_date.desc()).all()
    return render_template("mpesa_dashboard.html", payments=payments,
        total=sum(p.amount_paid for p in payments))


@app.route("/mpesa/parent-portal")
@login_required
def mpesa_parent_portal():
    students   = Student.query.all()
    total_fees = sum(f.amount for f in FeeStructure.query.all())
    student_data = []
    for s in students:
        paid = sum(p.amount_paid for p in s.payments)
        student_data.append({"student": s, "paid": paid,
            "balance": total_fees - paid, "total": total_fees})
    return render_template("mpesa_parent_portal.html",
        student_data=student_data, total_fees=total_fees)


@app.route("/mpesa/status")
@login_required
def mpesa_status():
    return render_template("mpesa_status.html",
        payments=Payment.query.order_by(Payment.payment_date.desc()).limit(50).all(),
        mpesa_payments=Payment.query.filter(Payment.method == "M-Pesa")
            .order_by(Payment.payment_date.desc()).limit(50).all())


@app.route("/mpesa/initiate", methods=["POST"])
@login_required
@csrf_protect
def mpesa_initiate():
    phone      = request.form.get("phone", "").strip()
    amount     = int(request.form.get("amount", 0))
    student_id = int(request.form.get("student_id", 0))
    if not phone or amount <= 0:
        return redirect(url_for("mpesa_parent_portal"))
    try:
        from mpesa import stk_push
        result = stk_push(phone=phone, amount=amount,
            account_ref=f"STU{student_id:04d}", description="School Fee Payment")
        db.session.add(Payment(
            student_id=student_id, amount_paid=amount, fee_id=1,
            payment_date=date.today(),
            reference=result.get("CheckoutRequestID"), method="M-Pesa",
        ))
        db.session.commit()
    except Exception as e:
        print(f"M-Pesa initiation error: {e}")
    return redirect(url_for("mpesa_status"))


@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    """Safaricom callback endpoint.

    Protect this URL by appending ?secret=<MPESA_CALLBACK_SECRET> when
    registering it in the Daraja console, then set the same value in the
    MPESA_CALLBACK_SECRET environment variable.
    """
    expected_secret = os.environ.get("MPESA_CALLBACK_SECRET", "")
    if expected_secret:
        provided = request.args.get("secret", "")
        if not provided or not secrets.compare_digest(expected_secret, provided):
            return {"ResultCode": 1, "ResultDesc": "Unauthorized"}, 403

    data = request.get_json(silent=True) or {}
    try:
        body   = data["Body"]["stkCallback"]
        code   = body["ResultCode"]
        req_id = body["CheckoutRequestID"]
        if code == 0:
            items   = {i["Name"]: i["Value"] for i in body["CallbackMetadata"]["Item"]}
            receipt = items.get("MpesaReceiptNumber")
            payment = Payment.query.filter_by(reference=req_id).first()
            if payment and receipt:
                payment.reference = receipt
                db.session.commit()
    except Exception as e:
        print(f"Callback error: {e}")
    return {"ResultCode": 0, "ResultDesc": "Accepted"}



# ── Library ────────────────────────────────────
@app.route("/library")
@login_required
def library_page():
    books   = Book.query.order_by(Book.title).all()
    borrows = BorrowRecord.query.filter_by(return_date=None).order_by(BorrowRecord.due_date).all()
    students = Student.query.filter_by(status="Active").order_by(Student.first_name).all()
    return render_template("library.html", books=books, borrows=borrows, students=students)


@app.route("/library/book/add", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def add_book():
    db.session.add(Book(
        title=request.form["title"][:150],
        author=request.form.get("author", "")[:100],
        isbn=request.form.get("isbn", "")[:30],
        category=request.form.get("category", "")[:50],
        copies_total=int(request.form.get("copies_total", 1)),
        copies_avail=int(request.form.get("copies_total", 1)),
    ))
    db.session.commit()
    return redirect(url_for("library_page"))


@app.route("/library/book/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_book(id):
    db.session.delete(Book.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for("library_page"))


@app.route("/library/borrow", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def borrow_book():
    book = Book.query.get_or_404(int(request.form["book_id"]))
    if book.copies_avail < 1:
        return redirect(url_for("library_page"))
    due = date.today() + timedelta(days=int(request.form.get("days", 14)))
    db.session.add(BorrowRecord(
        book_id=book.id,
        student_id=int(request.form["student_id"]),
        due_date=due,
    ))
    book.copies_avail -= 1
    db.session.commit()
    return redirect(url_for("library_page"))


@app.route("/library/return/<int:id>", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def return_book(id):
    rec = BorrowRecord.query.get_or_404(id)
    rec.return_date = date.today()
    rec.book.copies_avail = min(rec.book.copies_avail + 1, rec.book.copies_total)
    db.session.commit()
    return redirect(url_for("library_page"))


# ── Users (multi-role) ──────────────────────────
@app.route("/users")
@login_required
@admin_required
def users_page():
    users    = AppUser.query.order_by(AppUser.username).all()
    teachers = Teacher.query.filter_by(status="Active").order_by(Teacher.name).all()
    return render_template("users.html", users=users, teachers=teachers)


@app.route("/users/add", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def add_user():
    teacher_id = request.form.get("teacher_id") or None
    u = AppUser(
        username=request.form["username"][:50],
        role=request.form.get("role", "Teacher"),
        teacher_id=int(teacher_id) if teacher_id else None,
    )
    u.set_password(request.form["password"])
    db.session.add(u)
    db.session.commit()
    return redirect(url_for("users_page"))


@app.route("/users/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_user(id):
    db.session.delete(AppUser.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for("users_page"))


@app.route("/users/reset-password/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def reset_user_password(id):
    u = AppUser.query.get_or_404(id)
    u.set_password(request.form["password"])
    db.session.commit()
    return redirect(url_for("users_page"))


# ── Disciplinary ──────────────────────────────
@app.route("/disciplinary")
@login_required
def disciplinary_page():
    severity = request.args.get("severity")
    status   = request.args.get("status")
    q = DisciplinaryRecord.query.join(Student)
    if severity:
        q = q.filter(DisciplinaryRecord.severity == severity)
    if status:
        q = q.filter(DisciplinaryRecord.status == status)
    records  = q.order_by(DisciplinaryRecord.incident_date.desc()).all()
    students = Student.query.order_by(Student.surname).all()
    return render_template(
        "disciplinary.html",
        records=records,
        students=students,
        today=date.today().isoformat(),
    )

@app.route("/disciplinary/add", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def add_disciplinary():
    rec = DisciplinaryRecord(
        student_id    = request.form["student_id"],
        incident_date = date.fromisoformat(request.form["incident_date"]),
        severity      = request.form.get("severity", "medium"),
        description   = request.form["description"],
        action_taken  = request.form.get("action_taken") or None,
        status        = request.form.get("status", "open"),
    )
    db.session.add(rec)
    db.session.commit()
    return redirect(url_for("disciplinary_page"))

@app.route("/disciplinary/edit/<int:id>", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def edit_disciplinary(id):
    rec = DisciplinaryRecord.query.get_or_404(id)
    rec.student_id    = request.form["student_id"]
    rec.incident_date = date.fromisoformat(request.form["incident_date"])
    rec.severity      = request.form.get("severity", "medium")
    rec.description   = request.form["description"]
    rec.action_taken  = request.form.get("action_taken") or None
    rec.status        = request.form.get("status", "open")
    db.session.commit()
    return redirect(url_for("disciplinary_page"))

@app.route("/disciplinary/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_disciplinary(id):
    rec = DisciplinaryRecord.query.get_or_404(id)
    db.session.delete(rec)
    db.session.commit()
    return redirect(url_for("disciplinary_page"))


# ── Student Portal ────────────────────────────
@app.route("/student-portal/login", methods=["GET", "POST"])
def student_portal_login():
    if "student_id" in session:
        return redirect(url_for("student_portal_home"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        pu = StudentPortalUser.query.filter_by(username=username).first()
        if pu and pu.check_password(password):
            session["student_id"]   = pu.student_id
            session["student_user"] = pu.username
            pu.last_login = datetime.now()
            db.session.commit()
            return redirect(url_for("student_portal_home"))
        error = "Invalid username or password."
    return render_template("student_portal_login.html", error=error)


@app.route("/student-portal/logout")
def student_portal_logout():
    session.pop("student_id", None)
    session.pop("student_user", None)
    return redirect(url_for("student_portal_login"))


@app.route("/student-portal")
def student_portal_home():
    if "student_id" not in session:
        return redirect(url_for("student_portal_login"))
    student = Student.query.get_or_404(session["student_id"])
    today_str   = date.today().strftime("%A, %d %B %Y")
    day_name    = date.today().strftime("%A")

    # Attendance stats
    all_att    = Attendance.query.filter_by(student_id=student.id).all()
    present_count = sum(1 for a in all_att if a.status == "Present")
    total_att  = len(all_att)
    att_pct    = round(present_count / total_att * 100) if total_att else 0
    att_days   = [{"date": a.date.isoformat(), "status": a.status} for a in
                  sorted(all_att, key=lambda x: x.date)]

    # Exam results
    all_results = ExamResult.query.filter_by(student_id=student.id)\
        .join(Exam).order_by(Exam.exam_date.desc()).all()
    results_data = []
    for r in all_results:
        pct = round((r.marks / r.exam.total_marks) * 100, 1) if r.exam.total_marks else 0
        results_data.append({
            "exam": {"course": r.exam.course, "name": r.exam.title, "date": r.exam.exam_date},
            "score": pct, "grade": r.grade or compute_grade(r.marks, r.exam.total_marks),
        })
    average_score = round(sum(x["score"] for x in results_data) / len(results_data), 1) if results_data else 0
    recent_results = results_data[:5]

    # Fees
    fees        = FeeStructure.query.all()
    total_fees  = sum(f.amount for f in fees)
    payments    = Payment.query.filter_by(student_id=student.id).all()
    total_paid  = sum(p.amount_paid for p in payments)
    fee_balance = max(0, total_fees - total_paid)
    fee_items   = []
    for f in fees:
        paid_for = sum(p.amount_paid for p in payments if p.fee_id == f.id)
        fee_items.append({
            "description": f.name, "date": f.term,
            "amount": f.amount, "paid": paid_for >= f.amount,
        })

    # Today's timetable
    today_classes = TimetableEntry.query.join(Course)\
        .join(Enrollment, (Enrollment.course_id == Course.id) & (Enrollment.student_id == student.id))\
        .filter(TimetableEntry.day == day_name).order_by(TimetableEntry.start_time).all()

    # Library
    borrow_records = BorrowRecord.query.filter_by(student_id=student.id)\
        .order_by(BorrowRecord.borrow_date.desc()).all()

    return render_template(
        "student_portal.html",
        student=student,
        today_date=today_str,
        enrolled_courses=len(student.courses),
        attendance_pct=att_pct,
        present_count=present_count,
        absent_count=total_att - present_count,
        attendance_days=att_days,
        all_results=results_data,
        recent_results=recent_results,
        average_score=average_score,
        fee_balance=fee_balance,
        total_paid=total_paid,
        payment_count=len(payments),
        fee_items=fee_items,
        next_due_date=None,
        active_term=None,
        today_classes=today_classes,
        borrow_records=borrow_records,
    )


# ── Student Portal Management (Admin) ─────────
@app.route("/students/portal-accounts")
@login_required
@admin_required
def student_portal_accounts():
    students = Student.query.filter_by(status="Active").order_by(Student.surname).all()
    return render_template("student_portal_accounts.html", students=students)


@app.route("/students/<int:student_id>/create-portal", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def create_student_portal(student_id):
    student = Student.query.get_or_404(student_id)
    if student.portal_user:
        return redirect(url_for("student_portal_accounts"))
    username = request.form.get("username", student.id_number).strip()
    password = request.form.get("password", "").strip()
    if not password:
        password = student.id_number  # default password = student ID
    pu = StudentPortalUser(student_id=student.id, username=username)
    pu.set_password(password)
    db.session.add(pu)
    db.session.commit()
    return redirect(url_for("student_portal_accounts"))


@app.route("/students/<int:student_id>/reset-portal-password", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def reset_student_portal_password(student_id):
    pu = StudentPortalUser.query.filter_by(student_id=student_id).first_or_404()
    new_pw = request.form.get("password", "").strip()
    if new_pw:
        pu.set_password(new_pw)
        db.session.commit()
    return redirect(url_for("student_portal_accounts"))


@app.route("/students/<int:student_id>/delete-portal", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def delete_student_portal(student_id):
    pu = StudentPortalUser.query.filter_by(student_id=student_id).first()
    if pu:
        db.session.delete(pu)
        db.session.commit()
    return redirect(url_for("student_portal_accounts"))


# ── ID Card ───────────────────────────────────
@app.route("/students/<int:student_id>/id-card")
@login_required
def student_id_card(student_id):
    student = Student.query.get_or_404(student_id)
    return render_template("student_id_card.html", student=student, year=date.today().year)


@app.route("/students/id-cards/bulk")
@login_required
def bulk_id_cards():
    ids = request.args.get("ids", "")
    if ids:
        id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
        students = Student.query.filter(Student.id.in_(id_list)).all()
    else:
        students = Student.query.filter_by(status="Active").order_by(Student.surname).all()
    return render_template("student_id_card.html", students=students, year=date.today().year, bulk=True)


# ── Teacher Attendance ────────────────────────
@app.route("/teacher-attendance")
@login_required
def teacher_attendance_page():
    date_str  = request.args.get("date", date.today().isoformat())
    try:
        sel_date = date.fromisoformat(date_str)
    except ValueError:
        sel_date = date.today()

    teachers = Teacher.query.filter_by(status="Active").order_by(Teacher.name).all()
    records  = {r.teacher_id: r for r in TeacherAttendance.query.filter_by(date=sel_date).all()}

    # Summary stats for the month
    month_start = sel_date.replace(day=1)
    monthly = TeacherAttendance.query.filter(
        TeacherAttendance.date >= month_start,
        TeacherAttendance.date <= sel_date,
    ).all()

    teacher_stats = {}
    for t in teachers:
        t_recs = [r for r in monthly if r.teacher_id == t.id]
        present = sum(1 for r in t_recs if r.status == "Present")
        teacher_stats[t.id] = {
            "present": present, "total": len(t_recs),
            "rate": round(present / len(t_recs) * 100) if t_recs else None,
        }

    return render_template(
        "teacher_attendance.html",
        teachers=teachers, records=records,
        sel_date=sel_date, today=date.today(),
        teacher_stats=teacher_stats,
    )


@app.route("/teacher-attendance/mark", methods=["POST"])
@login_required
@roles_required("Admin", "Teacher")
@csrf_protect
def mark_teacher_attendance():
    date_str = request.form.get("date", date.today().isoformat())
    try:
        att_date = date.fromisoformat(date_str)
    except ValueError:
        att_date = date.today()

    teacher_ids = request.form.getlist("teacher_ids")
    for tid in teacher_ids:
        status = request.form.get(f"status_{tid}", "Absent")
        notes  = request.form.get(f"notes_{tid}", "")
        rec = TeacherAttendance.query.filter_by(teacher_id=int(tid), date=att_date).first()
        if rec:
            rec.status = status
            rec.notes  = notes or None
        else:
            db.session.add(TeacherAttendance(
                teacher_id=int(tid), date=att_date, status=status,
                notes=notes or None,
            ))
    db.session.commit()
    return redirect(url_for("teacher_attendance_page", date=att_date.isoformat()))


# ── Chatbot ───────────────────────────────────
@app.route("/chatbot", methods=["POST"])
@login_required
def chatbot():
    import json as _json
    data = request.get_json(force=True, silent=True) or {}
    messages = data.get("messages", [])
    if not messages:
        return {"error": "No messages provided"}, 400

    # Build a live snapshot of school data for context
    try:
        student_count   = Student.query.filter_by(status="Active").count()
        teacher_count   = Teacher.query.filter_by(status="Active").count()
        course_count    = Course.query.count()
        fee_debtors     = Student.query.filter(Student.fee_balance > 0).count()
        total_owed      = db.session.query(db.func.sum(Student.fee_balance)).scalar() or 0
        overdue_books   = BorrowRecord.query.filter(
            BorrowRecord.return_date.is_(None),
            BorrowRecord.due_date < date.today()
        ).count()
        recent_announcements = Announcement.query.order_by(
            Announcement.pinned.desc(), Announcement.created_at.desc()
        ).limit(3).all()
        ann_text = "; ".join(
            f'"{a.title}" ({a.created_at})' for a in recent_announcements
        ) or "none"
        upcoming_exams = Exam.query.filter(Exam.exam_date >= date.today()) \
            .order_by(Exam.exam_date).limit(5).all()
        exam_text = "; ".join(
            f'{e.title} on {e.exam_date}' for e in upcoming_exams
        ) or "none"
    except Exception:
        student_count = teacher_count = course_count = fee_debtors = overdue_books = "?"
        total_owed = 0
        ann_text = exam_text = "unavailable"

    role = session.get("role", "Staff")
    user = session.get("user", "User")
    today_str = date.today().strftime("%A, %d %B %Y")

    system_prompt = f"""You are SchoolBot, a helpful assistant built into SchoolApp — a school management system.
Today is {today_str}. The logged-in user is {user} (role: {role}).

Current school snapshot:
- Active students: {student_count}
- Active teachers: {teacher_count}
- Courses: {course_count}
- Students with fee balance: {fee_debtors} (total owed: KES {total_owed:,.2f})
- Overdue library books: {overdue_books}
- Recent announcements: {ann_text}
- Upcoming exams: {exam_text}

You can answer questions about the school, help navigate the system, explain features, \
or give guidance based on the data above. For detailed records the user should use \
the relevant pages in the app. Keep answers concise and friendly. \
If asked something you can't answer from the data provided, say so honestly."""

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not configured. Add it to your .env file."}, 503

    try:
        import requests as _req
        resp = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 512,
                "system": system_prompt,
                "messages": messages,
            },
            timeout=30,
        )
        resp.raise_for_status()
        reply = resp.json()["content"][0]["text"]
        return {"reply": reply}
    except Exception as e:
        return {"error": str(e)}, 500


# ── DB Init ───────────────────────────────────
def init_db():
    with app.app_context():
        db.create_all()
        seed_db()
        # Auto-migrate missing columns (safe to run every startup)
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE course ADD COLUMN IF NOT EXISTS session_type VARCHAR(20) NOT NULL DEFAULT 'session'"))
                conn.execute(text("ALTER TABLE course ADD COLUMN IF NOT EXISTS start_date DATE"))
                conn.commit()
        except Exception as e:
            print(f"Migration notice: {e}")
        # SQLite-safe table creation for new models
        try:
            db.create_all()
        except Exception as e:
            print(f"Table creation notice: {e}")


init_db()

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode)
