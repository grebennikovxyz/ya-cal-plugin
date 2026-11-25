import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from platformdirs import user_data_path
from ya_mail.accounts import Problem, address, vault

DATA = user_data_path("YaCalPlugin", "Grebennikov")
SERVICE = "org.grebennikov.ya-cal"
Group = Literal["work", "personal", "community", "other"]


@dataclass(frozen=True)
class Account:
    email: str
    mode: Literal["read", "write"]
    timezone: str
    password: str = field(repr=False)


def timezone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise Problem("Укажите часовой пояс IANA, например Europe/Moscow.") from None


@contextmanager
def database():
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "calendar.sqlite3", timeout=35)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS accounts(
                email TEXT PRIMARY KEY, mode TEXT NOT NULL, timezone TEXT NOT NULL, secret TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS prefs(
                email TEXT REFERENCES accounts ON DELETE CASCADE, calendar TEXT, category TEXT,
                priority INTEGER, PRIMARY KEY(email,calendar));
            CREATE TABLE IF NOT EXISTS notices(
                id TEXT PRIMARY KEY, email TEXT REFERENCES accounts ON DELETE CASCADE,
                calendar TEXT, event TEXT, change_id TEXT, recipient TEXT, method TEXT,
                payload BLOB, state TEXT NOT NULL, receipt TEXT);
        """)
        with db:
            yield db
    finally:
        db.close()


def profiles():
    with database() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT email,mode,timezone FROM accounts ORDER BY email"
            )
        ]


def save(acc):
    backend = vault()
    key = uuid4().hex
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        old = db.execute(
            "SELECT secret FROM accounts WHERE email=?", (acc.email,)
        ).fetchone()
        backend.set_password(
            SERVICE, key, json.dumps([acc.email, acc.mode, acc.timezone, acc.password])
        )
        try:
            db.execute(
                """INSERT INTO accounts VALUES (?,?,?,?) ON CONFLICT(email)
                        DO UPDATE SET mode=excluded.mode,timezone=excluded.timezone,secret=excluded.secret""",
                (acc.email, acc.mode, acc.timezone, key),
            )
            db.commit()
        except Exception:
            backend.delete_password(SERVICE, key)
            raise
    if old:
        backend.delete_password(SERVICE, old["secret"])


def current(email, write=False):
    email = address(email).lower()
    with database() as db:
        db.execute("BEGIN")
        row = db.execute(
            "SELECT secret FROM accounts WHERE email=?", (email,)
        ).fetchone()
        data = row and vault().get_password(SERVICE, row["secret"])
    if not data:
        raise Problem("Подключите аккаунт командой ya-ca connect.")
    acc = Account(*json.loads(data))
    if (
        acc.email != email
        or acc.mode not in ("read", "write")
        or (write and acc.mode != "write")
    ):
        raise Problem(
            "Для записи выберите режим редактирования в мастере ya-ca connect."
        )
    return acc


def forget(email):
    email = address(email).lower()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT secret FROM accounts WHERE email=?", (email,)
        ).fetchone()
        if row:
            backend = vault()
            if backend.get_password(SERVICE, row["secret"]) is not None:
                backend.delete_password(SERVICE, row["secret"])
            db.execute("DELETE FROM accounts WHERE email=?", (email,))


def preferences(email):
    with database() as db:
        return {
            r["calendar"]: (r["category"], r["priority"])
            for r in db.execute("SELECT * FROM prefs WHERE email=?", (email,))
        }


def configure(email, calendar, category, priority):
    with database() as db:
        db.execute(
            "INSERT OR REPLACE INTO prefs VALUES (?,?,?,?)",
            (email, calendar, category, priority),
        )
