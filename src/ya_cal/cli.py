import argparse
import json
import os
import sys

from ya_mail.accounts import Problem

from . import accounts, wizard


def main():
    parser = argparse.ArgumentParser(prog="ya-ca")
    subs = parser.add_subparsers(dest="action", required=True)
    for name in ("connect", "connect-mail"):
        cmd = subs.add_parser(name)
        cmd.add_argument("--terminal", action="store_true")
        cmd.add_argument("--desktop-only", action="store_true", help=argparse.SUPPRESS)
    subs.add_parser("status")
    subs.add_parser("serve")
    config = subs.add_parser(
        "mcp-config", help="Показать JSON для подключения локального MCP-клиента"
    )
    config.add_argument(
        "client",
        choices=("claude-code", "claude-desktop", "cursor", "gemini", "vscode"),
    )
    subs.add_parser("disconnect").add_argument("email")
    try:
        args = parser.parse_args()
        if args.action == "serve":
            from .server import mcp

            mcp.run()
        elif args.action == "mcp-config":
            # Keep the venv interpreter path, including a symlink on Linux.
            server = {
                "command": os.path.abspath(sys.executable),
                "args": ["-I", "-B", "-m", "ya_cal.cli", "serve"],
            }
            group = "mcpServers"
            if args.client == "vscode":
                group = "servers"
                server["type"] = "stdio"
            print(json.dumps({group: {"ya-ca": server}}, indent=2))
        elif args.action == "status":
            print(json.dumps(accounts.profiles(), ensure_ascii=False, indent=2))
        elif args.action == "disconnect":
            accounts.forget(args.email)
            print(
                "Локальный доступ отключён. Для отзыва пароля откройте "
                + wizard.PASSWORDS
            )
        else:
            wizard.wizard(
                args.terminal, args.desktop_only, args.action == "connect-mail"
            )
    except (KeyboardInterrupt, EOFError):
        parser.exit(1, "Подключение прервано.\n")
    except Problem as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
