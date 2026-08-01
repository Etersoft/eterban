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

python3 -c 'import ast, pathlib; tree = ast.parse(pathlib.Path("gateway/usr/share/eterban/eterban_switcher.py").read_text()); node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "nonempty_stream_entries"); module = ast.Module(body=[node], type_ignores=[]); ns = {}; exec(compile(module, "eterban_switcher.py", "exec"), ns); f = ns["nonempty_stream_entries"]; assert f({b"eterban:commands": [[]]}) == []; assert f({b"eterban:commands": [[b"1-0", {b"command": b"ban"}]]}) == [(b"eterban:commands", [[b"1-0", {b"command": b"ban"}]])]'

python3 -c 'import importlib.util; p = "ban-internal-server/data/www/int2.py"; s = importlib.util.spec_from_file_location("eterban_internal", p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); m.get_original_dst = lambda request: ("192.0.2.1", 80); m.read_settings = lambda path: (_ for _ in ()).throw(KeyError("Settings")); f = type("F", (), {"path": "/unban", "request": object(), "client_address": ("198.51.100.1", 1), "send_error": lambda self, status, message: setattr(self, "response", (status, message))})(); m.OriginalDstHandler.do_GET(f); assert f.response[0] == 503' >/dev/null 2>&1

if rg -q 'exec /usr/share/eterban/.*\.py' gateway/usr/bin/eterban.sh || ! rg -qx 'actionban = /usr/bin/python3 /usr/share/eterban/ban.py <ip> <name>' prod-server/etc/fail2ban/action.d/eterban.conf; then
    echo 'Python scripts installed with mode 0644 must be invoked through python3' >&2
    exit 1
fi

sh tests/cli-interface.sh

rg -Fq "ban_server + ':81'" gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq "'[' + ban_server_ipv6 + ']:81'" gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq "'80,81,443'" gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq "ipset_firehol, 'src', '-p', 'tcp', '-j', 'DNAT'" gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq "ipset_eterban_1, 'src', '-p', 'tcp', '-j', 'DNAT'" gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq "ipset_eterban_1_ipv6, 'src', '-p', 'tcp', '-j', 'DNAT'" gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq 'claim_interval_seconds = 60' gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq 'time.monotonic() >= next_claim_at' gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq 'socket_timeout=10' gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq 'def nonempty_stream_entries(response):' gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq "['ipset', 'list', name]" gateway/usr/share/eterban/eterban_switcher.py || {
    echo 'external IPv4/IPv6 ban redirects must target public port 81' >&2
    exit 1
}

# Internal interface: whitelisted destinations must bypass the ban DNAT,
# symmetric in create (-I) and destroy (-D) for both IPv4 and IPv6.
rg -Fq "'--match-set', ipset_eterban_white, 'dst', '-j', 'ACCEPT'" gateway/usr/share/eterban/eterban_switcher.py && \
rg -Fq "'--match-set', ipset_eterban_white_ipv6, 'dst', '-j', 'ACCEPT'" gateway/usr/share/eterban/eterban_switcher.py && \
[ "$(rg -Fc "'--match-set', ipset_eterban_white, 'dst', '-j', 'ACCEPT'" gateway/usr/share/eterban/eterban_switcher.py)" -ge 2 ] && \
[ "$(rg -Fc "'--match-set', ipset_eterban_white_ipv6, 'dst', '-j', 'ACCEPT'" gateway/usr/share/eterban/eterban_switcher.py)" -ge 2 ] || {
    echo 'internal interface must whitelist destinations before ban DNAT (create+destroy, v4+v6)' >&2
    exit 1
}

# filter_firehol: drop netset networks covered by the whitelist, keep the rest.
python3 -c '
import importlib.util, ipaddress
p = "gateway/usr/share/eterban/filter_firehol.py"
s = importlib.util.spec_from_file_location("filter_firehol", p)
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
wl = [ipaddress.ip_network("10.0.0.0/8")]
out, dropped = m.filter_netset(["10.0.0.0/8", "10.20.30.0/24", "203.0.113.0/24", "# comment", "junk"], wl, "firehol_tmp")
assert out == ["add firehol_tmp 203.0.113.0/24"], out
assert dropped == 2, dropped
# A network that merely contains a whitelisted subnet is NOT split/dropped
# (kept as-is); finer-grained holes are guaranteed by the iptables ACCEPT rule.
out2, dropped2 = m.filter_netset(["10.0.0.0/8"], [ipaddress.ip_network("10.20.30.0/24")], "firehol_tmp")
assert out2 == ["add firehol_tmp 10.0.0.0/8"], out2
assert dropped2 == 0, dropped2
# Missing/empty whitelist → passthrough.
out3, dropped3 = m.filter_netset(["203.0.113.0/24"], [], "firehol_tmp")
assert out3 == ["add firehol_tmp 203.0.113.0/24"], out3
assert dropped3 == 0, dropped3
'

rg -Fq 'python3 "$filter" "$firehol_tmp" < "$download"' gateway/etc/cron.hourly/get_firehol_ip.sh || {
    echo 'firehol import must run imported networks through the whitelist filter' >&2
    exit 1
}

rg -Fqx '        listen 81;' ban-server/etc/nginx/sites-enabled.d/eterban.conf && \
rg -Fq 'run_server(settings['"'"'ban_server'"'"'])' ban-internal-server/data/www/int2.py && \
rg -Fq 'port=82' ban-internal-server/data/www/int2.py && \
rg -Fq 'Для разблокировки нажмите:' ban-server/data/www/index.html && \
rg -Fq 'You accessed:' ban-internal-server/data/www/int2.py || {
    echo 'public and internal ban pages must remain separate user flows' >&2
    exit 1
}

for unit in gateway/etc/systemd/system/eterban.service gateway/etc/systemd/system/eterban-api.service gateway/etc/systemd/system/eterban-internal.service; do
    for directive in 'NoNewPrivileges=true' 'PrivateTmp=true' 'ProtectHome=true' 'ProtectSystem=full' 'UMask=0077'; do
        rg -qx "$directive" "$unit" || {
            echo "$unit is missing $directive" >&2
            exit 1
        }
    done
done

awk '
    $0 == "%files common" { section = "common"; next }
    /^%files/ { section = "other" }
    $0 == "%_datadir/%name/ban.py" {
        if (section == "common") common_ban = 1
        else misplaced_ban = 1
    }
    END { exit !(common_ban && !misplaced_ban) }
' eterban.spec || {
    echo 'ban.py must be owned by eterban-common for the public CLI and fail2ban' >&2
    exit 1
}

awk '
    $0 == "%package gateway" { in_gateway = 1; next }
    in_gateway && /^%description gateway/ { exit !(has_crontabs && has_logrotate) }
    in_gateway && /^Requires:/ {
        if ($0 ~ /(^|[[:space:]])crontabs([[:space:]]|$)/) has_crontabs = 1
        if ($0 ~ /(^|[[:space:]])logrotate([[:space:]]|$)/) has_logrotate = 1
    }
    END { exit !(has_crontabs && has_logrotate) }
' eterban.spec || {
    echo 'gateway package must require crontabs and logrotate' >&2
    exit 1
}
