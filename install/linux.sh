#!/bin/sh
# Generated release installer. All files belong to the current user.
set -eu
umask 077
root="${XDG_DATA_HOME:-$HOME/.local/share}/ya-ca"
versions="$root/versions"
release="$versions/v@VERSION@"
mkdir -p "$versions" "$root/envs"
exec 9>"$root/install.lock"
flock -x 9
temp=$(mktemp -d "$versions/.install.XXXXXXXX")
trap 'rm -rf -- "$temp"' EXIT
trap 'exit 1' HUP INT TERM

if command -v uv >/dev/null 2>&1; then
    uv=$(command -v uv)
elif [ -x "$root/tools/uv" ]; then
    uv="$root/tools/uv"
else
    curl -fsSL --retry 3 https://github.com/astral-sh/uv/releases/download/0.13.5/uv-installer.sh -o "$temp/uv.sh"
    (cd "$temp" && echo '1c6e7f025499664633ac2dce43a210800510e9ef0625c52e034a8afdf8bf177a  uv.sh' | sha256sum -c -)
    UV_UNMANAGED_INSTALL="$root/tools" sh "$temp/uv.sh"
    uv="$root/tools/uv"
fi

envdir="$root/envs/v@VERSION@"
if [ ! -x "$envdir/bin/python" ]; then
    "$uv" venv --python 3.13 "$envdir"
fi
python="$envdir/bin/python"
if [ ! -d "$release" ]; then
    curl -fsSL --retry 3 '@RELEASE_URL@/ya-ca-latest.zip' -o "$temp/package.zip"
    (cd "$temp" && echo '@DIGEST@  package.zip' | sha256sum -c -)
    "$python" -I -m zipfile -e "$temp/package.zip" "$temp/content"
    mv -T -- "$temp/content" "$release"
fi
(cd "$release" && "$uv" pip install --python "$python" './grebennikov_ya_ca-@VERSION@-py3-none-any.whl')
"$python" -I -B "$release/activate.py"
