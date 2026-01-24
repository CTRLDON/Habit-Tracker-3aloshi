"""
Flask backend for the habit tracker application.

This module implements a small REST API to support a habit tracking
application.  Users can register, log in, record completion of daily
habits, retrieve their progress, and fetch a daily motivational quote.

Key features:

* Uses Flask 3.x with SQLAlchemy for persistence and Flask-JWT-Extended
  for authentication.  The database defaults to SQLite but can be
  overridden via the `DATABASE_URL` environment variable.
* CORS is configured to allow cross‑origin requests from the static
  front‑end.  The standard `Authorization` header is explicitly
  permitted; MDN notes that `Authorization` must be listed in
  `Access-Control-Allow-Headers` and cannot be wildcarded【62605746793919†L219-L223】.
* The `GET /habits` endpoint is public.  It always returns the list of
  habits for the requested date, so the front‑end can render the
  checklist even before the user logs in.  If a token is provided,
  completions will be reflected; otherwise all habits are marked as
  incomplete.
* `POST /habits` and `GET /progress` require authentication via
  JSON Web Tokens.
* At startup, the application creates the database and seeds the
  default habit list.  Flask 3 removed the `before_first_request`
  decorator【604527695963413†L182-L184】, so initialization is done
  inside `app.app_context()` at import time.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import requests
from flask import Flask, request
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt_identity,
    jwt_required,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

###########################
# Application setup
###########################

# Create Flask app and configure database
app = Flask(__name__)

# Use SQLite database by default.  Set DATABASE_URL to override.
database_url = os.getenv("DATABASE_URL", "sqlite:///habits.db")
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Secret keys for Flask and JWT.  In production these should be set via
# environment variables.
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "super-secret-key")
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super-secret-jwt-key")

# Initialize extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)

# Configure CORS.  Explicitly allow the Authorization header; wildcards
# do not cover it【62605746793919†L219-L223】.  Expose Authorization so the
# browser can access it.  Credentials (cookies) are not used.
cors = CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["Authorization"],
    supports_credentials=False,
)


###########################
# Database models
###########################

class User(db.Model):
    """User model for authentication."""

    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    habit_entries = db.relationship(
        "HabitEntry",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Habit(db.Model):
    """Model for a habit definition."""

    __tablename__ = "habits"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    entries = db.relationship(
        "HabitEntry",
        back_populates="habit",
        cascade="all, delete-orphan",
    )


class HabitEntry(db.Model):
    """Model linking a user to a habit on a particular date."""

    __tablename__ = "habit_entries"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    habit_id = db.Column(db.Integer, db.ForeignKey("habits.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship("User", back_populates="habit_entries")
    habit = db.relationship("Habit", back_populates="entries")

    __table_args__ = (
        db.UniqueConstraint("user_id", "habit_id", "date", name="user_habit_date_unique"),
    )


###########################
# Utility functions
###########################

def seed_habits() -> None:
    """Populate the habits table with a default list if it is empty."""
    default_habits = [
        "Wake early",
        "Hydrate",
        "Read",
        "Exercise",
        "Pray",
        "Plan day",
        "Sleep Well",
        "Learn",
        "Eat Healthy",
        "Limit screentime",
        "Journal",
        "Gratitude",
        "Clean room",
        "Family time",
        "Walk",
    ]
    if Habit.query.count() == 0:
        for name in default_habits:
            db.session.add(Habit(name=name))
        db.session.commit()


def get_quote() -> Dict[str, str]:
    """
    Fetch a random quote from zenquotes.io.  If the API call fails,
    return a fallback quote.

    Returns a dictionary with keys 'quote' and 'author'.
    """
    try:
        response = requests.get("https://zenquotes.io/api/random", timeout=5)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            q = data[0].get("q")
            a = data[0].get("a")
            if q and a:
                return {"quote": q, "author": a}
    except Exception:
        pass
    # Fallback quote
    return {
        "quote": (
            "Every day is a new opportunity to improve yourself. "
            "Be mindful, grateful, and purposeful."
        ),
        "author": "Unknown",
    }


def parse_date(date_str: Optional[str]) -> date:
    """Parse a YYYY-MM-DD string into a date object, or return today."""
    if not date_str:
        return date.today()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Date must be in YYYY-MM-DD format")


###########################
# Initialization
###########################

# Create tables and seed habits at import time.  This replaces
# before_first_request, which was removed in Flask 3【604527695963413†L182-L184】.
with app.app_context():
    db.create_all()
    seed_habits()


###########################
# Routes
###########################

@app.post("/register")
def register() -> tuple[Dict[str, str], int]:
    """Register a new user account."""
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return {"error": "Username and password are required."}, 400
    if User.query.filter_by(username=username).first():
        return {"error": "Username already exists."}, 409
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return {"message": "User registered successfully."}, 201


@app.post("/login")
def login() -> tuple[Dict[str, str], int]:
    """Authenticate a user and return a JWT."""
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return {"error": "Invalid username or password."}, 401
    token = create_access_token(identity=str(user.id))
    return {"access_token": token}, 200


@app.get("/quote")
def quote() -> Dict[str, str]:
    """Return a random inspirational quote."""
    return get_quote()


@app.get("/habits")
@jwt_required(optional=True)
def get_habits() -> Dict[str, object]:
    """
    Return the list of habits and completion status for a given date.

    If the caller is authenticated, completion records will reflect their
    stored data; otherwise all habits are marked incomplete.  The date is
    supplied via the `date` query parameter (YYYY-MM-DD) and defaults
    to today.
    """
    # Determine date
    try:
        target_date = parse_date(request.args.get("date"))
    except ValueError as e:
        return {"error": str(e)}, 400

    # Ensure habit definitions exist
    if Habit.query.count() == 0:
        seed_habits()

    # Get all habits
    habits = Habit.query.order_by(Habit.id).all()
    result: List[Dict[str, object]] = []

    # If user is authenticated, fetch their completion status
    user_id = int(get_jwt_identity())
    completions: Dict[int, bool] = {}
    if user_id is not None:
        entries = HabitEntry.query.filter_by(user_id=user_id, date=target_date).all()
        completions = {entry.habit_id: bool(entry.completed) for entry in entries}

    for habit in habits:
        completed = completions.get(habit.id, False)
        result.append({"id": habit.id, "name": habit.name, "completed": completed})
    return {"date": target_date.isoformat(), "habits": result}, 200


@app.post("/habits")
@jwt_required()
def save_habits() -> tuple[Dict[str, object], int]:
    """
    Save the user's habit completions for a specific date.  Requires
    authentication.

    Expected JSON payload:
        {
          "date": "YYYY-MM-DD",
          "completions": {"1": true, "2": false, ...}
        }
    """
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    date_str = data.get("date")
    completions = data.get("completions")
    if not date_str or not isinstance(completions, dict):
        return {"error": "Invalid payload. 'date' and 'completions' are required."}, 400
    try:
        target_date = parse_date(date_str)
    except ValueError as e:
        return {"error": str(e)}, 400

    habits = Habit.query.order_by(Habit.id).all()
    completed_count = 0
    for habit in habits:
        completed = bool(completions.get(str(habit.id))) or bool(completions.get(habit.id))
        entry = HabitEntry.query.filter_by(
            user_id=user_id, habit_id=habit.id, date=target_date
        ).first()
        if entry:
            entry.completed = completed
        else:
            db.session.add(
                HabitEntry(
                    user_id=user_id,
                    habit_id=habit.id,
                    date=target_date,
                    completed=completed,
                )
            )
        if completed:
            completed_count += 1
    db.session.commit()
    percentage = (completed_count / len(habits) * 100) if habits else 0
    return {"message": "Habits saved.", "percentage": percentage}, 200


@app.get("/progress")
@jwt_required(optional=True)
def progress() -> Dict[str, object]:
    """
    Return aggregated completion data for a given period.  Requires
    authentication.

    Query parameters:
      period: "weekly" (default) or "monthly"
      end_date: optional end date (YYYY-MM-DD)
    """
    user_id = int(get_jwt_identity())
    if user_id is None:
        return {"error": "Missing or invalid token."}, 401

    period = request.args.get("period", "weekly").lower()
    try:
        end_date = parse_date(request.args.get("end_date"))
    except ValueError as e:
        return {"error": str(e)}, 400

    if period == "weekly":
        start_date = end_date - timedelta(days=6)
    elif period == "monthly":
        start_date = end_date - timedelta(days=29)
    else:
        return {"error": "Period must be 'weekly' or 'monthly'."}, 400

    habits = Habit.query.order_by(Habit.id).all()
    habit_stats: Dict[int, Dict[str, object]] = {
        habit.id: {
            "id": habit.id,
            "name": habit.name,
            "completed_days": 0,
            "total_days": 0,
        }
        for habit in habits
    }

    current = start_date
    while current <= end_date:
        entries = HabitEntry.query.filter_by(user_id=user_id, date=current).all()
        entries_map = {entry.habit_id: entry.completed for entry in entries}
        for habit in habits:
            stats = habit_stats[habit.id]
            stats["total_days"] += 1
            if entries_map.get(habit.id):
                stats["completed_days"] += 1
        current += timedelta(days=1)

    # Calculate percentages
    for stats in habit_stats.values():
        if stats["total_days"] > 0:
            stats["percentage"] = round(
                stats["completed_days"] / stats["total_days"] * 100, 2
            )
        else:
            stats["percentage"] = 0.0

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "period": period,
        "habits": list(habit_stats.values()),
    }, 200


if __name__ == "__main__":
    # For local development only.  In production use a WSGI server like Gunicorn.
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
