Ya-Ca подключает Яндекс Календарь к Codex и другим локальным MCP-клиентам. Установите плагин одной командой из терминала своего пользователя.

Для Codex, Claude Code и OpenClaw также доступна установка из каталога GitHub. [Команды для маркетплейсов](https://github.com/grebennikovxyz/ya-cal-plugin#установка-из-маркетплейса)

**Windows x64 · PowerShell**

```powershell
irm https://github.com/grebennikovxyz/ya-cal-plugin/releases/latest/download/ya-ca-latest.ps1 | iex
```

**Linux · Терминал**

```sh
curl -fsSL https://github.com/grebennikovxyz/ya-cal-plugin/releases/latest/download/ya-ca-latest.sh | sh
```

Откройте новый чат Codex, выберите Ya-Ca и попросите «Подключи мой календарь». Мастер откроет настройки Яндекс ID и попросит ввести пароль CalDAV на вашем компьютере.

Также доступны автономный архив Windows x64, переносимый каталог Codex, ZIP для Plugin Creator и контрольные суммы. [Инструкции для других клиентов](https://github.com/grebennikovxyz/ya-cal-plugin#подключение-агента)
