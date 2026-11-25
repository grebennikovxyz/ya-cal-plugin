from contextlib import contextmanager
from copy import deepcopy
from uuid import uuid4

import pytest
from icalendar import Calendar
from ya_mail import accounts as mailbox
from ya_mail.accounts import Problem

from ya_cal import accounts, notices, server
from ya_cal.dav import Rejected
from ya_cal.events import Fields, NewEvent, Repeat, master


class Vault(dict):
    def get_password(self, service, key):
        return self.get((service, key))

    def set_password(self, service, key, value):
        self[service, key] = value

    def delete_password(self, service, key):
        del self[service, key]


class Store:
    def __init__(self, account):
        self.account = account
        self.info = {
            k: {"calendar_id": k, "name": k, "priority": p, "category": k}
            for k, p in (("work", 90), ("personal", 30))
        }
        self.objects = {}
        self.calls = []

    def collection(self, key):
        if key not in self.info:
            raise Problem("calendar")
        return key

    def get(self, key, name):
        return deepcopy(self.objects.get((self.collection(key), name)))

    def query(self, key, lo, hi):
        for (cal, name), (doc, _) in self.objects.items():
            if cal == key:
                yield name, deepcopy(doc)

    def write(self, key, name, doc, etag):
        old = self.get(key, name)
        if (old and old[1] != etag) or (not old and etag):
            raise Rejected("conflict")
        self.calls.append((key, name))
        if doc is None:
            del self.objects[key, name]
        else:
            self.objects[key, name] = (
                Calendar.from_ical(doc.to_ical()),
                f'"{len(self.calls)}"',
            )


@pytest.fixture
def store(monkeypatch, tmp_path):
    vault = Vault()
    monkeypatch.setattr(accounts, "DATA", tmp_path / "cal")
    monkeypatch.setattr(mailbox, "DATA", tmp_path / "mail")
    monkeypatch.setattr(accounts, "vault", lambda: vault)
    monkeypatch.setattr(mailbox, "vault", lambda: vault)
    acct = accounts.Account(
        "organizer@example.org", "write", "Europe/Moscow", "test-only"
    )
    accounts.save(acct)
    st = Store(acct)

    @contextmanager
    def opened(acc):
        assert acc.email == acct.email
        yield st

    monkeypatch.setattr(server, "session", opened)
    return st


def event(**updates):
    return NewEvent(
        **(
            {
                "summary": "Занятие",
                "start": "2031-06-08T10:00:00",
                "end": "2031-06-08T11:00:00",
            }
            | updates
        )
    )


def create(st, key="work", **fields):
    return server.create_event(st.account.email, key, uuid4(), event(**fields))


def ref(st, result):
    key, resource = result["calendar_id"], result["event_id"]
    return (
        st.account.email,
        key,
        resource,
        server.get_event(st.account.email, key, resource)["etag"],
    )


def test_discovery_permissions_and_revoke(store):
    a = store.account.email
    server.configure_calendar(a, "work", "community", 80)
    assert accounts.preferences(a)["work"] == ("community", 80)
    accounts.save(accounts.Account(a, "read", "UTC", "second-secret"))
    assert len(server.list_calendars(a)) == 2
    with pytest.raises(Problem):
        create(store)
    with pytest.raises(Problem):
        server.list_calendars("other@example.org")
    assert b"second-secret" not in (accounts.DATA / "calendar.sqlite3").read_bytes()
    accounts.forget(a)
    assert not accounts.profiles() and not accounts.preferences(a)


def test_conflict_blocks_creation_preserves_etag_and_tags(store):
    a = store.account.email
    first = create(store, tags=["проект", "важно"])
    clash = create(store, "personal", summary="Личное")
    assert clash["saved"] is False and clash["conflicts"][0]["tags"] == [
        "проект",
        "важно",
    ]
    assert len(store.calls) == 1
    start = "2031-06-08"
    found = server.search_events(a, start, "2031-06-09", query="заня", tag="ПРОЕКТ")[
        "events"
    ]
    assert len(found) == 1 and found[0]["event_id"] == first["event_id"]
    args = ref(store, first)
    server.update_event(*args, Fields(location="Зал 2"))
    with pytest.raises(Problem):
        server.delete_event(*args)
    assert len(server.search_events(a, start, "2031-06-09", query="зал")["events"]) == 1
    second = create(store, "personal", start="2031-06-08T11:00", end="2031-06-08T12:00")
    overlapping = server.update_event(
        *ref(store, second), Fields(start="2031-06-08T10:30")
    )
    assert overlapping["saved"] is False
    busy = server.check_availability(a, "2031-06-08T09:00", "2031-06-08T13:00", 60)
    assert len(busy["free"]) == 2 and len(busy["busy"]) == 2


