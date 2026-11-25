"""Activate one verified release under a stable per-user marketplace path."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

MARKET = "grebennikov-calendar"
SELECTOR = f"ya-ca@{MARKET}"
INDEX = Path(".agents/plugins/marketplace.json")


def replace_file(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(data)
        except BaseException:
            stream.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.chmod(mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def register(codex, base):
    def run(args, cwd, **kwargs):
        return subprocess.run([codex, "plugin", *args], cwd=cwd, check=True, **kwargs)

    # An earlier manual installation can point to a clone or extracted ZIP.
    markets = json.loads(
        run(["marketplace", "list", "--json"], base, capture_output=True).stdout
    )["marketplaces"]
    old = next((Path(m["root"]) for m in markets if m["name"] == MARKET), None)
    migrate = old is not None and (not old.is_dir() or not old.samefile(base))
    if migrate:
        # Automatically migrate a matching local Ya-Ca marketplace only.
        # Git-managed caches can be removed by Codex; preserve their remote registration.
        config_path = (
            Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
        )
        config = (
            tomllib.loads(config_path.read_text(encoding="utf-8"))
            if config_path.is_file()
            else {}
        )
        registration = config.get("marketplaces", {}).get(MARKET, {})
        meta = old / "plugins/ya-ca/plugin.json"
        previous = (
            json.loads((old / INDEX).read_bytes()) if (old / INDEX).is_file() else {}
        )
        if (
            registration.get("source_type") != "local"
            or previous.get("name") != MARKET
            or [p["name"] for p in previous["plugins"]] != ["ya-ca"]
            or not meta.is_file()
            or json.loads(meta.read_bytes()).get("repository")
            != "https://github.com/grebennikovxyz/ya-cal-plugin"
        ):
            raise SystemExit(
                f"Codex already uses {MARKET} from {old}. To switch, run 'codex plugin marketplace remove {MARKET}' and repeat the installation."
            )
        run(["marketplace", "remove", MARKET], base)
    try:
        run(["marketplace", "add", "."], base)
        run(["add", SELECTOR], base)
    except subprocess.CalledProcessError:
        if migrate and old.is_dir():
            subprocess.run(
                [codex, "plugin", "marketplace", "remove", MARKET],
                cwd=base,
                check=False,
            )
            run(["marketplace", "add", "."], old)
            run(["add", SELECTOR], old)
        raise


def activate(codex=None):
    from ya_cal.server import (
        mcp,  # Verify the actual installed runtime before switching the marketplace.
    )

    release = Path(__file__).resolve().parent
    base = release.parent.parent
    index = json.loads((release / INDEX).read_bytes())
    plug = release / "plugins/ya-ca"
    version = json.loads((plug / "plugin.json").read_bytes())["version"]
    if release.parent.name != "versions" or release.name != f"v{version}" or not mcp:
        raise SystemExit("Unexpected Ya-Ca release directory.")
    index["plugins"][0]["source"]["path"] = "./" + plug.relative_to(base).as_posix()
    interpreter = os.path.abspath(sys.executable)
    if os.name != "nt":
        cfg = json.loads((plug / "mcp.json").read_bytes())
        cfg["mcpServers"]["ya-ca"].update(
            command=interpreter, args=["-I", "-B", "-m", "ya_cal.cli", "serve"]
        )
        replace_file(
            plug / "mcp.json", json.dumps(cfg, ensure_ascii=True, indent=2).encode()
        )
    target = base / INDEX
    before = target.read_bytes() if target.exists() else None
    replace_file(target, json.dumps(index, indent=2).encode())

    if os.name == "nt" and not codex:
        codex = shutil.which("codex.exe") or shutil.which("codex.cmd")
    codex = codex or shutil.which("codex")
    try:
        if codex:
            register(codex, base)
    except BaseException:
        if before is None:
            target.unlink(missing_ok=True)
        else:
            replace_file(target, before)
        raise

    if os.name == "nt":
        launcher = base / "ya-ca.cmd"
        cmd = (
            r'"%~dp0versions\v'
            + version
            + r'\plugins\ya-ca\runtime\python.exe" -I -B -m ya_cal.cli %*'
        )
        replace_file(launcher, ("@echo off\r\n" + cmd + "\r\n").encode("ascii"))
    else:
        launcher = base / "ya-ca"
        replace_file(
            launcher,
            f'#!/bin/sh\nexec {shlex.quote(interpreter)} -I -B -m ya_cal.cli "$@"\n'.encode(),
            0o700,
        )
    print(f"Ya-Ca {version} installed. CLI: {launcher}")
    if codex:
        print("Codex: open a new chat, select Ya-Ca and ask to connect your calendar.")
    else:
        print(
            "For another MCP client, run the CLI above with 'mcp-config CLIENT'. To register in Codex, install the Codex CLI and rerun this installer."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex")
    activate(parser.parse_args().codex)
