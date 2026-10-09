"""Flask configuration and application entry point."""
import os
from datetime import timedelta
from pathlib import Path

from flask import Flask

from database import init_db
from routes.auth import bp as auth_routes
from routes.pages import bp as page_routes
from routes.tracking import bp as tracking_routes
from routes.users import bp as user_routes

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app = Flask(
    __name__,
    template_folder=str(frontend_dir / "templates"),
    static_folder=str(frontend_dir / "static"),
)
app.config.update(
    SECRET_KEY=os.environ["FLASK_SECRET_KEY"],
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Enable this when serving the app over HTTPS.
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_COOKIE_SECURE", "false").lower() == "true",
    TRACKING_HEARTBEAT_SECONDS=int(os.environ.get("TRACKING_HEARTBEAT_SECONDS", "5")),
    TRACKING_TIMEOUT_SECONDS=int(os.environ.get("TRACKING_TIMEOUT_SECONDS", "15")),
)
if not 0 < app.config["TRACKING_HEARTBEAT_SECONDS"] < app.config["TRACKING_TIMEOUT_SECONDS"]:
    raise ValueError("Tracking timeout must be greater than the positive heartbeat interval.")

init_db()
for blueprint in (auth_routes, page_routes, tracking_routes, user_routes):
    app.register_blueprint(blueprint)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
