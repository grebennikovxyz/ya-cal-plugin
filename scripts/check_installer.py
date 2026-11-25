"""Exercise install, repeat install, and MCP discovery with a fresh Codex profile."""

import argparse
import asyncio
import functools
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

from check_package import discover
from release_assets import ROOT, digest, render_installer

WINDOWS = os.name == "nt"
SUFFIX = "-windows-x64.zip" if WINDOWS else ".zip"
SCRIPT = "ya-ca-latest.ps1" if WINDOWS else "ya-ca-latest.sh"
GITHUB = "https://github.com/grebennikovxyz/ya-cal-plugin/releases"


@contextmanager
def local_release(tmp, version):
    dist = tmp / "served"
    dist.mkdir()
    archive = dist / ("ya-ca-latest" + SUFFIX)
    shutil.copyfile(ROOT / "dist" / f"ya-ca-{version}{SUFFIX}", archive)
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(dist)
    )
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        url = f"http://127.0.0.1:{server.server_port}"
        template = "windows.ps1" if WINDOWS else "linux.sh"
        (dist / SCRIPT).write_text(
            render_installer("v" + version, template, url, digest(archive)),
            encoding="utf8",
            newline="\n",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield url
        finally:
            server.shutdown()
            thread.join()


def run(url, tmp, version):
    profile = tmp / "codex"
    profile.mkdir()
    data = tmp / "user data"
    data.mkdir()
    env = dict(
        os.environ,
        CODEX_HOME=str(profile),
        LOCALAPPDATA=str(data),
        XDG_DATA_HOME=str(data),
        UV_CACHE_DIR=str(ROOT / ".cache/uv"),
    )
    # Keep local profile isolation without hiding an npm-installed Codex command.
    codex = (
        (shutil.which("codex.exe") or shutil.which("codex.cmd"))
        if WINDOWS
        else shutil.which("codex")
    )
    if not codex:
        raise RuntimeError("The install smoke test needs Codex CLI.")
    env["PATH"] = str(Path(codex).parent) + os.pathsep + env["PATH"]
    if WINDOWS:
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"$ErrorActionPreference='Stop'; Invoke-RestMethod '{url}/{SCRIPT}' | Invoke-Expression",
        ]
        base = data / "Ya-Ca"
    else:
        command = ["bash", "-o", "pipefail", "-c", f'curl -fsSL "{url}/{SCRIPT}" | sh']
        base = data / "ya-ca"

    for _ in range(2):
        subprocess.run(command, env=env, cwd=tmp, check=True, timeout=420)
    installed = json.loads(
        subprocess.check_output(
            [codex, "plugin", "marketplace", "list", "--json"], env=env, cwd=tmp
        )
    )
    (match,) = [
        m for m in installed["marketplaces"] if m["name"] == "grebennikov-calendar"
    ]
    assert Path(match["root"]).samefile(base)
    cached = profile / "plugins/cache/grebennikov-calendar/ya-ca" / version
    config = json.loads((cached / "mcp.json").read_bytes())["mcpServers"]["ya-ca"]
    cmd = config["command"]
    assert Path(cmd).is_absolute() and Path(cmd).is_relative_to(base)
    subprocess.run([cmd, "-I", "-B", "-c", "import charset_normalizer"], check=True)
    count = asyncio.run(discover(cmd, config["args"], cached))
    cli = base / ("ya-ca.cmd" if WINDOWS else "ya-ca")
    output = json.loads(
        subprocess.check_output([str(cli), "mcp-config", "cursor"], env=env, cwd=tmp)
    )
    assert Path(output["mcpServers"]["ya-ca"]["command"]).is_file()
    print(f"Installed Ya-Ca {version} twice; Codex cache exposed {count} MCP tools.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--published",
        action="store_true",
        help="Use the public latest Release instead of the local build",
    )
    args = parser.parse_args()
    version = json.loads((ROOT / "plugins/ya-ca/plugin.json").read_bytes())["version"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as name:
        tmp = Path(name)
        if args.published:
            run(GITHUB + "/latest/download", tmp, version)
        else:
            with local_release(tmp, version) as url:
                run(url, tmp, version)
