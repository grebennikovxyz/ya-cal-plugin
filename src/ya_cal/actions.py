import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from ya_mail.accounts import Problem

from . import notices
from .accounts import timezone
from .events import (
    CHANGE,
    MANAGED,
    edit,
    email_of,
    event_data,
    make_event,
    master,
    occurrence,
    people,
    put,
)
from .schedule import check

CREATE = "X-YA-CAL-CREATE-DIGEST"
CREATED_BY = "X-YA-CAL-CREATE-CHANGE"


def read(store, key, resource):
    found = store.get(key, resource)
    if not found:
        raise Problem("Событие не найдено.")
    return found


def version(store, key, resource, expected):
    doc, etag = read(store, key, resource)
    if (
        not etag
        or not (etag.startswith('"') and etag.endswith('"'))
        or etag != expected
    ):
        raise Problem(
            "Для изменения перечитайте событие и используйте его текущий сильный ETag."
        )
    for event in doc.walk("VEVENT"):
        if CHANGE in event:
            notices.ready(store.account.email, key, resource, str(event[CHANGE]))
    return doc, etag


def detail(store, key, resource):
    doc, etag = read(store, key, resource)
    zone = timezone(store.account.timezone)
    return {
        "calendar_id": key,
        "event_id": resource,
        "etag": etag,
        "events": [event_data(e, zone) for e in doc.walk("VEVENT")],
    }


def owner(ev, email):
    organizer = email_of(ev.get("ORGANIZER", ""))
    if organizer and organizer != email:
        raise Problem(
            "Встречу меняет её организатор. Для своего участия используйте respond_to_event."
        )
    if people(ev) and not organizer:
        raise Problem(
            "Встреча без адреса организатора. Проверьте её в Яндекс Календаре."
        )


def handoff(
    store,
    key,
    resource,
    doc,
    ev,
    old,
    *,
    etag=None,
    delete=False,
    cancel=False,
    single=False,
    change=None,
):
    change = change or (("del-" if delete else "") + uuid4().hex)
    put(ev, CHANGE, change)
    messages = []
    selected = [ev] if single else [ev, *(e for e in doc.walk("VEVENT") if e is not ev)]
    selected = [e for e in selected if str(e.get(MANAGED, "")) == "1"]
    managed = bool(selected)
    if managed:
        prior = people(old) if old is not None else {}
        invited = {guest for item in selected for guest in people(item)}
        for guest in sorted(invited | set(prior)):
            method = "CANCEL" if cancel or guest not in invited else "REQUEST"
            items = [e for e in selected if guest in people(e)]
            if guest not in invited:
                removed = deepcopy(ev)
                removed.add("ATTENDEE", prior[guest])
                items = [removed]
            messages.append(
                (method, guest, notices.invitation(doc, items, method, guest))
            )
    email = store.account.email
    if not delete:
        doc.add_missing_timezones()
    notices.save_change(
        store, key, resource, None if delete else doc, etag, change, messages
    )
    return {
        "saved": True,
        "deleted": delete,
        "event_id": resource,
        "calendar_id": key,
        "change_id": change,
        "notifications": notices.batch_info(email, key, resource, change)
        if messages
        else [],
        "scheduling": "ya-mail" if managed else ("provider" if people(ev) else "none"),
    }


def create(store, key, request_id, fields, allow_conflicts):
    store.collection(key)
    resource = str(request_id) + ".ics"
    digest = hashlib.sha256(fields.model_dump_json().encode()).hexdigest()
    found = store.get(key, resource)
    if found:
        ev = master(found[0])
        if str(ev.get(CREATE, "")) != digest:
            raise Problem("Ключ создания уже занят другим событием.")
        change = str(ev[CREATED_BY])
        if str(ev.get(CHANGE, "")) == change:
            notices.ready(store.account.email, key, resource, change)
        return {
            "saved": True,
            "already_exists": True,
            "calendar_id": key,
            "event_id": resource,
            "etag": found[1],
            "change_id": change,
            "notifications": notices.batch_info(
                store.account.email, key, resource, change
            ),
        }
    zone = timezone(store.account.timezone)
    doc = make_event(fields, store.account.email, str(request_id) + "@ya-cal", zone)
    ev = master(doc)
    change = uuid4().hex
    put(ev, CREATE, digest)
    put(ev, CREATED_BY, change)
    checked = check(store, key, resource, doc, ev, zone, False)
    if checked["conflicts"] and not allow_conflicts:
        return {"saved": False, **checked}
    return {**handoff(store, key, resource, doc, ev, None, change=change), **checked}


