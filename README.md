# Ya-Ca

[![Boosty](https://img.shields.io/badge/Boosty-F15F2C?style=flat&logo=boosty&logoColor=white)](https://boosty.to/grebennikov.xyz/donate)<br>
<https://boosty.to/grebennikov.xyz/donate>

[![Стабильная версия](https://img.shields.io/github/v/release/grebennikovxyz/ya-cal-plugin?label=version&color=007ec6)](https://github.com/grebennikovxyz/ya-cal-plugin/releases/latest)
[![Лицензия](https://img.shields.io/github/license/grebennikovxyz/ya-cal-plugin?label=license&color=d4a600)](https://github.com/grebennikovxyz/ya-cal-plugin/blob/main/LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/grebennikovxyz/ya-cal-plugin?style=social)](https://github.com/grebennikovxyz/ya-cal-plugin/stargazers)
[![Сборка и тесты](https://github.com/grebennikovxyz/ya-cal-plugin/actions/workflows/verify.yml/badge.svg?branch=main)](https://github.com/grebennikovxyz/ya-cal-plugin/actions/workflows/verify.yml)

<img src="plugins/ya-ca/assets/ya-ca.png" alt="Лист календаря с датой 8 jun и расширением .ics" width="96" align="right">

Ya-Ca подключает Яндекс Календарь к локальному ИИ-агенту через MCP. Агент видит расписание по всем календарям выбранного аккаунта, ищет свободное время и помогает договориться о встрече. Приглашения, переносы, отмены и ответы участников можно отправлять из того же ящика через [Ya-Mail](https://github.com/grebennikovxyz/ya-mail-plugin).

> «Найди в четверг свободный час с 10 до 16 по рабочему и личному календарям. Поставь встречу в рабочий календарь и пригласи участников».

## Установка из маркетплейса

Для установки из GitHub нужны Git и `uvx` в PATH на компьютере, где работает агент. При первом обращении к календарю `uvx` загружает Python 3.13 и опубликованный пакет той же версии, что и плагин. Если в Windows нужен вариант со встроенным Python, используйте установщик из следующего раздела. [Установка uv и uvx](https://docs.astral.sh/uv/getting-started/installation/)

**Codex**

```sh
codex plugin marketplace add grebennikovxyz/ya-cal-plugin
codex plugin add ya-ca@grebennikov-calendar
```

**Claude Code**

```sh
claude plugin marketplace add grebennikovxyz/ya-cal-plugin
claude plugin install ya-ca@grebennikov-calendar
```

**OpenClaw**

```sh
openclaw plugins install ya-ca --marketplace grebennikovxyz/ya-cal-plugin
openclaw skills info ya-ca
```

Откройте новую сессию и попросите «Подключи мой календарь». OpenClaw получает и навык `ya-ca`, и инструменты MCP. Отдельный текст навыка можно установить из клона командой `openclaw skills install ./plugins/ya-ca/skills/ya-ca`, если сервер Ya-Ca уже подключён.

Для обновления каталога Claude Code выполните `claude plugin marketplace update grebennikov-calendar`, затем `claude plugin update ya-ca@grebennikov-calendar`. В Codex для GitHub-каталога используйте `codex plugin marketplace upgrade grebennikov-calendar`, затем повторите `codex plugin add ya-ca@grebennikov-calendar`. Для OpenClaw повторите команду установки с `--force`, чтобы заменить установленную копию. Если Ya-Ca установлен из релиза одной командой, для обновления повторите именно её.

## Установка одной командой

Откройте терминал под тем же пользователем, который запускает Codex. Команда скачивает текущий стабильный релиз, проверяет SHA-256 и регистрирует Ya-Ca в установленном Codex.

**Windows x64 — PowerShell**

```powershell
irm https://github.com/grebennikovxyz/ya-cal-plugin/releases/latest/download/ya-ca-latest.ps1 | iex
```

**Linux — терминал**

```sh
curl -fsSL https://github.com/grebennikovxyz/ya-cal-plugin/releases/latest/download/ya-ca-latest.sh | sh
```

В Windows Python входит в комплект. В Linux нужны `curl`, `sha256sum` и `flock`. Установщик использует существующий `uv` или загружает его в папку Ya-Ca и готовит Python 3.13. Установка выполняется с правами обычного пользователя. Чтобы обновиться, повторите ту же команду. Подключённые аккаунты и разрешения хранятся отдельно от программы.

**Первый вход.** В новом чате Codex выберите Ya-Ca и попросите «Подключи мой календарь». Мастер откроет Яндекс ID. Выберите **Безопасность → Пароли приложений → Календарь (CalDAV)**, создайте пароль с именем `Ya-Ca` и вставьте его в локальное окно. Укажите полный email, часовой пояс и разрешения. Когда подключение готово, попросите показать события на завтра. [Пароли приложений](https://id.yandex.ru/security/app-passwords) · [Справка Яндекса](https://yandex.ru/support/yandex-360/customers/calendar/web/ru/data-exchange/synchronization/sync-desktop)

Для приглашений подключите тот же адрес в мастере Ya-Mail с правом отправки. Для текстового режима используйте `connect --terminal`, для подключения почты — `connect-mail --terminal`. Установщик выводит путь к команде Ya-Ca.

| Система | Как открыть текстовый мастер после установки |
| --- | --- |
| Windows, PowerShell | `& "$env:LOCALAPPDATA\Ya-Ca\ya-ca.cmd" connect --terminal` |
| Linux | `"${XDG_DATA_HOME:-$HOME/.local/share}/ya-ca/ya-ca" connect --terminal` |

В Linux пароль сохраняется в разблокированном Secret Service пользовательской D-Bus-сессии. Для графического окна нужен Tk.

## Скачать файлы вручную

Постоянные ссылки ведут на файлы последней стабильной версии. На странице конкретного релиза доступны те же файлы и их контрольные суммы. [Все релизы](https://github.com/grebennikovxyz/ya-cal-plugin/releases)

| Файл | Назначение |
| --- | --- |
| [ya-ca-latest-windows-x64.zip](https://github.com/grebennikovxyz/ya-cal-plugin/releases/latest/download/ya-ca-latest-windows-x64.zip) | Автономная сборка Windows x64. Распакуйте и запустите `connect.cmd`. |
| [ya-ca-latest.zip](https://github.com/grebennikovxyz/ya-cal-plugin/releases/latest/download/ya-ca-latest.zip) | Переносимый каталог Codex для Windows и Linux с `uv`. Запустите `connect.cmd` или `sh connect.sh`. |
| [ya-ca-latest-plugin.zip](https://github.com/grebennikovxyz/ya-cal-plugin/releases/latest/download/ya-ca-latest-plugin.zip) | Один плагин Agent Plugins 1.0 для Plugin Creator и локальных исполнителей. |
| [SHA256SUMS.txt](https://github.com/grebennikovxyz/ya-cal-plugin/releases/latest/download/SHA256SUMS.txt) | Контрольные суммы архивов, установщиков и wheel. |

## Подключение агента

При установке одной командой Ya-Ca появляется в Codex автоматически, если доступна команда `codex` или приложение Codex для Windows со встроенным CLI. При ручной установке из каталога или исходников выполните из папки с `.agents/plugins/marketplace.json`:

```sh
codex plugin marketplace add .
codex plugin add ya-ca@grebennikov-calendar
```

**Claude Code, Claude Desktop, Cursor, Gemini CLI и VS Code.** Команда ниже выводит JSON с абсолютным путём к установленному интерпретатору и аргументами запуска. Выберите свой клиент в таблице и добавьте запись `ya-ca` в соответствующий раздел настроек, сохранив остальные серверы.

```sh
ya-ca mcp-config cursor
```

После установки одной командой в Windows используйте:

```powershell
& "$env:LOCALAPPDATA\Ya-Ca\ya-ca.cmd" mcp-config cursor
```

| Клиент | Аргумент `mcp-config` | Куда добавить запись |
| --- | --- | --- |
| Claude Code | `claude-code` | `mcpServers` в `.mcp.json` проекта. [Документация](https://code.claude.com/docs/en/mcp) |
| Claude Desktop | `claude-desktop` | `mcpServers` в `claude_desktop_config.json` через Settings → Developer → Edit Config. [Документация](https://modelcontextprotocol.io/docs/develop/connect-local-servers) |
| Cursor | `cursor` | `mcpServers` в `~/.cursor/mcp.json` или `.cursor/mcp.json` проекта. [Документация](https://cursor.com/docs/mcp) |
| Gemini CLI | `gemini` | `mcpServers` в `~/.gemini/settings.json`. [Документация](https://geminicli.com/docs/tools/mcp-server/) |
| VS Code с GitHub Copilot | `vscode` | `servers` в `.vscode/mcp.json` или в пользовательской конфигурации MCP. [Документация](https://code.visualstudio.com/docs/copilot/reference/mcp-configuration) |

Перезапустите или перезагрузите MCP-сервер в клиенте. Для Claude Code состояние подключения показывает `claude mcp list`, для Gemini CLI — `gemini mcp list`. Через чат вызовите `list_accounts`, затем `list_calendars` с выбранным адресом. Другие локальные клиенты MCP могут запустить `ya-ca serve` как дочерний процесс по stdio. Пароли в JSON-конфигурации не нужны.

**Plugin Creator.** Выберите `ya-ca-latest-plugin.zip`. В его корне лежат `plugin.json`, `mcp.json`, навык, иконка и wheel Ya-Ca. Локальный исполнитель должен поддерживать stdio, подстановку `${PLUGIN_ROOT}` и команду `uv` в PATH. При первом старте `uv` устанавливает зависимости из сети. Вход доступен через инструмент `open_connection_wizard`. Для работы в веб-клиенте без локального исполнителя потребовалось бы отдельное удалённое подключение.

## Что умеет Ya-Ca

| Задача | Поведение |
| --- | --- |
| Посмотреть повестку | Объединяет календари выбранного аккаунта. При совпадении времени первым показывает событие из календаря с более высоким приоритетом. |
| Навести порядок | Задаёт календарю группу (рабочий, личный, общественный, другой) и приоритет от 0 до 100. Ищет события по тексту, участникам, месту и тегам. Теги сохраняются в iCalendar `CATEGORIES`. |
| Найти свободное окно | Учитывает события на весь день, повторения и исключения. Отменённые, прозрачные события и встречи, от которых пользователь отказался, освобождают время. |
| Создать или перенести встречу | Перед записью проверяет занятость по календарям аккаунта. Если есть пересечение, возвращает конфликт. Можно изменить одно повторение или целую серию, задать участников и напоминания. |
| Работать с почтой | Читает календарные вложения по ссылке на письмо из Ya-Mail. Для встреч под управлением Ya-Ca готовит письма iCalendar REQUEST, CANCEL или REPLY. По просьбе пользователя отправляет их и показывает результат SMTP для каждого адресата. |

Для повторяющейся серии проверка охватывает до 366 дней вперёд. Границы периода возвращаются в результате. Проверка занятости и запись — отдельные операции CalDAV: между ними другое устройство может занять время. Изменение существующего события защищено проверкой версии ETag. Серверные встречи используют механизм планирования своего провайдера.

Если отправка прервалась, `list_notifications` покажет состояние очереди. Повторяйте отправку с прежним `change_id`. При неоднозначном ответе SMTP Ya-Mail сохраняет Message-ID для проверки. Статус принятия письма относится к почтовому серверу.

## Данные и отключение

Пароли календаря и почты хранятся раздельно в системном хранилище. Локальная SQLite хранит настройки, очередь уведомлений и результаты отправки. Клиент агента получает результаты вызванных инструментов. Поиск переписки и обычные почтовые операции доступны в отдельном плагине Ya-Mail.

`ya-ca status` показывает аккаунты и разрешения. `ya-ca disconnect EMAIL` удаляет локальный доступ к календарю, настройки и очередь для этого адреса. Для отзыва пароля удалите его в Яндекс ID. Почтовой учётной записью управляет Ya-Mail.

## Разработка

Требуется Python 3.13 или новее. Из корня репозитория:

```sh
uv run --python 3.13 --with pytest python -m pytest -q
uv run --python 3.13 python scripts/package.py
```

В `dist/` появятся wheel, ZIP для Plugin Creator, переносимый каталог Codex и SHA-256 текущей сборки. Для автономного Windows x64 добавьте к команде сборки `--windows-runtime ПУТЬ` к чистой Windows x64 сборке CPython 3.13 от python-build-standalone. В CI выполняются протокольные тесты с синтетическими данными и проверяется запуск собранного пакета. Вход в Яндекс и доставка реальному адресату требуют отдельной проверки с тестовыми аккаунтами.

### Выпуск новой версии

Измените `project.version` в `pyproject.toml`, выполните `python scripts/sync_marketplaces.py` и закоммитьте результат. Скрипт обновит манифесты Codex, Claude Code и Agent Plugins, версию навыка OpenClaw и ссылку MCP на wheel. Claude Code и OpenClaw читают один каталог GitHub. CI проверяет согласованность версий и установку из каталога перед публикацией.

Отправьте тег `vX.Y.Z` для этого коммита. GitHub Actions выпустит архивы, проверит установку публичной версии на Windows и Linux и опубликует `SKILL.md` в ClawHub с той же версией и тегом `latest`. Для ClawHub задайте один раз секрет репозитория `CLAWHUB_TOKEN` с правом публикации. Сбой публикации виден в задаче `clawhub`. После исправления повторите упавшую задачу в GitHub Actions. PickAPlugin рассматривает заявку редакционно и перечитывает свои публичные источники ежедневно. [Правила PickAPlugin](https://pickaplugin.com/submit)

Ya-Ca — независимый проект. Товарный знак «Яндекс» принадлежит ООО «ЯНДЕКС». Код и иконка распространяются под Apache-2.0. Для текста навыка в ClawHub также доступна MIT-0. [Лицензия Apache 2.0](LICENSE) · [MIT-0](https://spdx.org/licenses/MIT-0.html) · [Уведомления](NOTICE)
