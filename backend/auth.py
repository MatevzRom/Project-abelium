"""Shared authorization checks for protected user-management routes."""
from flask import jsonify, session

from models import TrackingState, User


def check_admin(db_session):
    user_id = session.get("user_id")
    current_user = db_session.get(User, user_id) if isinstance(user_id, int) else None
    state = db_session.get(TrackingState, user_id) if current_user else None
    if current_user is None or state is None or state.login_key != session.get("tracking_key"):
        session.clear()
        return jsonify(error="Login required."), 401
    if current_user.role != "admin":
        return jsonify(error="Admin access required."), 403
    return None
