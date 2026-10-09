"""Login, registration, and logout endpoints."""
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, render_template, request, session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from database import SessionLocal
from models import TrackingState, User
from services.tracking import confirm_time, utcnow

bp = Blueprint("auth", __name__)

@bp.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")

@bp.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")

@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a JSON object with username and password."), 400

    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not username.strip() or len(username) > 50:
        return jsonify(error="Username must contain 1 to 50 characters and cannot be blank."), 400
    if not isinstance(password, str) or len(password) < 8 or not password.strip():
        return jsonify(error="Password must contain at least 8 characters and cannot be blank."), 400

    with SessionLocal() as db_session:
        if db_session.scalar(select(User).where(User.username == username)) is not None:
            return jsonify(error="Username already exists."), 409

        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role="user",
        )
        db_session.add(user)
        try:
            db_session.commit()
        except IntegrityError:
            # The unique constraint also protects against simultaneous registrations.
            db_session.rollback()
            return jsonify(error="Username already exists."), 409

        return jsonify(
            message="User created. You can now log in.",
            user={"id": user.id, "username": user.username, "role": user.role},
        ), 201

@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a JSON object with username and password."), 400

    username = data.get("username")
    password = data.get("password")
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or not username
        or not password
    ):
        return jsonify(error="Username and password must be non-empty strings."), 400

    with SessionLocal() as db_session:
        user = db_session.scalar(select(User).where(User.username == username).with_for_update())
        if user is None or not check_password_hash(user.password_hash, password):
            return jsonify(error="Invalid username or password."), 401

        session.clear()
        session["user_id"] = user.id
        session["tracking_key"] = str(uuid4())
        session.permanent = True
        # One active login per user avoids counting overlapping browser sessions.
        state = db_session.get(TrackingState, user.id)
        if state is None:
            state = TrackingState(user_id=user.id)
            db_session.add(state)
        state.login_key = session["tracking_key"]
        state.page = state.view_key = state.last_seen = None
        state.sequence = 0
        db_session.commit()
        return jsonify(
            message="Logged in.",
            user={"id": user.id, "username": user.username, "role": user.role},
        )

@bp.route("/logout", methods=["POST"])
def logout():
    with SessionLocal() as db_session:
        user = db_session.scalar(select(User).where(User.id == session.get("user_id")).with_for_update())
        state = db_session.get(TrackingState, user.id) if user else None
        if state and state.login_key == session.get("tracking_key"):
            confirm_time(db_session, state, utcnow(), current_app.config["TRACKING_TIMEOUT_SECONDS"])
            db_session.delete(state)
            db_session.commit()
    session.clear()
    return jsonify(message="Logged out.")
