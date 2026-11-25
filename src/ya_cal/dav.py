"""Yandex-only CalDAV discovery and conditional resource operations."""

import hashlib
from contextlib import contextmanager
from datetime import UTC, timedelta
from urllib.parse import unquote, urljoin, urlsplit

import caldav
import requests
from caldav.lib.error import AuthorizationError
from icalendar import Calendar
from ya_mail.accounts import Problem

from .accounts import preferences

ORIGIN = "https://caldav.yandex.ru"
D = "{DAV:}"
C = "{urn:ietf:params:xml:ns:caldav}"


class Rejected(Problem):
    """The server definitively refused a mutation."""


def destination(url):
    parsed = urlsplit(str(url))
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "caldav.yandex.ru"
        or parsed.query
        or parsed.fragment
        or "\\" in unquote(str(url))
        or any(ord(c) < 32 for c in unquote(str(url)))
    ):
        raise Problem("CalDAV вернул недопустимый адрес ресурса.")
    return str(url)


def child(base, name):
    if (
        not name
        or unquote(name) in (".", "..")
        or any(c in unquote(name) for c in "/\\?#")
        or ":" in name
    ):
        raise Problem("Используйте event_id, возвращённый календарём.")
    return destination(base.rstrip("/") + "/" + name)


@contextmanager
def session(account):
    client = caldav.DAVClient(
        url=ORIGIN,
        auth=requests.auth.HTTPBasicAuth(account.email, account.password),
        timeout=25,
        ssl_verify_cert=True,
    )
    client.session.trust_env = False
    original = client.session.request

    def guarded(method, url, **kwargs):
        kwargs["allow_redirects"] = False
        return original(method, destination(url), **kwargs)

    client.session.request = guarded
    try:
        yield Store(client, account)
    except AuthorizationError:
        raise Problem(
            "Яндекс отклонил доступ. Проверьте пароль CalDAV и права календаря."
        ) from None
    except (requests.RequestException, caldav.lib.error.DAVError):
        raise Problem(
            "Ошибка связи с CalDAV. После записи перечитайте событие перед повтором."
        ) from None
    finally:
        client.close()


class Store:
    def __init__(self, client, account):
        self.client = client
        self.account = account
        self.collections = {}
        self.info = {}
        prefs = preferences(account.email)
        for cal in client.principal().calendars():
            url = destination(cal.url).rstrip("/") + "/"
            key = hashlib.sha256(url.encode()).hexdigest()[:24]
            category, priority = prefs.get(key, ("other", 50))
            self.collections[key] = url
            self.info[key] = dict(
                calendar_id=key,
                name=str(cal.name or key),
                category=category,
                priority=priority,
            )

    def collection(self, key):
        if key not in self.collections:
            raise Problem(
                "Календарь недоступен этому аккаунту. Обновите list_calendars."
            )
        return self.collections[key]

    def query(self, key, start, end):
        base = self.collection(key)
        # Floating and all-day values may have a different server default timezone.
        lo = (start.astimezone(UTC) - timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")
        hi = (end.astimezone(UTC) + timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")
        body = f"""<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
        <d:prop><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR">
        <c:comp-filter name="VEVENT"><c:time-range start="{lo}" end="{hi}"/></c:comp-filter>
        </c:comp-filter></c:filter></c:calendar-query>"""
        response = self.client.request(
            base, "REPORT", body, {"Depth": "1", "Content-Type": "application/xml"}
        )
        if (
            response.status != 207
            or response.tree is None
            or response.tree.tag != D + "multistatus"
        ):
            raise Problem(
                "CalDAV не вернул полный список событий. Занятость неизвестна."
            )
        for item in response.tree.findall(D + "response"):
            href = destination(urljoin(base, item.findtext(D + "href") or ""))
            if not href.startswith(base):
                raise Problem("Событие не принадлежит запрошенному календарю.")
            name = href[len(base) :]
            child(base, name)
            for part in item.findall(D + "propstat"):
                status = (part.findtext(D + "status") or "").split()
                data = part.findtext(D + "prop/" + C + "calendar-data")
                if status[1:2] == ["200"] and data:
                    yield name, Calendar.from_ical(data)
                    break
            else:
                raise Problem("Часть календаря недоступна. Занятость неизвестна.")

    def get(self, key, event_id):
        response = self.client.request(child(self.collection(key), event_id), "GET")
        if response.status == 404:
            return None
        if response.status != 200:
            raise Problem(f"Не удалось прочитать событие (HTTP {response.status}).")
        return Calendar.from_ical(response.raw), response.headers.get("ETag")

    def write(self, key, event_id, document, etag=None):
        url = child(self.collection(key), event_id)
        headers = {"If-Match": etag} if etag else {"If-None-Match": "*"}
        method = "DELETE" if document is None else "PUT"
        if document is None and not etag:
            raise Problem("Для удаления нужна текущая версия события.")
        headers["Content-Type"] = "text/calendar; charset=utf-8"
        try:
            response = self.client.request(
                url, method, document.to_ical() if document is not None else "", headers
            )
        except AuthorizationError:
            raise Rejected(
                "У аккаунта нет права изменить этот календарь или истёк пароль CalDAV."
            ) from None
        if response.status in (409, 412):
            raise Rejected("Событие изменилось. Перечитайте его перед повтором.")
        if 400 <= response.status < 500:
            raise Rejected(f"CalDAV отклонил изменение (HTTP {response.status}).")
        if response.status not in (200, 201, 204):
            raise Problem(f"CalDAV отклонил изменение (HTTP {response.status}).")
