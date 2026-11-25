#!/bin/sh
set -eu
if command -v ya-ca >/dev/null 2>&1; then exec ya-ca connect "$@"; fi
if ! command -v uv >/dev/null 2>&1; then
  echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi
root=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
uv tool install --python 3.13 "$root"
uv tool update-shell
exec "$(uv tool dir --bin)/ya-ca" connect "$@"
