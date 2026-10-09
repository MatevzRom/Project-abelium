# import os

# from flask import Flask
# from sqlalchemy import create_engine, text

# app = Flask(__name__)
# engine = create_engine(os.environ["DATABASE_URL"])


# @app.route("/")
# def index():
#     # Smoke test: proves the backend container can reach the db container.
#     with engine.connect() as conn:
#         version = conn.execute(text("SELECT version()")).scalar()
#     return f"Backend is up. DB says: {version}"


# if __name__ == "__main__":
#     # host 0.0.0.0 is required so the browser can reach Flask from outside the container
#     app.run(host="0.0.0.0", port=5000, debug=True)


import os

from datetime import timedelta

from flask import Flask, jsonify, render_template_string, request, session
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash
from models import Base, User

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Enable this when serving the app over HTTPS.
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_COOKIE_SECURE", "false").lower() == "true",
)
engine = create_engine(os.environ["DATABASE_URL"])
SessionLocal = sessionmaker(bind=engine)


def init_db():
    # Create any tables that don't exist yet (does nothing if they do)
    Base.metadata.create_all(engine)

    # Seed the first admin, but only if the users table is empty
    with SessionLocal() as session:
        user_count = session.scalar(select(func.count()).select_from(User))
        if user_count == 0:
            session.add(
                User(
                    username=os.environ["ADMIN_USERNAME"],
                    password_hash=generate_password_hash(os.environ["ADMIN_PASSWORD"]),
                    role="admin",
                )
            )
            session.commit()
            print("Seeded admin user", flush=True)


init_db()


@app.route("/")
def index():
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
    return f"Backend is up. DB says: {version}"

@app.route("/login", methods=["POST"])
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
        user = db_session.scalar(select(User).where(User.username == username))
        if user is None or not check_password_hash(user.password_hash, password):
            return jsonify(error="Invalid username or password."), 401

        session.clear()
        session["user_id"] = user.id
        session.permanent = True
        return jsonify(
            message="Logged in.",
            user={"id": user.id, "username": user.username, "role": user.role},
        )


@app.route("/debug/users")
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
