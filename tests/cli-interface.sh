#!/bin/sh
# Regression tests for the public /usr/bin/eterban command-line interface.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test_tmp=$(mktemp -d)
trap 'rm -rf "$test_tmp"' EXIT HUP INT TERM
bin_dir="$test_tmp/bin"
mkdir -p "$bin_dir"
record="$test_tmp/record"

cat >"$bin_dir/python3" <<'EOF'
#!/bin/sh
printf 'python3 %s\n' "$*" >>"$ETERBAN_TEST_RECORD"
exit "${ETERBAN_TEST_STATUS:-0}"
EOF

cat >"$bin_dir/systemctl" <<'EOF'
#!/bin/sh
printf 'systemctl %s\n' "$*" >>"$ETERBAN_TEST_RECORD"
exit "${ETERBAN_TEST_STATUS:-0}"
EOF

cat >"$bin_dir/ipset" <<'EOF'
#!/bin/sh
printf 'ipset %s\n' "$*" >>"$ETERBAN_TEST_RECORD"
case "$1" in
    list)
        case " ${ETERBAN_TEST_LIST_FAILURES:-} " in
            *" $2 "*) exit 1 ;;
        esac
        printf 'Name: %s\nNumber of entries: %s\n192.0.2.1\n' "$2" "${ETERBAN_TEST_COUNT:-2}"
        ;;
    test)
        case " ${ETERBAN_TEST_MATCHES:-} " in
            *" $2 "*) exit 0 ;;
            *) exit 1 ;;
        esac
        ;;
esac
EOF
chmod 755 "$bin_dir/python3" "$bin_dir/systemctl" "$bin_dir/ipset"

# Keep the source launcher unchanged while redirecting its external effects to
# test doubles.  Absolute paths in the installed interface are intentional.
sed \
    -e "s|/usr/bin/python3|$bin_dir/python3|g" \
    -e "s|systemctl|$bin_dir/systemctl|g" \
    -e "s|ipset|$bin_dir/ipset|g" \
    "$root/gateway/usr/bin/eterban.sh" >"$test_tmp/eterban"

fail() {
    echo "cli-interface: $*" >&2
    exit 1
}

assert_status() {
    [ "$1" -eq "$2" ] || fail "status $1, expected $2"
}

assert_file() {
    expected=$1
    actual=$(cat "$2")
    [ "$actual" = "$expected" ] || fail "unexpected contents of $2: $actual"
}

run_cli() {
    : >"$record"
    : >"$test_tmp/stdout"
    : >"$test_tmp/stderr"
    if ETERBAN_TEST_RECORD="$record" ETERBAN_TEST_STATUS="${ETERBAN_TEST_STATUS:-0}" \
        ETERBAN_TEST_MATCHES="${ETERBAN_TEST_MATCHES:-}" ETERBAN_TEST_COUNT="${ETERBAN_TEST_COUNT:-2}" \
        ETERBAN_TEST_LIST_FAILURES="${ETERBAN_TEST_LIST_FAILURES:-}" \
        sh "$test_tmp/eterban" "$@" >"$test_tmp/stdout" 2>"$test_tmp/stderr"; then
        cli_status=0
    else
        cli_status=$?
    fi
}

ETERBAN_TEST_STATUS=0 ETERBAN_TEST_MATCHES='' run_cli count
assert_status "$cli_status" 0
assert_file 'Count of banned:
eterban_1: 2
eterban_1_ipv6: 2' "$test_tmp/stdout"

ETERBAN_TEST_STATUS=0 ETERBAN_TEST_MATCHES='' run_cli list
assert_status "$cli_status" 0
assert_file 'ipset list eterban_1
ipset list eterban_1_ipv6' "$record"

ETERBAN_TEST_STATUS=0 ETERBAN_TEST_MATCHES='' ETERBAN_TEST_LIST_FAILURES='eterban_1' run_cli count
assert_status "$cli_status" 1
[ ! -s "$test_tmp/stdout" ] || fail 'count emitted a false result after an ipset failure'

ETERBAN_TEST_STATUS=0 ETERBAN_TEST_MATCHES='' ETERBAN_TEST_LIST_FAILURES='eterban_1' run_cli list
assert_status "$cli_status" 1
assert_file 'ipset list eterban_1' "$record"

ETERBAN_TEST_STATUS=0 ETERBAN_TEST_MATCHES='eterban_1' run_cli check 192.0.2.1
assert_status "$cli_status" 0
assert_file '192.0.2.1 is BANNED (in eterban_1)' "$test_tmp/stdout"

ETERBAN_TEST_STATUS=0 ETERBAN_TEST_MATCHES='eterban_1_ipv6 eterban_white_ipv6' run_cli check 2001:db8::1
assert_status "$cli_status" 0
assert_file '2001:db8::1 is BANNED (in eterban_1_ipv6)
2001:db8::1 is WHITELISTED (in eterban_white_ipv6)' "$test_tmp/stdout"

ETERBAN_TEST_STATUS=0 ETERBAN_TEST_MATCHES='' run_cli search 192.0.2.1
assert_status "$cli_status" 0
assert_file '192.0.2.1
192.0.2.1' "$test_tmp/stdout"

for command in unban ban clear info reset pending permanent; do
    case "$command" in
        unban) args='192.0.2.1'; expected='/usr/share/eterban/unban.py 192.0.2.1' ;;
        ban) args='192.0.2.1'; expected='/usr/share/eterban/ban.py 192.0.2.1 blocked with eterban manually' ;;
        clear) args='--force'; expected='/usr/share/eterban/autoban_cli.py clear' ;;
        info|reset) args='192.0.2.1'; expected="/usr/share/eterban/autoban_cli.py $command 192.0.2.1" ;;
        pending|permanent) args=''; expected="/usr/share/eterban/autoban_cli.py $command" ;;
    esac
    ETERBAN_TEST_STATUS=23 ETERBAN_TEST_MATCHES='' run_cli "$command" $args
    assert_status "$cli_status" 23
    assert_file "python3 $expected" "$record"
done

ETERBAN_TEST_STATUS=0 ETERBAN_TEST_MATCHES='' run_cli clear
assert_status "$cli_status" 2
[ ! -s "$record" ] || fail 'clear without --force called a helper'

ETERBAN_TEST_STATUS=24 ETERBAN_TEST_MATCHES='' run_cli reload-whitelist
assert_status "$cli_status" 24
assert_file 'systemctl kill --signal=HUP eterban.service' "$record"

ETERBAN_TEST_STATUS=0 ETERBAN_TEST_MATCHES='' run_cli
assert_status "$cli_status" 0
grep -Fqx 'Usage:' "$test_tmp/stdout" || fail 'usage header changed'

ETERBAN_TEST_STATUS=0 ETERBAN_TEST_MATCHES='' run_cli unknown
assert_status "$cli_status" 0
grep -Fqx 'Usage:' "$test_tmp/stdout" || fail 'unknown-command usage changed'
