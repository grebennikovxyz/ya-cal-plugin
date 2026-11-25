"""Build the installable marketplace and (optionally) a Windows standalone copy."""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/ya-ca"
DIST = ROOT / "dist"
VERSION = json.loads((PLUGIN / "plugin.json").read_bytes())["version"]


def add_tree(archive, folder, prefix, exclude=()):
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder)
        if (
            path.is_file()
            and rel.parts[0] not in exclude
            and "__pycache__" not in rel.parts
            and rel.parts[:2] != ("Lib", "site-packages")
            and path.suffix != ".pyc"
            and path.name not in {"direct_url.json", "uv_cache.json", "uv_build.json"}
        ):
            archive.write(path, prefix + rel.as_posix())


def build(runtime=None):
    DIST.mkdir(exist_ok=True)
    wheel = DIST / f"grebennikov_ya_ca-{VERSION}-py3-none-any.whl"
    subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--out-dir",
            str(DIST),
            "--cache-dir",
            str(ROOT / ".cache/uv"),
        ],
        cwd=ROOT,
        check=True,
    )
    marketplace = ".agents/plugins/marketplace.json"
    for standalone in [False, True] if runtime else [False]:
        output = DIST / (
            f"ya-ca-{VERSION}" + ("-windows-x64" if standalone else "") + ".zip"
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            ZipFile(output, "w", ZIP_DEFLATED) as archive,
        ):
            archive.write(ROOT / marketplace, marketplace)
            prefix = "plugins/ya-ca/"
            for path in sorted(PLUGIN.rglob("*")):
                if path.is_file() and path.name != "mcp.json":
                    archive.write(path, prefix + path.relative_to(PLUGIN).as_posix())
            config = json.loads((PLUGIN / "mcp.json").read_bytes())
            for doc in ("README.md", "LICENSE", "NOTICE"):
                archive.write(ROOT / doc, doc)
            if standalone:
                packages = Path(tmp) / "deps"
                python = runtime / "python.exe"
                if not python.is_file():
                    raise ValueError(
                        "Specify a clean standalone Windows Python installation."
                    )
                subprocess.run(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--only-binary",
                        ":all:",
                        "--cache-dir",
                        str(ROOT / ".cache/uv"),
                        "--target",
                        str(packages),
                        "--python",
                        str(python),
                        str(wheel),
                    ],
                    check=True,
                )
                add_tree(
                    archive,
                    runtime,
                    prefix + "runtime/",
                    {"include", "libs", "Scripts"},
                )
                add_tree(
                    archive,
                    packages,
                    prefix + "runtime/Lib/site-packages/",
                    {"bin", "Scripts"},
                )
                config["mcpServers"]["ya-ca"].update(
                    command="./runtime/python.exe",
                    args=["-I", "-B", "-m", "ya_cal.cli", "serve"],
                )
                archive.writestr(
                    "connect.cmd",
                    '@echo off\r\n"%~dp0plugins\\ya-ca\\runtime\\python.exe" -I -B -m ya_cal.cli connect %*\r\nif errorlevel 1 pause\r\n',
                )
            else:
                archive.write(wheel, wheel.name)
                # Reuse the checkout launchers, installing the packaged wheel.
                for script in ("connect.sh", "connect.cmd"):
                    source = (
                        (ROOT / script)
                        .read_text(encoding="utf-8")
                        .replace('"%~dp0."', f'"%~dp0{wheel.name}"')
                        .replace('"$root"', f'"$root/{wheel.name}"')
                    )
                    archive.writestr(script, source)
            archive.writestr(prefix + "mcp.json", json.dumps(config, indent=2))
        print(output)
    with (DIST / "SHA256SUMS.txt").open("w", encoding="utf-8", newline="\n") as stream:
        for path in sorted(DIST.iterdir()):
            if path.suffix in {".zip", ".whl"}:
                with path.open("rb") as src:
                    stream.write(
                        f"{hashlib.file_digest(src, 'sha256').hexdigest()}  {path.name}\n"
                    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--windows-runtime", type=Path)
    build(cli.parse_args().windows_runtime)
