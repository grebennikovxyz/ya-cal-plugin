"""Verify both the standalone Windows runtime and the Agent Plugins ZIP."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile


async def discover(command, args, folder, env=None):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=command, args=args, cwd=str(folder), env=env)
    async with stdio_client(params) as (r, w), ClientSession(r, w) as client:
        await client.initialize()
        names = {t.name for t in (await client.list_tools()).tools}
        assert {
            "create_event",
            "read_mail_invitation",
            "send_notifications",
            "check_availability",
        } <= names
        return len(names)


def check_plugin(root, folder, version):
    with ZipFile(root / "dist" / f"ya-ca-{version}-plugin.zip") as archive:
        names = set(archive.namelist())
        assert {
            "plugin.json",
            "mcp.json",
            "skills/ya-ca/SKILL.md",
            "assets/ya-ca.png",
        } <= names
        assert not any(name.startswith(("plugins/", ".agents/")) for name in names)
        archive.extractall(folder)
    manifest = json.loads((folder / "plugin.json").read_bytes())
    interface = manifest["extensions"]["com.openai"]["interface"]
    assert manifest["version"] == version and manifest["name"] == "ya-ca"
    assert (
        len(interface["shortDescription"]) <= 30
        and (folder / interface["logo"]).is_file()
    )
    config = json.loads((folder / "mcp.json").read_bytes())["mcpServers"]["ya-ca"]
    args = [arg.replace("${PLUGIN_ROOT}", str(folder)) for arg in config["args"]]
    count = asyncio.run(
        discover(
            config["command"],
            args,
            folder.parent,
            {"UV_CACHE_DIR": str(root / ".cache/uv")},
        )
    )
    print(f"Agent Plugins archive: {count} tools")


async def probe(folder):
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
    count = await discover(str(exe), config["args"], folder)
    print(f"Standalone MCP: {count} tools")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(probe(Path(sys.argv[1])))
    else:
        root = Path(__file__).resolve().parents[1]
        version = json.loads((root / "plugins/ya-ca/plugin.json").read_bytes())[
            "version"
        ]
        with tempfile.TemporaryDirectory() as tmp:
            check_plugin(root, Path(tmp) / "Ya Ca #Plugin", version)
            if sys.platform != "win32":
                sys.exit(0)
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
