"""Synchronize repository marketplace manifests with the Python project version."""

import argparse
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/ya-ca"


def sync(check=True):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    version = project["version"]
    common_path = PLUGIN / "plugin.json"
    common = json.loads(common_path.read_bytes())
    common["version"] = version
    shared = {
        key: common[key]
        for key in ("name", "version", "description", "author", "repository", "license")
    }
    codex = {
        **shared,
        "requires_local_executor": True,
        "mcpServers": "./mcp.json",
        "skills": "./skills/",
        "interface": common["extensions"]["com.openai"]["interface"],
    }
    claude = {**shared, "mcpServers": "./mcp.json"}
    catalog = json.loads((ROOT / ".agents/plugins/marketplace.json").read_bytes())
    (entry,) = catalog["plugins"]
    if (
        entry["name"] != common["name"]
        or (ROOT / entry["source"]["path"]).resolve() != PLUGIN
    ):
        raise ValueError("Codex marketplace must reference the Ya-Ca plugin directory.")
    marketplace = {
        "name": catalog["name"],
        "description": common["description"],
        "owner": common["author"],
        "plugins": [
            {
                "name": entry["name"],
                "source": entry["source"]["path"],
                "description": common["description"],
            }
        ],
    }
    wheel = f"grebennikov_ya_ca-{version}-py3-none-any.whl"
    url = f"{common['repository']}/releases/download/v{version}/{wheel}"
    mcp = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        "mcpServers": {
            "ya-ca": {
                "type": "stdio",
                "command": "uvx",
                "args": ["--python", "3.13", "--from", url, "ya-ca", "serve"],
            }
        },
    }
    files = {
        common_path: common,
        PLUGIN / ".codex-plugin/plugin.json": codex,
        PLUGIN / ".claude-plugin/plugin.json": claude,
        ROOT / ".claude-plugin/marketplace.json": marketplace,
        PLUGIN / "mcp.json": mcp,
    }
    contents = {
        path: json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        for path, value in files.items()
    }
    skill = PLUGIN / "skills/ya-ca/SKILL.md"
    _, front, body = skill.read_text(encoding="utf-8").split("---\n", 2)
    front, count = re.subn(r"(?m)^version: .+$", f"version: {version}", front)
    if count != 1:
        raise ValueError("The skill frontmatter needs one version field.")
    contents[skill] = f"---\n{front}---\n{body}"
    for path, content in contents.items():
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        if check:
            raise ValueError(
                f"{path.relative_to(ROOT)} is out of sync. Run python scripts/sync_marketplaces.py"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    print(sync(check=parser.parse_args().check))
