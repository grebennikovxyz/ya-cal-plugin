from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal

import recurring_ical_events
from icalendar import Alarm, Calendar, Event, vCalAddress
from pydantic import BaseModel, ConfigDict, Field
from ya_mail.accounts import Problem, address

Short = Annotated[str, Field(min_length=1, max_length=512)]
Tags = Annotated[list[Short], Field(max_length=50)]
Emails = Annotated[list[Short], Field(max_length=100)]
Reminder = Annotated[int, Field(ge=0, le=525600)]
CHANGE = "X-YA-CAL-CHANGE-ID"
MANAGED = "X-YA-CAL-MAIL"


class Fields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: Short | None = None
    start: Short | None = None
    end: Short | None = None
    description: Annotated[str, Field(max_length=60000)] | None = None
    location: Short | None = None
    tags: Tags | None = None
    attendees: Emails | None = None
    busy: bool | None = None
    reminders_minutes: Annotated[list[Reminder], Field(max_length=10)] | None = None


class Repeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frequency: Literal["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]
    interval: Annotated[int, Field(ge=1, le=999)] = 1
    count: Annotated[int, Field(ge=1, le=10000)] | None = None
    weekdays: list[Literal["MO", "TU", "WE", "TH", "FR", "SA", "SU"]] = Field(
        default_factory=list, max_length=7
    )


class NewEvent(Fields):
    summary: Short
    start: Short
    end: Short
    repeat: Repeat | None = None


def local(value, zone):
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time.min)
    return (value if value.tzinfo else value.replace(tzinfo=zone)).astimezone(zone)


def parse(value, zone):
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            early, late = (
                dt.replace(tzinfo=zone, fold=0),
                dt.replace(tzinfo=zone, fold=1),
            )
            if early.utcoffset() != late.utcoffset():
                raise Problem(
                    "Для перехода на летнее/зимнее время укажите явное смещение UTC."
                )
            return early
        return dt.astimezone(zone)
    except ValueError as exc:
        if isinstance(exc, Problem):
            raise
        raise Problem("Ожидается дата или дата-время ISO 8601.") from None


def window(start, end, zone):
    lo, hi = [local(parse(v, zone), zone).astimezone(UTC) for v in (start, end)]
    if hi <= lo or hi - lo > timedelta(days=367):
        raise Problem("Интервал должен быть положительным, максимум 366 дней.")
    return lo, hi


def interval(ev, zone):
    start = ev.decoded("DTSTART")
    if "DTEND" in ev:
        end = ev.decoded("DTEND")
    elif "DURATION" in ev:
        end = start + ev.decoded("DURATION")
    else:
        end = start if isinstance(start, datetime) else start + timedelta(days=1)
    return start, end


def put(obj, key, value):
    obj.pop(key, None)
    if value is not None:
        obj.add(key, value)


def values(obj, key):
    val = obj.get(key, [])
    return val if isinstance(val, list) else [val]


def email_of(value):
    return str(value).removeprefix("mailto:").removeprefix("MAILTO:").lower()


def people(ev):
    return {email_of(a): a for a in values(ev, "ATTENDEE")}


def edit(ev, fields, account, zone):
    for name in ("summary", "location", "description"):
        value = getattr(fields, name)
        if value is not None:
            put(ev, name, value)
    if fields.start is not None or fields.end is not None:
        start = parse(fields.start, zone) if fields.start else ev.decoded("DTSTART")
        end = parse(fields.end, zone) if fields.end else interval(ev, zone)[1]
        if type(start) is not type(end) or local(end, zone).astimezone(UTC) <= local(
            start, zone
        ).astimezone(UTC):
            raise Problem(
                "Начало и конец должны быть одного типа. Конец должен быть позже начала."
            )
        ev.pop("DURATION", None)
        put(ev, "DTSTART", start)
        put(ev, "DTEND", end)
    if fields.busy is not None:
        put(ev, "TRANSP", "OPAQUE" if fields.busy else "TRANSPARENT")
    if fields.tags is not None:
        put(ev, "CATEGORIES", list(dict.fromkeys(fields.tags)) or None)
    if fields.reminders_minutes is not None:
        ev.subcomponents[:] = [c for c in ev.subcomponents if c.name != "VALARM"]
        for minutes in sorted(set(fields.reminders_minutes)):
            alarm = Alarm()
            alarm.add("ACTION", "DISPLAY")
            alarm.add("DESCRIPTION", str(ev.get("SUMMARY", "Событие")))
            alarm.add("TRIGGER", -timedelta(minutes=minutes))
            ev.add_component(alarm)
    if fields.attendees is not None:
        existing = people(ev)
        managed = ev.get(MANAGED) == "1" or ("ORGANIZER" not in ev and not existing)
        guests = list(dict.fromkeys(address(a).lower() for a in fields.attendees))
        if account in guests:
            raise Problem("Организатор уже участвует во встрече.")
        ev.pop("ATTENDEE", None)
        if guests and managed:
            put(ev, MANAGED, "1")
            organizer = vCalAddress("mailto:" + account)
            organizer.params["SCHEDULE-AGENT"] = "CLIENT"
            put(ev, "ORGANIZER", organizer)
        for guest in guests:
            person = existing.get(guest) or vCalAddress("mailto:" + guest)
            if guest not in existing:
                person.params.update({"PARTSTAT": "NEEDS-ACTION", "RSVP": "TRUE"})
            if managed:
                person.params["SCHEDULE-AGENT"] = "CLIENT"
            ev.add("ATTENDEE", person)