def test_series_overrides_delete_and_all_day(store):
    a = store.account.email
    series = create(
        store,
        start="2031-06-08",
        end="2031-06-09",
        repeat=Repeat(frequency="DAILY", count=3),
    )
    assert series["saved"]
    r = server.search_events(a, "2031-06-08", "2031-06-12")["events"]
    assert len(r) == 3 and r[1]["all_day"]
    with pytest.raises(Problem, match="series"):
        server.delete_event(*ref(store, series))
    server.update_event(
        *ref(store, series),
        Fields(summary="Исключение"),
        "occurrence",
        r[1]["recurrence_id"],
    )
    changed = server.search_events(a, "2031-06-08", "2031-06-12")["events"]
    assert [x["summary"] for x in changed] == ["Занятие", "Исключение", "Занятие"]
    server.delete_event(*ref(store, series), "occurrence", r[1]["recurrence_id"])
    remaining = server.search_events(a, "2031-06-08", "2031-06-12")["events"]
    assert len(remaining) == 2
    assert create(store, "personal", start="2031-06-09", end="2031-06-10")["saved"]
    assert not create(store, "personal", start="2031-06-10", end="2031-06-11")["saved"]
    server.delete_event(*ref(store, series), "series")
    assert len(store.objects) == 1


def test_create_retry_free_and_order(store):
    a = store.account.email
    token = uuid4()
    fields = event(busy=False)
    first = server.create_event(a, "personal", token, fields)
    assert server.create_event(a, "personal", token, fields)["already_exists"]
    with pytest.raises(Problem):
        server.create_event(a, "personal", token, event(summary="Другое"))
    second = create(store, "work")
    page = server.search_events(a, "2031-06-08", "2031-06-09", limit=1)
    assert (
        page["events"][0]["event_id"] == second["event_id"] and page["next_offset"] == 1
    )
    assert first["saved"]


def test_mail_ical_lifecycle_and_retries(store, monkeypatch):
    a, b = "one@example.org", "two@example.org"
    sender = store.account.email
    sent = []

    @contextmanager
    def smtp(_):
        class Client:
            def send_message(self, msg, **kwargs):
                assert msg["From"] == sender
                calendar_part = msg.get_body(preferencelist=("calendar",))
                parsed = Calendar.from_ical(calendar_part.get_content())
                assert parsed["METHOD"] == calendar_part.get_param("method")
                sent.append((kwargs["to_addrs"], parsed))
                return {}

        yield Client()

    monkeypatch.setattr(notices.outbox, "outgoing", smtp)
    meeting = create(
        store, attendees=[a, b], tags=["private-tag"], reminders_minutes=[15]
    )
    assert meeting["scheduling"] == "ya-mail" and len(meeting["notifications"]) == 2
    with pytest.raises(Problem):
        server.send_notifications(sender, meeting["change_id"])
    mailbox.save(mailbox.Account(sender, "send", "dummy"))
    assert server.list_accounts()["accounts"][0]["mail_send"]
    for _ in range(2):
        result = server.send_notifications(sender, meeting["change_id"])
        assert [r["accepted"] for r in result["smtp"]] == [[a], [b]]
    assert len(sent) == 2
    for _, cal in sent:
        assert (
            cal["METHOD"] == "REQUEST"
            and not cal.walk("VALARM")
            and "CATEGORIES" not in master(cal)
        )
        assert (
            master(cal)["SEQUENCE"] == 0
            and "SCHEDULE-AGENT" not in master(cal)["ORGANIZER"].params
        )
    changed = server.update_event(
        *ref(store, meeting), Fields(attendees=[b], summary="Перенос")
    )
    assert {n["method"] for n in changed["notifications"]} == {"CANCEL", "REQUEST"}
    server.send_notifications(sender, changed["change_id"])
    cancel = server.delete_event(*ref(store, meeting))
    server.send_notifications(sender, cancel["change_id"])
    assert not store.objects and not server.list_notifications(sender)
    assert (
        sent[-1][1]["METHOD"] == "CANCEL" and int(master(sent[-1][1])["SEQUENCE"]) == 2
    )


