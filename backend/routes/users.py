"""Admin role management and First User account deletion."""
from flask import Blueprint, jsonify, session
from sqlalchemy import delete, text

from auth import check_admin
from database import SessionLocal
from models import PageTime, TrackingState, User

bp = Blueprint("users", __name__)

@bp.route("/users/<int:user_id>/promote", methods=["POST"])
def promote_user(user_id):
    with SessionLocal() as db_session:
        # Serialize admin mutations so authorization remains valid during deletion.
        db_session.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
        error = check_admin(db_session)
        if error is not None:
            return error
        user = db_session.get(User, user_id)
        if user is None:
            return jsonify(error="User not found."), 404
        user.role = "admin"
        db_session.commit()
        return jsonify(
            message="User is now an admin.",
            user={"id": user.id, "username": user.username, "role": user.role},
        )

@bp.route("/users/<int:user_id>/demote", methods=["POST"])
def demote_user(user_id):
    with SessionLocal() as db_session:
        db_session.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
        error = check_admin(db_session)
        if error is not None:
            return error
        user = db_session.get(User, user_id)
        if user is None:
            return jsonify(error="User not found."), 404
        if user.is_protected:
            return jsonify(error="Cannot revoke the protected First User's admin role."), 409
        user.role = "user"
        db_session.commit()
        return jsonify(
            message="Admin role revoked.",
            user={"id": user.id, "username": user.username, "role": user.role},
        )

@bp.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    with SessionLocal() as db_session:
        db_session.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
        error = check_admin(db_session)
        if error is not None:
            return error
        current_user = db_session.get(User, session["user_id"])
        if not current_user.is_protected:
            return jsonify(error="Only First User can delete accounts."), 403
        user = db_session.get(User, user_id)
        if user is None:
            return jsonify(error="User not found."), 404
        if user.is_protected:
            return jsonify(error="Cannot delete the protected First User account."), 409
        db_session.execute(delete(PageTime).where(PageTime.user_id == user_id))
        db_session.execute(delete(TrackingState).where(TrackingState.user_id == user_id))
        db_session.delete(user)
        db_session.commit()
        if session.get("user_id") == user_id:
            session.clear()
        return jsonify(message="User deleted.", user_id=user_id)
