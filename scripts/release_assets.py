"""Prepare stable GitHub Release asset names from the already tested archives."""

import argparse
import hashlib
import re
import shutil
from pathlib import Path

from sync_marketplaces import sync

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/grebennikovxyz/ya-cal-plugin/releases/download"


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def render_installer(tag, filename, url, checksum):
    source = (ROOT / "install" / filename).read_text(encoding="utf-8")
    return (
        source.replace("@VERSION@", tag.removeprefix("v"))
        .replace("@RELEASE_URL@", url)
        .replace("@DIGEST@", checksum)
    )


def prepare(tag, dist, output):
    version = sync()
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or tag != f"v{version}":
        raise ValueError("A stable tag must match the synchronized project version.")
    checksums = {
        name: sha
        for sha, name in (
            line.split("  ", 1)
            for line in (dist / "SHA256SUMS.txt").read_text().splitlines()
        )
    }
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use an empty directory for release assets.")
    wheel = f"grebennikov_ya_ca-{version}-py3-none-any.whl"
    files = {
        f"ya-ca-{version}{suffix}": "ya-ca-latest" + suffix
        for suffix in (".zip", "-plugin.zip", "-windows-x64.zip")
    }
    files[wheel] = wheel
    sums = {}
    for name, alias in files.items():
        path = dist / name
        sha = digest(path)
        if sha != checksums[name]:
            raise ValueError(f"Checksum mismatch for {name}")
        shutil.copyfile(path, output / alias)
        sums[alias] = sha
    for filename, asset, platform in (
        ("ya-ca-latest.ps1", "ya-ca-latest-windows-x64.zip", "windows.ps1"),
        ("ya-ca-latest.sh", "ya-ca-latest.zip", "linux.sh"),
    ):
        rendered = render_installer(tag, platform, f"{URL}/{tag}", sums[asset])
        path = output / filename
        path.write_text(rendered, encoding="utf-8", newline="\n")
        sums[filename] = digest(path)
    (output / "SHA256SUMS.txt").write_text(
        "".join(f"{sha}  {name}\n" for name, sha in sorted(sums.items())),
        encoding="ascii",
        newline="\n",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("dist", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.tag, args.dist, args.output)
