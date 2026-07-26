#!/bin/sh
# Syntax-only regression checks for files shipped by the Eterban packages.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

find gateway prod-server ban-internal-server -type f -name '*.py' -exec \
    python3 -B -c 'import pathlib, sys; p = pathlib.Path(sys.argv[1]); compile(p.read_bytes(), str(p), "exec")' {} \;
find ban-server -type f -name '*.php' -exec php -l {} \;
find gateway prod-server common -type f -name '*.sh' -exec sh -n {} \;

if python3 gateway/usr/share/eterban/unban.py >/dev/null 2>&1; then
    echo 'unban.py without an IP must fail' >&2
    exit 1
fi

if python3 -c 'from pathlib import Path; p = Path("prod-server/usr/share/eterban/ban.py"); code = p.read_text().replace("/etc/eterban/settings.ini", "/nonexistent/eterban/settings.ini"); exec(compile(code, str(p), "exec"))' >/dev/null 2>&1; then
    echo 'ban.py without configuration must fail' >&2
    exit 1
fi
