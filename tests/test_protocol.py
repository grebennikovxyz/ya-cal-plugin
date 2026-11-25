import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import pytest
import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ya_cal import accounts, dav, wizard
from ya_cal.events import NewEvent, make_event

ROOT = Path(__file__).resolve().parents[1]


def test_client_launch_configs(capsys, monkeypatch):
    from ya_cal.cli import main

    for client in ("claude-code", "claude-desktop", "cursor", "gemini", "vscode"):
        monkeypatch.setattr(sys, "argv", ["ya-ca", "mcp-config", client])
        main()
        config = json.loads(capsys.readouterr().out)
        group = "servers" if client == "vscode" else "mcpServers"
        assert list(config) == [group]
        launch = config[group]["ya-ca"]
        assert launch["command"] == os.path.abspath(sys.executable)
        assert launch["args"] == ["-I", "-B", "-m", "ya_cal.cli", "serve"]
        assert launch.get("type") == ("stdio" if client == "vscode" else None)

    async def check():
        params = StdioServerParameters(command=launch["command"], args=launch["args"])
        async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
            await session.initialize()
            assert "list_accounts" in {
                t.name for t in (await session.list_tools()).tools
            }

    asyncio.run(check())


def test_plugin_manifest_and_stdio(tmp_path):
    plug = ROOT / "plugins/ya-ca"
    manifest = json.loads((plug / ".codex-plugin/plugin.json").read_bytes())
    common = json.loads((plug / "plugin.json").read_bytes())
    assert common["extensions"]["com.openai"]["interface"] == manifest["interface"]
    assert (plug / manifest["interface"]["logo"]).read_bytes().startswith(b"\x89PNG")
    config = json.loads((plug / manifest["mcpServers"]).read_bytes())["mcpServers"][
        "ya-ca"
    ]
    assert config == {"type": "stdio", "command": "ya-ca", "args": ["serve"]}
    script = (
        "import sys;from pathlib import Path;from ya_cal import accounts;from ya_mail import accounts as mail;"
        "p=Path(sys.argv.pop(1));accounts.DATA=p/'cal';mail.DATA=p/'mail';from ya_cal.cli import main;main()"
    )

    async def check():
        params = StdioServerParameters(
            command=sys.executable, args=["-c", script, str(tmp_path), *config["args"]]
        )
        async with (
            stdio_client(params) as (reader, writer),
            ClientSession(reader, writer) as client,
        ):
            await client.initialize()
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert {
                "check_availability",
                "upcoming_events",
                "list_calendars",
                "create_event",
                "send_notifications",
            } <= tools.keys()
            assert (
                tools["search_events"].annotations.readOnlyHint
                and tools["delete_event"].annotations.destructiveHint
            )
            res = await client.call_tool("list_accounts", {})
            assert not res.isError and json.loads(res.content[0].text)["accounts"] == []

    asyncio.run(check())


def test_real_caldav_http_library(monkeypatch, tmp_path):
    monkeypatch.setattr(accounts, "DATA", tmp_path / "data")
    stored = {}
    paths = []

    def send(_session, req, **kwargs):
        path = urlsplit(req.url).path
        assert req.url.startswith(dav.ORIGIN + "/")
        assert req.headers["Authorization"].startswith("Basic ")
        paths.append((req.method, path))
        result = requests.Response()
        result.request, result.url = req, req.url
        result.status_code, result._content = 207, b""
        resp = ET.Element(dav.D + "multistatus")
        item = ET.SubElement(resp, dav.D + "response")
        href = ET.SubElement(item, dav.D + "href")
        href.text = path
        part = ET.SubElement(item, dav.D + "propstat")
        ET.SubElement(part, dav.D + "status").text = "HTTP/1.1 200 OK"
        props = ET.SubElement(part, dav.D + "prop")
        if req.method == "PROPFIND":
            if path == "/":
                ET.SubElement(
                    ET.SubElement(props, dav.D + "current-user-principal"),
                    dav.D + "href",
                ).text = "/user/"
            elif path == "/user/":
                ET.SubElement(
                    ET.SubElement(props, dav.C + "calendar-home-set"), dav.D + "href"
                ).text = "/home/"
            elif path == "/home/":
                href.text = "/home/work/"
                ET.SubElement(
                    ET.SubElement(props, dav.D + "resourcetype"), dav.C + "calendar"
                )
                ET.SubElement(props, dav.D + "displayname").text = "Работа"
            else:
                pytest.fail(path)
        elif req.method == "REPORT":
            assert req.headers["Depth"] == "1" and b"time-range" in req.body
            href.text = "/home/work/test.ics"
            ET.SubElement(props, dav.C + "calendar-data").text = stored[
                href.text
            ].decode()
        elif req.method == "PUT":
            if path not in stored:
                assert req.headers["If-None-Match"] == "*"
            else:
                assert req.headers["If-Match"] == '"rev"'
            stored[path] = req.body
            result.status_code = 201
        elif req.method == "GET":
            result.status_code = 200
            result.headers.update(
                {"ETag": '"rev"', "Content-Type": "text/calendar; charset=utf-8"}
            )
            result._content = stored[path]
        elif req.method == "DELETE":
            assert req.headers["If-Match"] == '"rev"'
            del stored[path]
            result.status_code = 204
        if result.status_code == 207:
            result.headers["Content-Type"] = "application/xml; charset=utf-8"
            result._content = ET.tostring(resp, encoding="utf-8")
        result.headers["Content-Length"] = str(len(result._content))
        return result

    monkeypatch.setattr(requests.Session, "send", send)
    acct = accounts.Account(
        "one@example.org", "write", "Europe/Moscow", "local-test-only"
    )
    with dav.session(acct) as store:
        (key,) = store.collections
        assert store.info[key]["name"] == "Работа"
        doc = make_event(
            NewEvent(summary="Работа", start="2031-06-08", end="2031-06-09"),
            acct.email,
            "id",
            accounts.timezone(acct.timezone),
        )
        store.write(key, "test.ics", doc)
        lo, hi = datetime(2031, 6, 7, tzinfo=UTC), datetime(2031, 6, 10, tzinfo=UTC)
        assert next(store.query(key, lo, hi))[0] == "test.ics"
        current, etag = store.get(key, "test.ics")
        assert current.walk("VEVENT")[0]["SUMMARY"] == "Работа"
        store.write(key, "test.ics", current, etag)
        store.write(key, "test.ics", None, etag)
    assert not stored and len(paths) == 8


