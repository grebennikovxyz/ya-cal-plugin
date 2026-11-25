import getpass
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from queue import Empty, Queue

from ya_mail.accounts import Problem, address

from . import accounts
from .dav import session

PASSWORDS = "https://id.yandex.ru/security/app-passwords"
GUIDE = "https://yandex.ru/support/yandex-360/customers/calendar/web/ru/data-exchange/synchronization/sync-desktop"
HINT = (
    "Войдите в нужный Яндекс ID. Откройте «Безопасность → Пароли приложений», "
    "выберите «Календарь» (CalDAV), укажите название Ya-Ca и нажмите «Создать». "
    "Скопируйте пароль. Яндекс показывает его один раз, он действует до отзыва."
)
FORM = "Введите полный адрес этого аккаунта и созданный пароль приложения. Выберите часовой пояс для дат и режим доступа."
TERMINAL = "ya-ca connect --terminal"
VAULT_HINT = (
    "Не удалось открыть системное хранилище паролей. В Windows проверьте Диспетчер учётных данных, "
    "в Linux разблокируйте Secret Service в пользовательской D-Bus-сессии и повторите подключение."
)


def connect(email, password, mode, tz):
    email = address(email).lower()
    accounts.timezone(tz)
    if not password.strip() or mode not in ("read", "write"):
        raise Problem("Введите пароль приложения и выберите режим доступа.")
    acc = accounts.Account(email, mode, tz, password.strip())
    with session(acc) as store:
        count = len(store.info)
    if not count:
        raise Problem(
            "Яндекс не вернул календарей. Проверьте аккаунт и создайте календарь в веб-интерфейсе."
        )
    try:
        accounts.save(acc)
    except Exception:
        raise Problem(VAULT_HINT) from None
    return count


def terminal():
    if not sys.stdin.isatty():
        raise Problem("Откройте интерактивный терминал и выполните " + TERMINAL)
    print("Шаг 1 из 3. Создайте пароль календаря.\n" + HINT + "\n" + PASSWORDS)
    if (
        input(
            "Enter — открыть Яндекс ID в браузере, минус — открыть ссылку самостоятельно: "
        ).strip()
        != "-"
    ):
        webbrowser.open(PASSWORDS)
    print("Шаг 2 из 3. " + FORM)
    while True:
        email = input("Полный email: ").strip()
        zone = input("Часовой пояс [Europe/Moscow]: ").strip() or "Europe/Moscow"
        mode = input("1 — чтение, 2 — чтение и редактирование [1]: ").strip() or "1"
        if mode not in ("1", "2"):
            print("Выберите 1 или 2.")
            continue
        password = getpass.getpass("Пароль приложения CalDAV (скрытый ввод): ")
        try:
            count = connect(email, password, "write" if mode == "2" else "read", zone)
        except Problem as err:
            print(str(err))
            if input("Повторить ввод? [Д/н]: ").lower() in ("н", "нет", "n", "no"):
                return
        else:
            print(f"Шаг 3 из 3. Подключён {email}. Доступно календарей: {count}.")
            print(
                "Для приглашений подключите этот же адрес с отправкой писем: ya-ca connect-mail"
            )
            return
        finally:
            password = ""


