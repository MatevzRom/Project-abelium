"""Server-clock accounting. Only confirmed, visible activity adds to totals."""
from datetime import datetime, timezone

from sqlalchemy import select

from models import PageTime

PAGES = ("home", "content", "statistics")


def utcnow():
    return datetime.now(timezone.utc)


def elapsed_since(value, now):
    # SQLite test databases return naive datetimes; PostgreSQL returns aware ones.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, (now - value).total_seconds())


def confirm_time(db, state, now, timeout):
    if state.page and state.last_seen:
        elapsed = elapsed_since(state.last_seen, now)
        if elapsed <= timeout:
            total = db.get(PageTime, (state.user_id, state.page))
            if total is None:
                total = PageTime(user_id=state.user_id, page=state.page, seconds=0)
                db.add(total)
            total.seconds += elapsed


def totals_for(db, user_id):
    totals = dict.fromkeys(PAGES, 0)
    for item in db.scalars(select(PageTime).where(PageTime.user_id == user_id)):
        totals[item.page] = round(item.seconds, 3)
    return totals