def test_headless_falls_back_to_terminal(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def without_tk(name, *args, **kwargs):
        if name == "tkinter":
            raise ImportError
        return real_import(name, *args, **kwargs)

    seen = []
    monkeypatch.setattr(builtins, "__import__", without_tk)
    monkeypatch.setattr(wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(wizard, "terminal", lambda: seen.append(True))
    wizard.wizard()
    assert seen == [True]


def test_terminal_wizard_guides_validates_and_hides_password(monkeypatch, capsys):
    import builtins

    monkeypatch.setattr(wizard.sys.stdin, "isatty", lambda: True)
    answers = iter(["-", "me@example.org", "Europe/Moscow", "2"])
    monkeypatch.setattr(builtins, "input", lambda _: next(answers))
    monkeypatch.setattr(wizard.getpass, "getpass", lambda _: "sensitive-example")
    seen = []

    def connect(*args):
        seen.append(args)
        return 3

    monkeypatch.setattr(wizard, "connect", connect)
    wizard.terminal()
    out = capsys.readouterr().out
    assert seen == [("me@example.org", "sensitive-example", "write", "Europe/Moscow")]
    assert wizard.PASSWORDS in out and "sensitive-example" not in out and "3" in out


def test_graphical_wizard_steps(monkeypatch):
    import os
    import time
    import tkinter as tk
    from tkinter import ttk

    try:
        root = tk.Tk()
    except tk.TclError:
        if os.environ.get("YA_CA_UI_TEST") == "required":
            raise
        pytest.skip("Tk display unavailable")
    root.withdraw()
    monkeypatch.setattr(tk, "Tk", lambda: root)
    links, inputs = [], []
    monkeypatch.setattr(wizard.webbrowser, "open", lambda url: links.append(url))

    def connect(*args):
        inputs.append(args)
        return 2

    monkeypatch.setattr(wizard, "connect", connect)

    def widgets():
        return root.winfo_children()[0].winfo_children()

    def click(text):
        next(
            w for w in widgets() if isinstance(w, ttk.Button) and w.cget("text") == text
        ).invoke()

    def interact():
        click("Открыть Яндекс ID")
        click("Пароль скопирован · Далее")
        email, secret, zone = [w for w in widgets() if isinstance(w, ttk.Entry)]
        assert secret.cget("show") == "*"
        email.insert(0, "me@example.org")
        secret.insert(0, "test-only")
        click("Проверить и подключить")
        deadline = time.monotonic() + 10
        while not any(
            isinstance(w, ttk.Button) and w.cget("text") == "Готово" for w in widgets()
        ):
            root.update()
            if time.monotonic() > deadline:
                pytest.fail("Wizard did not show successful discovery")
            time.sleep(0.02)
        assert any("Доступно календарей: 2" in str(w.cget("text")) for w in widgets())

    monkeypatch.setattr(root, "mainloop", interact)
    try:
        wizard.window()
    finally:
        root.destroy()
    assert links == [wizard.PASSWORDS] and inputs == [
        ("me@example.org", "test-only", "read", "Europe/Moscow")
    ]
