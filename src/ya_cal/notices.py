"""Durable handoff between a CalDAV write and Ya-Mail's idempotent SMTP outbox."""

import json
from copy import deepcopy
from email import policy
from email.message import EmailMessage
from email.utils import formatdate
from uuid import uuid4

from icalendar import Calendar
from ya_mail import accounts as mail_accounts
from ya_mail import outbox
from ya_mail.accounts import Problem, address

from .accounts import database
from .events import CHANGE, people, put


def invitation(cal, events, method, recipient):
    message = Calendar()
    message.add("VERSION", "2.0")
    message.add("PRODID", "-//Grebennikov//Ya-Ca//RU")
    message.add("METHOD", method)
    for component in cal.walk("VTIMEZONE"):
        message.add_component(deepcopy(component))
    for original in events:
        event = deepcopy(original)
        event.subcomponents.clear()
        for key in list(event):
            if key not in {
                "UID",
                "DTSTAMP",
                "SEQUENCE",
                "DTSTART",
                "DTEND",
                "DURATION",
                "SUMMARY",
                "DESCRIPTION",
                "LOCATION",
                "ORGANIZER",
                "ATTENDEE",
                "STATUS",
                "RRULE",
                "EXDATE",
                "RDATE",
                "RECURRENCE-ID",
                "TRANSP",
                "URL",
                "CLASS",
            }:
                del event[key]
        attendees = people(event)
        event.pop("ATTENDEE", None)
        for email, person in attendees.items():
            if method == "CANCEL" and email != recipient:
                continue
            person.params.pop("SCHEDULE-AGENT", None)
            person.params.pop("SCHEDULE-STATUS", None)
            event.add("ATTENDEE", person)
        if method == "CANCEL":
            put(event, "STATUS", "CANCELLED")
        event["ORGANIZER"].params.pop("SCHEDULE-AGENT", None)
        message.add_component(event)
    message.add_missing_timezones()
    return message.to_ical()


def stage(email, key, resource, change, notices):
    with database() as db:
        for method, recipient, payload in notices:
            db.execute(
                "INSERT INTO notices VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                (
                    uuid4().hex,
                    email,
                    key,
                    resource,
                    change,
                    address(recipient),
                    method,
                    payload,
                    "prepared",
                ),
            )


def ready(email, key, resource, change):
    with database() as db:
        db.execute(
            """UPDATE notices SET state='ready' WHERE email=? AND calendar=? AND event=?
                      AND change_id=? AND state='prepared'""",
            (email, key, resource, change),
        )


def save_change(store, key, resource, document, etag, change, messages):
    from .dav import Rejected

    email = store.account.email
    if messages:
        stage(email, key, resource, change, messages)
    try:
        store.write(key, resource, document, etag)
    except Rejected:
        with database() as db:
            db.execute(
                "DELETE FROM notices WHERE email=? AND change_id=? AND state='prepared'",
                (email, change),
            )
        raise
    if messages:
        ready(email, key, resource, change)


def batch_info(email, change):
    with database() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT id,method,recipient,state FROM notices WHERE email=? AND change_id=? ORDER BY rowid",
                (email, change),
            )
        ]


def pending(email):
    with database() as db:
        return [
            dict(r)
            for r in db.execute(
                """SELECT id,calendar,event,change_id,recipient,method,state
                    FROM notices WHERE email=? AND state NOT IN ('accepted','superseded')
                    ORDER BY rowid""",
                (email,),
            )
        ]


def discard_unconfirmed(store, change):
    """Manual recovery after an ambiguous CalDAV write; never discard an SMTP reservation."""
    email = store.account.email
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            "SELECT * FROM notices WHERE email=? AND change_id=?", (email, change)
        ).fetchall()
        if not rows or any(r["state"] != "prepared" for r in rows):
            raise Problem(
                "Можно снять только неподтверждённую запись CalDAV до начала рассылки."
            )
        row = rows[0]
        found = store.get(row["calendar"], row["event"])
        if (not found and change.startswith("del-")) or (
            found
            and any(str(e.get(CHANGE, "")) == change for e in found[0].walk("VEVENT"))
        ):
            raise Problem(
                "Изменение подтверждено календарём. Используйте send_notifications."
            )
        db.execute(
            "UPDATE notices SET state='superseded',payload=NULL WHERE email=? AND change_id=?",
            (email, change),
        )
    return {"discarded": len(rows)}


def dispatch(store, change):
    email = store.account.email
    with database() as db:
        rows = db.execute(
            "SELECT rowid,* FROM notices WHERE email=? AND change_id=? ORDER BY rowid",
            (email, change),
        ).fetchall()
    if not rows:
        raise Problem("Для этого аккаунта такая рассылка не найдена.")
    if any(r["state"] == "superseded" for r in rows):
        raise Problem("Неподтверждённая рассылка снята владельцем.")
    if any(r["state"] == "prepared" for r in rows):
        found = store.get(rows[0]["calendar"], rows[0]["event"])
        # A physical deletion is staged with a del- prefix. A failed precondition
        # never confirms a live event, even if its time/title happen to match.
        if (not found and change.startswith("del-")) or (
            found
            and any(str(ev.get(CHANGE, "")) == change for ev in found[0].walk("VEVENT"))
        ):
            ready(email, rows[0]["calendar"], rows[0]["event"], change)
        else:
            raise Problem(
                "Запись CalDAV не подтверждена. Отправка приглашений приостановлена."
            )
    account = mail_accounts.current(email, "send")
    results = []
    for row in rows:
        if row["receipt"]:
            results.append(json.loads(row["receipt"]))
            continue
        with database() as db:
            earlier = db.execute(
                """SELECT change_id FROM notices WHERE email=? AND calendar=? AND event=?
                    AND recipient=? AND rowid<? AND state IN ('ready','prepared') ORDER BY rowid LIMIT 1""",
                (email, row["calendar"], row["event"], row["recipient"], row["rowid"]),
            ).fetchone()
        if earlier:
            raise Problem("Сначала обработайте предыдущую рассылку: " + earlier[0])
        payload = row["payload"]
        event = Calendar.from_ical(payload).walk("VEVENT")[0]
        msg = EmailMessage(policy=policy.SMTP)
        msg["From"] = email
        msg["To"] = row["recipient"]
        msg["Date"] = formatdate(localtime=True)
        title = " ".join(str(event.get("SUMMARY", "")).splitlines())
        verb = {
            "CANCEL": "Отмена встречи",
            "REQUEST": "Приглашение на встречу",
            "REPLY": "Ответ на приглашение",
        }[row["method"]]
        msg["Subject"] = f"{verb}: {title}"
        msg.set_content(
            f"{verb}: {title}\nНачало: {event.decoded('DTSTART').isoformat()}\n"
            f"Место: {event.get('LOCATION', '')}\n{event.get('DESCRIPTION', '')}"
        )
        msg.add_alternative(
            payload.decode(), subtype="calendar", params={"method": row["method"]}
        )
        receipt = outbox.submit(account, "ya-cal:" + row["id"], payload, msg)
        state = "accepted" if row["recipient"] in receipt["accepted"] else "refused"
        with database() as db:
            db.execute(
                "UPDATE notices SET state=?,receipt=?,payload=NULL WHERE id=?",
                (state, json.dumps(receipt), row["id"]),
            )
        results.append(receipt)
    return {"change_id": change, "smtp": results}