def make_event(fields, account, uid, zone):
    cal = Calendar()
    cal.add("VERSION", "2.0")
    cal.add("PRODID", "-//Grebennikov//Ya-Ca//RU")
    ev = Event()
    ev.add("UID", uid)
    ev.add("DTSTAMP", datetime.now(UTC))
    ev.add("SEQUENCE", 0)
    edit(ev, fields, account, zone)
    if fields.repeat:
        rule = {"FREQ": fields.repeat.frequency, "INTERVAL": fields.repeat.interval}
        if fields.repeat.count:
            rule["COUNT"] = fields.repeat.count
        if fields.repeat.weekdays:
            rule["BYDAY"] = fields.repeat.weekdays
        ev.add("RRULE", rule)
    cal.add_component(ev)
    return cal


def event_data(ev, zone):
    start, end = interval(ev, zone)
    return dict(
        uid=str(ev["UID"]),
        summary=str(ev.get("SUMMARY", "")),
        start=start.isoformat(),
        end=end.isoformat(),
        start_utc=local(start, zone).astimezone(UTC).isoformat(),
        end_utc=local(end, zone).astimezone(UTC).isoformat(),
        recurrence_id=ev.decoded("RECURRENCE-ID").isoformat()
        if "RECURRENCE-ID" in ev
        else None,
        all_day=not isinstance(start, datetime),
        location=str(ev.get("LOCATION", "")),
        description=str(ev.get("DESCRIPTION", "")),
        tags=[str(tag) for group in values(ev, "CATEGORIES") for tag in group.cats],
        organizer=email_of(ev.get("ORGANIZER", "")),
        attendees=[
            {"email": email, "status": str(a.params.get("PARTSTAT", "NEEDS-ACTION"))}
            for email, a in people(ev).items()
        ],
        sequence=int(ev.get("SEQUENCE", 0)),
        status=str(ev.get("STATUS", "CONFIRMED")),
        busy=ev.get("STATUS") != "CANCELLED" and ev.get("TRANSP") != "TRANSPARENT",
        repeat=ev["RRULE"].to_ical().decode() if "RRULE" in ev else None,
        reminders=[
            str(alarm.decoded("TRIGGER"))
            for alarm in ev.walk("VALARM")
            if "TRIGGER" in alarm
        ],
    )


def master(cal):
    found = [e for e in cal.walk("VEVENT") if "RECURRENCE-ID" not in e]
    if len(found) != 1:
        raise Problem("У ресурса отсутствует единственное основное событие.")
    return found[0]


def instances(cal, lo, hi, zone):
    components = cal.walk("VEVENT")
    recurring = any(
        "RRULE" in e or "RDATE" in e or "RECURRENCE-ID" in e for e in components
    )
    if recurring:
        # Keep date boundaries and floating wall times in the profile's zone.
        for e in components:
            for rule in values(e, "RRULE"):
                if str(rule["FREQ"][0]) in (
                    "SECONDLY",
                    "MINUTELY",
                ) and hi - lo > timedelta(days=2):
                    raise Problem(
                        "В календаре частые повторы. Сократите период до двух дней."
                    )
        events = recurring_ical_events.of(cal).between(
            lo.astimezone(zone), hi.astimezone(zone)
        )
    else:
        events = components
    for ev in events:
        start, end = interval(ev, zone)
        a, b = (local(v, zone).astimezone(UTC) for v in (start, end))
        if a < hi and (b > lo or a == b == lo) and ev.get("STATUS") != "CANCELLED":
            yield ev


def occurrence(cal, rid, zone):
    value = parse(rid, zone)
    instant = local(value, zone).astimezone(UTC)
    for e in cal.walk("VEVENT"):
        if (
            "RECURRENCE-ID" in e
            and local(e.decoded("RECURRENCE-ID"), zone).astimezone(UTC) == instant
        ):
            return e
    for e in instances(cal, instant, instant + timedelta(seconds=1), zone):
        if (
            "RECURRENCE-ID" in e
            and local(e.decoded("RECURRENCE-ID"), zone).astimezone(UTC) == instant
        ):
            override = deepcopy(e)
            cal.add_component(override)
            return override
    raise Problem("Указанное повторение не найдено.")
