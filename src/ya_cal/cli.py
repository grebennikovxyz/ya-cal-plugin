import argparse
import json

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
    subs.add_parser("disconnect").add_argument("email")
    try:
        args = parser.parse_args()
        if args.action == "serve":
            from .server import mcp

            mcp.run()
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
