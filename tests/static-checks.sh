#!/bin/sh
# Syntax-only regression checks for files shipped by the Eterban packages.
set -eu
export PYTHONDONTWRITEBYTECODE=1

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

find gateway prod-server ban-internal-server -type f -name '*.py' -exec \
    python3 -B -c 'import pathlib, sys; p = pathlib.Path(sys.argv[1]); compile(p.read_bytes(), str(p), "exec")' {} \;
find ban-server -type f -name '*.php' -exec php -l {} \;
find gateway prod-server common -type f -name '*.sh' -exec sh -n {} \;

if printf '%s\n' '[Settings]' | python3 -c 'from pathlib import Path; p = Path("gateway/usr/share/eterban/unban.py"); code = p.read_text().replace("/etc/eterban/settings.ini", "/proc/self/fd/0"); exec(compile(code, str(p), "exec"))' >/dev/null 2>&1; then
    echo 'unban.py without an IP must fail' >&2
    exit 1
fi

if python3 -c 'from pathlib import Path; p = Path("prod-server/usr/share/eterban/ban.py"); code = p.read_text().replace("/etc/eterban/settings.ini", "/nonexistent/eterban/settings.ini"); exec(compile(code, str(p), "exec"))' >/dev/null 2>&1; then
    echo 'ban.py without configuration must fail' >&2
    exit 1
fi

if (cd gateway/usr/share/eterban && python3 -c 'from pathlib import Path; p = Path("eterban_switcher.py"); code = p.read_text().replace("/etc/eterban/settings.ini", "/dev/null").replace("/var/log/eterban/eterban.log", "/tmp/eterban-switcher-static-check.log"); exec(compile(code, str(p), "exec"))') >/dev/null 2>&1; then
    echo 'switcher without configuration must fail' >&2
    exit 1
else
    status=$?
fi
if [ "$status" -ne 78 ]; then
    echo "switcher without configuration returned $status, expected 78" >&2
    exit 1
fi

if (cd ban-internal-server/data/www && python3 -c 'from pathlib import Path; p = Path("int2.py"); code = p.read_text().replace("/etc/eterban/settings.ini", "/dev/null"); exec(compile(code, str(p), "exec"))') >/dev/null 2>&1; then
    echo 'internal service without configuration must fail' >&2
    exit 1
else
    status=$?
fi
if [ "$status" -ne 78 ]; then
    echo "internal service without configuration returned $status, expected 78" >&2
    exit 1
fi

if printf '%s\n' '[API]' 'rate_limit_per_minute = 0' | (cd gateway/usr/share/eterban && python3 -c 'from pathlib import Path; p = Path("eterban_api.py"); code = p.read_text().replace("/etc/eterban/settings.ini", "/proc/self/fd/0"); exec(compile(code, str(p), "exec"))') >/dev/null 2>&1; then
    echo 'API service with invalid configuration must fail' >&2
    exit 1
else
    status=$?
fi
if [ "$status" -ne 78 ]; then
    echo "API service with invalid configuration returned $status, expected 78" >&2
    exit 1
fi

python3 -c 'import importlib.util; p = "gateway/usr/share/eterban/eterban_api.py"; s = importlib.util.spec_from_file_location("eterban_api", p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); m.ipset_test = lambda setname, ip: None; assert m.check_ip("192.0.2.1") == {"error": "ipset query failed"}'

python3 -c 'import importlib.util; p = "ban-internal-server/data/www/int2.py"; s = importlib.util.spec_from_file_location("eterban_internal", p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); m.get_original_dst = lambda request: ("192.0.2.1", 80); m.read_settings = lambda path: (_ for _ in ()).throw(KeyError("Settings")); f = type("F", (), {"path": "/unban", "request": object(), "client_address": ("198.51.100.1", 1), "send_error": lambda self, status, message: setattr(self, "response", (status, message))})(); m.OriginalDstHandler.do_GET(f); assert f.response[0] == 503' >/dev/null 2>&1

if rg -q 'exec /usr/share/eterban/.*\.py' gateway/usr/bin/eterban.sh || ! rg -qx 'actionban = /usr/bin/python3 /usr/share/eterban/ban.py <ip> <name>' prod-server/etc/fail2ban/action.d/eterban.conf; then
    echo 'Python scripts installed with mode 0644 must be invoked through python3' >&2
    exit 1
fi

sh tests/cli-interface.sh