def window():
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Ya-Ca · Подключение календаря")
    from pathlib import Path

    icon = Path(__file__).with_name("assets") / "ya-ca.png"
    if not icon.is_file():
        icon = Path(__file__).resolve().parents[2] / "plugins/ya-ca/assets/ya-ca.png"
    if icon.is_file():
        root.iconphoto(True, tk.PhotoImage(file=str(icon)))
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill="both", expand=True)
    email, password = tk.StringVar(), tk.StringVar()
    zone, mode = tk.StringVar(value="Europe/Moscow"), tk.StringVar(value="read")
    queue = Queue()

    def clear():
        for widget in frame.winfo_children():
            widget.destroy()

    def label(text, heading=False):
        ttk.Label(
            frame,
            text=text,
            wraplength=480,
            justify="left",
            font=("TkDefaultFont", 14 if heading else 10),
        ).pack(anchor="w", pady=5)

    def button(text, action):
        ttk.Button(frame, text=text, command=action).pack(anchor="w", pady=5)

    def first():
        clear()
        label("1 из 3 · Создайте пароль календаря", True)
        label(HINT)
        label(PASSWORDS)
        button("Открыть Яндекс ID", lambda: webbrowser.open(PASSWORDS))
        button("Справка Яндекса", lambda: webbrowser.open(GUIDE))
        button("Пароль скопирован · Далее", form)

    def form(error=""):
        clear()
        label("2 из 3 · Подключите аккаунт", True)
        label(FORM)
        if error:
            label(error)
        for title, variable, mask in (
            ("Email", email, ""),
            ("Пароль CalDAV", password, "*"),
            ("Часовой пояс", zone, ""),
        ):
            label(title)
            ttk.Entry(frame, textvariable=variable, show=mask, width=48).pack(fill="x")
        for text, value in (
            ("Только чтение", "read"),
            ("Чтение и редактирование", "write"),
        ):
            ttk.Radiobutton(frame, text=text, variable=mode, value=value).pack(
                anchor="w"
            )
        button("Проверить и подключить", verify)
        button("Назад", first)

    def verify():
        args = email.get(), password.get(), mode.get(), zone.get().strip()
        password.set("")
        clear()
        label("Проверяем доступные календари…")

        def worker():
            try:
                queue.put((connect(*args), None))
            except Problem as exc:
                queue.put((0, str(exc)))
            except Exception:
                queue.put(
                    (
                        0,
                        "Не удалось подключиться. Проверьте доступ к Яндексу и повторите ввод.",
                    )
                )

        threading.Thread(target=worker, daemon=True).start()
        root.after(125, finish)

    def finish():
        try:
            count, err = queue.get_nowait()
        except Empty:
            root.after(125, finish)
            return
        if err:
            form(err)
            return
        clear()
        label("3 из 3 · Календарь подключён", True)
        label(
            f"{email.get()} · Доступно календарей: {count}. Попросите агента показать ближайшие события."
        )
        label(
            "Для отправки приглашений подключите тот же адрес в Ya-Mail с правом отправки."
        )
        button("Открыть мастер Ya-Mail", lambda: spawn(["connect-mail"]))
        button("Готово", root.destroy)

    first()
    root.mainloop()


def spawn(args):
    cmd = [sys.executable, "-m", "ya_cal.cli", *args]
    if os.name == "nt":
        subprocess.Popen(
            cmd, creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True
        )
        return True
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        for name, flag in (
            ("x-terminal-emulator", "-e"),
            ("gnome-terminal", "--"),
            ("konsole", "-e"),
            ("xterm", "-e"),
        ):
            if exe := shutil.which(name):
                subprocess.Popen(
                    [exe, flag, *cmd],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
        if "connect" in args and "--terminal" not in args:
            subprocess.Popen(
                [*cmd, "--desktop-only"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
    return False


def launch():
    return {
        "launched": spawn(["connect"]),
        "terminal_command": TERMINAL,
        "password_settings": PASSWORDS,
    }


def wizard(text=False, desktop_only=False, mail=False):
    if mail:
        from ya_mail.wizard import terminal as tty
        from ya_mail.wizard import window as gui
    else:
        tty, gui = terminal, window
    if not text:
        try:
            import tkinter as tk
        except ImportError:
            pass
        else:
            try:
                gui()
                return
            except tk.TclError:
                pass
    if desktop_only:
        raise Problem("Графическая среда недоступна. Откройте терминал: " + TERMINAL)
    if (
        not sys.stdin.isatty()
        and not text
        and spawn(["connect-mail" if mail else "connect", "--terminal"])
    ):
        return
    tty()
