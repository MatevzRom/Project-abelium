import os

from flask import Flask
from sqlalchemy import create_engine, text

app = Flask(__name__)
engine = create_engine(os.environ["DATABASE_URL"])


@app.route("/")
def index():
    # Smoke test: proves the backend container can reach the db container.
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
    return f"Backend is up. DB says: {version}"


if __name__ == "__main__":
    # host 0.0.0.0 is required so the browser can reach Flask from outside the container
    app.run(host="0.0.0.0", port=5000, debug=True)
