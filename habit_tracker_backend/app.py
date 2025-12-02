"""
Flask backend for the habit tracker application.

This application exposes a REST API that allows users to register an account,
authenticate with JSON Web Tokens, log daily habit completions, retrieve their
progress over different time periods, and fetch a motivational quote. It uses
SQLite for persistence via SQLAlchemy and returns JSON responses suitable for
consumption by a JavaScript front‑end.

Endpoints:
  POST /register               Register a new user account.
  POST /login                  Authenticate a user and return a JWT.
  GET  /quote                  Retrieve a random inspirational quote.
  GET  /habits                 Return the list of habits and their completion
                               status for a given date.
  POST /habits                 Save the user's habit completions for a date.
  GET  /progress               Retrieve aggregated completion data for a
                               period (weekly or monthly).

The API enforces authentication on all habit‑related endpoints using Flask‑JWT‑
Extended. CORS is enabled to allow cross‑origin requests from the Netlify
front‑end. See README.md for deployment instructions.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, date
from typing import Dict, List

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt_identity,
    jwt_required,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


###########################
# Application setup
###########################

# Create Flask app and configure database
app = Flask(__name__)

# Use SQLite database by default. You can override with the DATABASE_URL
# environment variable when deploying (e.g., to Postgres on Render).
database_url = os.getenv("DATABASE_URL", "sqlite:///habits.db")
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Secret keys for Flask and JWT. Always override in production via environment.
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "super-secret-key")
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super-secret-jwt-key")

db = SQLAlchemy(app)
jwt = JWTManager(app)
cors = CORS(app, resources={r"*": {"origins": "*"}})


###########################
# Database models
###########################

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    habit_entries = db.relationship("HabitEntry", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Habit(db.Model):
    __tablename__ = "habits"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    entries = db.relationship("HabitEntry", back_populates="habit", cascade="all, delete-orphan")


class HabitEntry(db.Model):
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
    """Populate the habits table with the default list if it's empty."""
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
    Fetch a random quote from the zenquotes.io API. If the API call fails,
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
            return {"quote": q, "author": a}
    except Exception:
        pass
    # Fallback quote in case of network failure
    return {
        "quote": "Every day is a new opportunity to improve yourself."
        " Be mindful, grateful, and purposeful.",
        "author": "Unknown",
    }


