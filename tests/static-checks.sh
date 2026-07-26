#!/bin/sh
# Syntax-only regression checks for files shipped by the Eterban packages.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

find gateway prod-server ban-internal-server -type f -name '*.py' -exec \
    python3 -B -c 'import pathlib, sys; p = pathlib.Path(sys.argv[1]); compile(p.read_bytes(), str(p), "exec")' {} \;
find ban-server -type f -name '*.php' -exec php -l {} \;
find gateway prod-server common -type f -name '*.sh' -exec sh -n {} \;