def test_mail_recovers_lost_dav_ack(store, monkeypatch):
    sender = store.account.email
    original = store.write

    def fail(*args):
        original(*args)
        raise OSError("lost response")

    monkeypatch.setattr(store, "write", fail)
    with pytest.raises(OSError):
        create(store, attendees=["guest@example.org"])
    row = server.list_notifications(sender)[0]
    assert row["state"] == "prepared"
    with pytest.raises(Problem):  # mail profile missing, CalDAV write recovered first
        server.send_notifications(sender, row["change_id"])
    assert server.list_notifications(sender)[0]["state"] == "ready"


def test_mail_rejected_write_leaves_no_queue(store, monkeypatch):
    def reject(*_):
        raise Rejected("precondition")

    monkeypatch.setattr(store, "write", reject)
    with pytest.raises(Rejected):
        create(store, attendees=["guest@example.org"])
    assert not server.list_notifications(store.account.email)


def test_origin_and_foreign_meeting(store):
    from ya_cal.dav import child, destination

    for v in [
        "https://other.invalid/x",
        "https://user@caldav.yandex.ru/x",
        "http://caldav.yandex.ru/x",
    ]:
        with pytest.raises(Problem):
            destination(v)
    for v in ["../name", "%2e%2e", "//host", "a%2fb"]:
        with pytest.raises(Problem):
            child("https://caldav.yandex.ru/c/", v)
    item = create(store)
    doc, etag = store.objects["work", item["event_id"]]
    ev = master(doc)
    ev.add("ORGANIZER", "mailto:guest@example.org")
    ev.add("ATTENDEE", "mailto:" + store.account.email)
    with pytest.raises(Problem):
        server.update_event(*ref(store, item), Fields(summary="changed"))
    result = server.respond_to_event(*ref(store, item), "ACCEPTED")
    assert result["scheduling"] == "provider"


def test_client_rsvp_and_incoming_mail(store, monkeypatch):
    from email.message import EmailMessage

    sender = store.account.email
    meeting = create(store)
    doc, etag = store.objects["work", meeting["event_id"]]
    ev = master(doc)
    ev.add(
        "ORGANIZER", "mailto:host@example.org", parameters={"SCHEDULE-AGENT": "CLIENT"}
    )
    ev.add("ATTENDEE", "mailto:" + sender)
    ev.add("ATTENDEE", "mailto:another@example.org")
    result = server.respond_to_event(*ref(store, meeting), "DECLINED")
    assert result["notifications"][0]["recipient"] == "host@example.org"
    assert not server.check_availability(sender, "2031-06-08", "2031-06-09")["busy"]
    with accounts.database() as db:
        data = db.execute(
            "SELECT payload FROM notices WHERE change_id=?", (result["change_id"],)
        ).fetchone()[0]
    invite = Calendar.from_ical(data)
    assert (
        invite["METHOD"] == "REPLY"
        and str(master(invite)["ATTENDEE"]) == "mailto:" + sender
    )
    msg = EmailMessage()
    msg.set_content("Письмо")
    msg.add_attachment(data, maintype="text", subtype="calendar", filename="reply.ics")
    mailbox.save(mailbox.Account(sender, "read", "dummy"))
    from contextlib import nullcontext

    from ya_mail.mail import Ref

    monkeypatch.setattr(server, "mailbox", lambda acc: nullcontext(None))
    monkeypatch.setattr(server, "raw_message", lambda client, ref, account: msg)
    preview = server.read_mail_invitation(
        Ref(account=sender, folder="INBOX", validity=1, uid=1)
    )
    assert preview["events"][0]["method"] == "REPLY" and preview["events"][0][
        "uid"
    ] == str(ev["UID"])


def test_creation_replay_never_returns_later_notification_batch(store):
    request = uuid4()
    fields = event(attendees=["guest@example.org"])
    original = server.create_event(store.account.email, "work", request, fields)
    changed = server.update_event(*ref(store, original), Fields(location="новый зал"))
    replay = server.create_event(store.account.email, "work", request, fields)
    assert changed["change_id"] != replay["change_id"] == original["change_id"]


def test_orphan_notification_can_be_closed_without_sending(store, monkeypatch):
    def unavailable(*_):
        raise OSError()

    monkeypatch.setattr(store, "write", unavailable)
    with pytest.raises(OSError):
        create(store, attendees=["guest@example.org"])
    change = notices.pending(store.account.email)[0]["change_id"]
    with pytest.raises(Problem, match="не подтверждена"):
        notices.dispatch(store, change)
    assert notices.discard_unconfirmed(store, change) == {"discarded": 1}
    assert not notices.pending(store.account.email)
    with pytest.raises(Problem, match="снята"):
        notices.dispatch(store, change)