def parse_date(date_str: str) -> date:
    """Parse a YYYY-MM-DD string into a date object."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Date must be in YYYY-MM-DD format")


###########################
# Routes
###########################

@app.before_first_request
def initialize_database() -> None:
    """Initialize the database and seed default habits."""
    db.create_all()
    seed_habits()


@app.route("/register", methods=["POST"])
def register() -> tuple[Dict[str, str], int]:
    """
    Register a new user.

    Expects JSON with 'username' and 'password'. Returns a success message on
    success or an error message if the username is already taken or the input
    is invalid.
    """
    data = request.get_json() or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    if not username or not password:
        return {"error": "Username and password are required."}, 400
    if User.query.filter_by(username=username).first():
        return {"error": "Username already exists."}, 409
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return {"message": "User registered successfully."}, 201


@app.route("/login", methods=["POST"])
def login() -> tuple[Dict[str, str], int]:
    """
    Authenticate a user and return a JWT access token.

    Expects JSON with 'username' and 'password'. On success returns
    {"access_token": token}. On failure returns an error message.
    """
    data = request.get_json() or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return {"error": "Invalid username or password."}, 401
    token = create_access_token(identity=user.id)
    return {"access_token": token}, 200


@app.route("/quote", methods=["GET"])
def quote() -> Dict[str, str]:
    """Return a random inspirational quote."""
    return get_quote()


@app.route("/habits", methods=["GET"])
@jwt_required()
def get_habits() -> Dict[str, List[Dict[str, object]]]:
    """
    Return the user's habits and completion status for a given date.

    Query parameters:
      - date: optional date in YYYY-MM-DD format. Defaults to today (server time).
    Returns a list of habits with fields id, name, and completed (boolean).
    """
    user_id = get_jwt_identity()
    date_str = request.args.get("date")
    if date_str:
        try:
            target_date = parse_date(date_str)
        except ValueError as e:
            return {"error": str(e)}, 400
    else:
        target_date = date.today()
    # Retrieve all habits
    habits = Habit.query.order_by(Habit.id).all()
    entries_by_habit = {
        entry.habit_id: entry
        for entry in HabitEntry.query.filter_by(user_id=user_id, date=target_date).all()
    }
    result = []
    for habit in habits:
        entry = entries_by_habit.get(habit.id)
        result.append({
            "id": habit.id,
            "name": habit.name,
            "completed": bool(entry.completed) if entry else False,
        })
    return {"date": target_date.isoformat(), "habits": result}


@app.route("/habits", methods=["POST"])
@jwt_required()
def save_habits() -> tuple[Dict[str, object], int]:
    """
    Save the user's habit completions for a specific date.

    Expects JSON with:
        - date: YYYY-MM-DD string
        - completions: a dict mapping habit IDs (as strings) to booleans

    Creates or updates HabitEntry records for the given date. Returns the
    completion percentage (number of completed habits / total habits * 100).
    """
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    date_str = data.get("date")
    completions = data.get("completions")
    if not date_str or not isinstance(completions, dict):
        return {"error": "Invalid payload. 'date' and 'completions' are required."}, 400
    try:
        target_date = parse_date(date_str)
    except ValueError as e:
        return {"error": str(e)}, 400

    # Ensure all habits exist
    habits = Habit.query.order_by(Habit.id).all()
    habit_ids = {habit.id for habit in habits}
    # Update or create entries
    completed_count = 0
    for habit in habits:
        completed = bool(completions.get(str(habit.id)) or completions.get(habit.id))
        entry = HabitEntry.query.filter_by(user_id=user_id, habit_id=habit.id, date=target_date).first()
        if entry:
            entry.completed = completed
        else:
            entry = HabitEntry(
                user_id=user_id,
                habit_id=habit.id,
                date=target_date,
                completed=completed,
            )
            db.session.add(entry)
        if completed:
            completed_count += 1
    db.session.commit()
    percentage = (completed_count / len(habits) * 100) if habits else 0
    return {"message": "Habits saved.", "percentage": percentage}, 200


@app.route("/progress", methods=["GET"])
@jwt_required()
def progress() -> Dict[str, object]:
    """
    Return aggregated habit completion data for a given period.

    Query parameters:
      - period: 'weekly' (default) or 'monthly'
      - end_date: optional date (YYYY-MM-DD) marking the end of the period.

    The API returns a list of habits with counts of completed days and total
    occurrences within the period, along with percentage completions.
    """
    user_id = get_jwt_identity()
    period = request.args.get("period", "weekly").lower()
    end_date_str = request.args.get("end_date")
    if end_date_str:
        try:
            end_date = parse_date(end_date_str)
        except ValueError as e:
            return {"error": str(e)}, 400
    else:
        end_date = date.today()
    if period == "weekly":
        start_date = end_date - timedelta(days=6)
    elif period == "monthly":
        start_date = end_date - timedelta(days=29)
    else:
        return {"error": "Period must be 'weekly' or 'monthly'."}, 400

    # Build a map for each habit
    habits = Habit.query.order_by(Habit.id).all()
    habit_stats = {
        habit.id: {
            "id": habit.id,
            "name": habit.name,
            "completed_days": 0,
            "total_days": 0,
        }
        for habit in habits
    }

    # Count entries per day
    current_date = start_date
    while current_date <= end_date:
        # For each day, get entries for user
        entries = HabitEntry.query.filter_by(user_id=user_id, date=current_date).all()
        entries_map = {entry.habit_id: entry.completed for entry in entries}
        for habit in habits:
            stats = habit_stats[habit.id]
            stats["total_days"] += 1
            if entries_map.get(habit.id):
                stats["completed_days"] += 1
        current_date += timedelta(days=1)

    # Compute percentages
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
    }


if __name__ == "__main__":
    # In development you can run the server directly. In production, use a WSGI
    # server such as Gunicorn.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)