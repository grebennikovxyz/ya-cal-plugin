from datetime import UTC, datetime, timedelta
from itertools import pairwise

from ya_mail.accounts import Problem

from .accounts import timezone
from .events import event_data, instances


def agenda(store, lo, hi, calendars=None, category=None):
    zone = timezone(store.account.timezone)
    result = []
    for key in dict.fromkeys(calendars if calendars is not None else store.info):
        store.collection(key)
        info = store.info[key]
        if category and category != info["category"]:
            continue
        for resource, document in store.query(key, lo, hi):
            for ev in instances(document, lo, hi, zone):
                row = {**info, "event_id": resource, **event_data(ev, zone)}
                if any(
                    a["email"] == store.account.email and a["status"] == "DECLINED"
                    for a in row["attendees"]
                ):
                    row["busy"] = False
                result.append(row)
    result.sort(
        key=lambda row: (
            row["start_utc"],
            -row["priority"],
            row["calendar_id"],
            row["event_id"],
            row["recurrence_id"] or "",
        )
    )
    return result


def busy_rows(store, lo, hi, calendars=None):
    return [
        r
        for r in agenda(store, lo, hi, calendars)
        if r["busy"] and r["end_utc"] > r["start_utc"]
    ]


def check(store, key, resource, cal, ev, zone, single, whole=False):
    from .events import interval, local, master

    start, end = [local(v, zone).astimezone(UTC) for v in interval(ev, zone)]
    recurring = not single and any(k in master(cal) for k in ("RRULE", "RDATE"))
    if recurring:
        # A series edited years after creation needs its upcoming occurrences checked.
        lo = max(start, datetime.now(UTC)) if whole else start
        hi = lo + timedelta(days=366)
        proposed = list(instances(cal, lo, hi, zone))
    else:
        lo, hi, proposed = start, end, [ev]
    if hi - lo > timedelta(days=367):
        raise Problem("Для проверки занятости выберите интервал до года.")
    rid = ev.decoded("RECURRENCE-ID").isoformat() if single else None
    clashes = []
    if proposed and hi > lo:
        intervals = []
        for item in proposed:
            if (
                item.get("STATUS") != "CANCELLED"
                and item.get("TRANSP") != "TRANSPARENT"
            ):
                a, b = [local(v, zone).astimezone(UTC) for v in interval(item, zone)]
                intervals.append((a, b))
        if intervals:
            check_lo = min(a for a, b in intervals)
            check_hi = max(b for a, b in intervals)
            for other in busy_rows(store, check_lo, check_hi):
                if (
                    other["calendar_id"] == key
                    and other["event_id"] == resource
                    and (not single or other["recurrence_id"] == rid)
                ):
                    continue
                a = datetime.fromisoformat(other["start_utc"])
                b = datetime.fromisoformat(other["end_utc"])
                if any(a < finish and begin < b for begin, finish in intervals):
                    clashes.append(other)
            if any(a2 < b1 for (a1, b1), (a2, b2) in pairwise(sorted(intervals))):
                clashes.append(
                    {"summary": "Повторения этой серии пересекаются между собой."}
                )
    return {
        "conflicts": clashes,
        "checked_from": lo.isoformat(),
        "checked_until": hi.isoformat(),
    }


def availability(store, lo, hi, minutes, calendars):
    rows = busy_rows(store, lo, hi, calendars)
    free = []
    cursor = lo
    for start, end in [
        (datetime.fromisoformat(r["start_utc"]), datetime.fromisoformat(r["end_utc"]))
        for r in rows
    ] + [(hi, hi)]:
        if start - cursor >= timedelta(minutes=minutes):
            free.append(
                {"start": cursor.isoformat(), "end": min(start, hi).isoformat()}
            )
        cursor = max(end, cursor)
    return {"busy": rows, "free": free, "timezone": store.account.timezone}
