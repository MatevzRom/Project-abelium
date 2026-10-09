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
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
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

    # create_all does not add columns to existing tables. Migrate the original
    # schema once, protecting ID 1 (the account seeded by this application).
    with engine.begin() as conn:
        columns = {column["name"] for column in inspect(conn).get_columns("users")}
        if "is_protected" not in columns:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN is_protected BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            first_user = conn.execute(text("SELECT role FROM users WHERE id = 1")).first()
            if first_user is not None:
                if first_user.role != "admin":
                    raise RuntimeError("Original account ID 1 must be an admin before migration.")
                conn.execute(text("UPDATE users SET is_protected = TRUE WHERE id = 1"))
            elif conn.execute(text("SELECT COUNT(*) FROM users")).scalar():
                raise RuntimeError("Original account ID 1 is missing; cannot identify First User.")

    # Seed the first admin, but only if the users table is empty
    with SessionLocal() as session:
        user_count = session.scalar(select(func.count()).select_from(User))
        if user_count == 0:
            session.add(
                User(
                    username=os.environ["ADMIN_USERNAME"],
                    password_hash=generate_password_hash(os.environ["ADMIN_PASSWORD"]),
                    role="admin",
                    is_protected=True,
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

@app.route("/register", methods=["POST"])
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


def check_admin(db_session):
    user_id = session.get("user_id")
    current_user = db_session.get(User, user_id) if isinstance(user_id, int) else None
    if current_user is None:
        session.clear()
        return jsonify(error="Login required."), 401
    if current_user.role != "admin":
        return jsonify(error="Admin access required."), 403
    return None


@app.route("/users/<int:user_id>/promote", methods=["POST"])
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


@app.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    with SessionLocal() as db_session:
        db_session.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
        error = check_admin(db_session)
        if error is not None:
            return error
        user = db_session.get(User, user_id)
        if user is None:
            return jsonify(error="User not found."), 404
        if user.is_protected:
            return jsonify(error="Cannot delete the protected First User account."), 409
        db_session.delete(user)
        db_session.commit()
        if session.get("user_id") == user_id:
            session.clear()
        return jsonify(message="User deleted.", user_id=user_id)


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
