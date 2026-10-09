"""Application pages and the independent development users view."""
from flask import Blueprint, current_app, redirect, render_template, render_template_string, session, url_for
from sqlalchemy import select

from database import SessionLocal
from models import User

bp = Blueprint("pages", __name__)

@bp.route("/")
def index():
    return redirect(url_for("pages.show_page", page_name="home"))

@bp.route("/pages/<page_name>")
def show_page(page_name):
    pages = {
        "home": ("Home", "Welcome to your time-tracking app.",
                 "Use the navigation buttons to explore the three pages."),
        "content": ("Content", "A little space to learn.",
                    "Taking regular breaks can help you stay focused. Try a short walk between study sessions."),
        "statistics": ("Statistics", "Your time on each page.",
                       "Saved time updates automatically while you browse."),
    }
    if page_name not in pages:
        return "Page not found.", 404
    with SessionLocal() as db_session:
        user_id = session.get("user_id")
        user = db_session.get(User, user_id) if isinstance(user_id, int) else None
        if user is None:
            session.clear()
            return redirect(url_for("auth.login_page"))
        title, heading, description = pages[page_name]
        return render_template(
            "page.html", page_name=page_name, title=title,
            heading=heading, description=description, user=user,
            heartbeat_seconds=current_app.config["TRACKING_HEARTBEAT_SECONDS"],
        )

@bp.route("/debug/users")
def debug_users():
    with SessionLocal() as session:
        users = session.scalars(select(User).order_by(User.id)).all()
    return render_template_string(
        """
        <table border="1" cellpadding="6">
          <tr><th>id</th><th>username</th><th>role</th><th>created (UTC)</th></tr>
          {% for u in users %}
          <tr><td>{{ u.id }}</td><td>{{ u.username }}</td>
              <td>{{ u.role }}</td><td>{{ u.created_at }}</td></tr>
          {% endfor %}
        </table>
        """,
        users=users,
    )
