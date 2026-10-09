"""Run from /app: python -m unittest discover -s tests -v.

Uses an isolated SQLite database and a controlled server clock, never live users.
"""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["FLASK_SECRET_KEY"] = "isolated-test-secret"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["TRACKING_HEARTBEAT_SECONDS"] = "5"
os.environ["TRACKING_TIMEOUT_SECONDS"] = "15"

import app as module
from models import Base, PageTime, TrackingState
from sqlalchemy import event


@event.listens_for(module.engine, "before_cursor_execute", retval=True)
def skip_postgres_lock(conn, cursor, statement, parameters, context, executemany):
    if statement.startswith("LOCK TABLE"):
        return "SELECT 1", ()
    return statement, parameters


class TrackingTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(module.engine)
        module.init_db()
        self.client = module.app.test_client()
        self.client.post("/login", json={"username": "test-admin", "password": "test-password"})
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.clock = patch("tracking.utcnow", side_effect=lambda: self.now)
        self.logout_clock = patch("app.utcnow", side_effect=lambda: self.now)
        self.clock.start()
        self.logout_clock.start()
        self.addCleanup(self.clock.stop)
        self.addCleanup(self.logout_clock.stop)
        self.key = str(uuid4())
        self.sequence = 0

    def send(self, action, page="home", client=None, key=None):
        self.sequence += 1
        return (client or self.client).post("/api/tracking", json={
            "action": action, "page": page, "view_key": key or self.key,
            "sequence": self.sequence,
        })

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)

    def test_navigation_pause_and_lost_stop(self):
        self.send("start")
        self.advance(5)
        self.assertEqual(self.send("heartbeat").json["totals"]["home"], 5)
        self.advance(2)
        self.assertEqual(self.send("stop").json["totals"]["home"], 7)
        self.key = str(uuid4())
        self.send("start", "content")
        self.advance(5)
        self.send("heartbeat", "content")
        # Resume after 10 hidden seconds, with the stop message lost.
        self.advance(10)
        self.key = str(uuid4())
        self.send("start", "content")
        self.advance(5)
        totals = self.send("heartbeat", "content").json["totals"]
        self.assertEqual(totals, {"home": 7, "content": 10, "statistics": 0})

    def test_timeout_and_reordered_messages(self):
        self.send("start")
        self.advance(5)
        self.send("heartbeat")
        self.advance(20)
        self.assertEqual(self.send("heartbeat").json["totals"]["home"], 5)
        self.advance(5)
        self.assertEqual(self.send("heartbeat").json["totals"]["home"], 10)
        stale = self.client.post("/api/tracking", json={
            "action": "stop", "page": "home", "view_key": self.key, "sequence": 2,
        })
        self.assertTrue(stale.json["active"])
        old_key = self.key
        self.key = str(uuid4())
        self.send("start", "content")
        self.advance(3)
        self.assertFalse(self.send("stop", key=old_key).json["active"])
        self.assertEqual(self.send("heartbeat", "content").json["totals"]["content"], 3)

    def test_logout_and_relogin_preserve_totals_revoke_old_cookie(self):
        self.send("start")
        self.advance(4)
        old_cookie = self.client.get_cookie("session").value
        self.client.post("/logout")
        thief = module.app.test_client()
        thief.set_cookie("session", old_cookie)
        self.assertEqual(self.send("heartbeat", client=thief).status_code, 401)
        self.assertEqual(thief.get("/api/statistics").status_code, 401)
        self.assertEqual(thief.post("/users/1/promote").status_code, 401)
        self.client.post("/login", json={"username": "test-admin", "password": "test-password"})
        self.advance(100)
        self.key = str(uuid4())
        self.send("start")
        self.advance(5)
        self.assertEqual(self.send("heartbeat").json["totals"]["home"], 9)

    def test_access_control_and_debug_exclusion(self):
        regular = module.app.test_client()
        uid = regular.post("/register", json={"username": "alice", "password": "alice-password"}).json["user"]["id"]
        regular.post("/login", json={"username": "alice", "password": "alice-password"})
        self.assertEqual(len(regular.get("/api/statistics").json["users"]), 1)
        self.assertEqual(len(self.client.get("/api/statistics").json["users"]), 2)
        self.assertEqual(self.send("start", page="/debug/users").status_code, 400)
        self.assertEqual(regular.get("/debug/users").status_code, 200)
        self.assertEqual(regular.post("/users/1/promote").status_code, 403)
        self.send("start", client=regular)
        self.advance(5)
        self.send("heartbeat", client=regular)
        self.assertEqual(self.client.delete(f"/users/{uid}").status_code, 200)
        with module.SessionLocal() as db:
            self.assertIsNone(db.get(TrackingState, uid))
            self.assertIsNone(db.get(PageTime, (uid, "home")))


if __name__ == "__main__":
    unittest.main()
