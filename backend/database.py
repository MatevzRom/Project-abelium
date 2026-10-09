"""Database connection, schema initialization, and First User seeding."""
import os

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from models import Base, User

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
