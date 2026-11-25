@echo off
setlocal
where ya-ca >nul 2>&1
if not errorlevel 1 goto start
where uv >nul 2>&1
if errorlevel 1 (
  echo Install uv: https://docs.astral.sh/uv/getting-started/installation/
  pause
  exit /b 1
)
uv tool install --python 3.13 "%~dp0."
if errorlevel 1 goto fail
uv tool update-shell
for /f "delims=" %%i in ('uv tool dir --bin') do "%%i\ya-ca.exe" connect %*
if errorlevel 1 goto fail
exit /b 0
:start
ya-ca connect %*
if errorlevel 1 goto fail
exit /b 0
:fail
pause
exit /b 1
