"""Heartbeat and statistics HTTP endpoints."""
from uuid import UUID

from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy import select

from database import SessionLocal
from models import TrackingState, User
from services.tracking import PAGES, confirm_time, totals_for, utcnow

bp = Blueprint("tracking", __name__)


@bp.route("/api/tracking", methods=["POST"])
def tracking_update():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a JSON object."), 400
    action, page = data.get("action"), data.get("page")
    view_key, sequence = data.get("view_key"), data.get("sequence")
    if action not in ("start", "heartbeat", "stop") or page not in PAGES:
        return jsonify(error="Invalid tracking action or page."), 400
    try:
        UUID(view_key)
    except (ValueError, TypeError, AttributeError):
        return jsonify(error="Invalid view key."), 400
    if type(sequence) is not int or sequence < 1:
        return jsonify(error="Sequence must be a positive integer."), 400

    with SessionLocal() as db:
        user_id = session.get("user_id")
        user = db.scalar(select(User).where(User.id == user_id).with_for_update())
        state = db.get(TrackingState, user_id) if user else None
        if not state or state.login_key != session.get("tracking_key"):
            return jsonify(error="Login required. Please log in again."), 401
        now = utcnow()
        if action == "start":
            # A new visible period never fills in an unconfirmed hidden gap.
            if state.view_key != view_key:
                state.view_key, state.page = view_key, page
                state.sequence, state.last_seen = sequence, now
        elif state.view_key == view_key and state.page == page and sequence > state.sequence:
            confirm_time(db, state, now, current_app.config["TRACKING_TIMEOUT_SECONDS"])
            state.sequence, state.last_seen = sequence, now
            if action == "stop":
                state.page = None
        db.flush()
        totals = totals_for(db, user_id)
        active = state.page == page and state.view_key == view_key
        db.commit()
        return jsonify(totals=totals, active=active)

@bp.route("/api/statistics")
def statistics():
    with SessionLocal() as db:
        user = db.get(User, session.get("user_id")) if session.get("user_id") else None
        state = db.get(TrackingState, user.id) if user else None
        if user is None or state is None or state.login_key != session.get("tracking_key"):
            return jsonify(error="Login required."), 401
        users = db.scalars(select(User).order_by(User.id)).all() if user.role == "admin" else [user]
        return jsonify(viewer_role=user.role, users=[
            {"id": item.id, "username": item.username, "role": item.role,
             "is_protected": item.is_protected,
             "totals": totals_for(db, item.id)} for item in users
        ])