def select_event(doc, scope, rid, zone):
    if scope == "occurrence":
        if not rid:
            raise Problem(
                "Для изменения одного повторения передайте recurrence_id из повестки."
            )
        return occurrence(doc, rid, zone)
    if rid:
        raise Problem("Для recurrence_id выберите scope=occurrence.")
    if scope == "event" and any(k in master(doc) for k in ("RRULE", "RDATE")):
        raise Problem("Укажите область изменения повторения: series или occurrence.")
    return master(doc)


def advance(doc, ev):
    put(ev, "SEQUENCE", max(int(e.get("SEQUENCE", 0)) for e in doc.walk("VEVENT")) + 1)
    put(ev, "DTSTAMP", datetime.now(UTC))


def update(store, key, resource, expected, fields, scope, rid, allow_conflicts):
    doc, etag = version(store, key, resource, expected)
    zone = timezone(store.account.timezone)
    ev = select_event(doc, scope, rid, zone)
    owner(ev, store.account.email)
    old = deepcopy(ev)
    edit(ev, fields, store.account.email, zone)
    if ev.to_ical() == old.to_ical():
        return {"saved": True, "unchanged": True, "etag": etag, "notifications": []}
    if fields.model_fields_set <= {"tags", "reminders_minutes"}:
        store.write(key, resource, doc, etag)
        return {
            "saved": True,
            "event_id": resource,
            "calendar_id": key,
            "notifications": [],
        }
    checked = {}
    if any(v is not None for v in (fields.start, fields.end, fields.busy)):
        checked = check(
            store, key, resource, doc, ev, zone, scope == "occurrence", whole=True
        )
        if checked["conflicts"] and not allow_conflicts:
            return {"saved": False, **checked}
    advance(doc, ev)
    return {
        **handoff(
            store, key, resource, doc, ev, old, etag=etag, single=scope == "occurrence"
        ),
        **checked,
    }


def delete(store, key, resource, expected, scope, rid):
    doc, etag = version(store, key, resource, expected)
    ev = select_event(doc, scope, rid, timezone(store.account.timezone))
    owner(ev, store.account.email)
    advance(doc, ev)
    single = scope == "occurrence"
    put(ev, "STATUS", "CANCELLED")
    return handoff(
        store,
        key,
        resource,
        doc,
        ev,
        None,
        etag=etag,
        delete=not single,
        cancel=True,
        single=single,
    )


def respond(store, key, resource, expected, answer):
    doc, etag = version(store, key, resource, expected)
    ev = master(doc)
    email = store.account.email
    guest = people(ev).get(email)
    if guest is None or email_of(ev.get("ORGANIZER", "")) in ("", email):
        raise Problem("Аккаунт должен быть приглашённым участником этой встречи.")
    if guest.params.get("PARTSTAT") == answer:
        change = str(ev.get(CHANGE, ""))
        return {
            "saved": True,
            "unchanged": True,
            "status": answer,
            "change_id": change,
            "notifications": notices.batch_info(email, key, resource, change),
        }
    guest.params["PARTSTAT"] = answer
    guest.params["RSVP"] = "FALSE"
    agent = str(ev["ORGANIZER"].params.get("SCHEDULE-AGENT", "SERVER")).upper()
    if agent == "CLIENT":
        change = uuid4().hex
        put(ev, CHANGE, change)
        reply = deepcopy(ev)
        put(reply, "DTSTAMP", datetime.now(UTC))
        put(reply, "ATTENDEE", deepcopy(guest))
        recipient = email_of(ev["ORGANIZER"])
        payload = notices.invitation(doc, [reply], "REPLY", recipient)
        notices.save_change(
            store, key, resource, doc, etag, change, [("REPLY", recipient, payload)]
        )
        return {
            "saved": True,
            "status": answer,
            "scheduling": "ya-mail",
            "change_id": change,
            "notifications": notices.batch_info(email, key, resource, change),
        }
    store.write(key, resource, doc, etag)
    return {
        "saved": True,
        "status": answer,
        "scheduling": "provider" if agent == "SERVER" else "none",
    }
