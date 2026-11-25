"""Smoke-test the Windows archive using only its installed plugin runtime."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile


async def probe(folder):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from ya_mail.accounts import SERVICE as MAIL_SERVICE

    from ya_cal import accounts
    from ya_cal.cli import wizard

    assert MAIL_SERVICE != accounts.SERVICE and accounts.vault().priority > 0
    import tkinter as tk

    assert tk.Tcl().eval("info patchlevel")
    assert (Path(wizard.__file__).with_name("assets") / "ya-ca.png").is_file()
    config = json.loads((folder / "mcp.json").read_bytes())["mcpServers"]["ya-ca"]
    exe = (folder / config["command"]).resolve()
    assert exe == Path(sys.executable).resolve()
    async with (
        stdio_client(StdioServerParameters(command=str(exe), args=config["args"])) as (
            r,
            w,
        ),
        ClientSession(r, w) as client,
    ):
        await client.initialize()
        names = {t.name for t in (await client.list_tools()).tools}
        assert {
            "create_event",
            "read_mail_invitation",
            "send_notifications",
            "check_availability",
        } <= names
        print(f"Standalone MCP: {len(names)} tools")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(probe(Path(sys.argv[1])))
    else:
        root = Path(__file__).resolve().parents[1]
        version = json.loads((root / "plugins/ya-ca/plugin.json").read_bytes())[
            "version"
        ]
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "Ya Ca Package"
            with ZipFile(root / "dist" / f"ya-ca-{version}-windows-x64.zip") as bundle:
                bundle.extractall(dest)
            folder = dest / "plugins/ya-ca"
            subprocess.run(
                [folder / "runtime/python.exe", "-I", "-B", __file__, folder],
                cwd=dest,
                env={
                    **os.environ,
                    "PATH": str(Path(os.environ["SystemRoot"]) / "System32"),
                },
                check=True,
                timeout=90,
            )
