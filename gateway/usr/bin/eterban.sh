#!/bin/sh

setname="eterban_1"
setname_ipv6="eterban_1_ipv6"

count_set() {
    output=$(ipset list "$1") || return 1
    printf '%s\n' "$output" | awk '/^Number of entries:/ { print $4; found=1 } END { if (!found) print 0 }'
}

command="$1"
[ -n "$command" ] && shift

if [ "$command" = "count" ] ; then
    count_v4=$(count_set "$setname") || exit 1
    count_v6=$(count_set "$setname_ipv6") || exit 1
    echo "Count of banned:"
    echo "$setname: $count_v4"
    echo "$setname_ipv6: $count_v6"
    exit
fi

if [ "$command" = "list" ] ; then
    ipset list "$setname" && ipset list "$setname_ipv6"
    exit $?
fi

if [ "$command" = "unban" ] ; then
    exec /usr/bin/python3 /usr/share/eterban/unban.py "$1"
fi

if [ "$command" = "ban" ] ; then
    exec /usr/bin/python3 /usr/share/eterban/ban.py "$1" "blocked with eterban manually"
fi

if [ "$command" = "check" ] ; then
    ip="$1"
    if [ -z "$ip" ] ; then
        echo "Usage: eterban check <ip>"
        exit 1
    fi
    found=0
    if echo "$ip" | grep -q ':' ; then
        # IPv6
        if ipset test $setname_ipv6 "$ip" 2>/dev/null ; then
            echo "$ip is BANNED (in $setname_ipv6)"
            found=1
        fi
        if ipset test eterban_white_ipv6 "$ip" 2>/dev/null ; then
            echo "$ip is WHITELISTED (in eterban_white_ipv6)"
            found=1
        fi
    else
        # IPv4
        if ipset test $setname "$ip" 2>/dev/null ; then
            echo "$ip is BANNED (in $setname)"
            found=1
        fi
        if ipset test firehol_level1 "$ip" 2>/dev/null ; then
            echo "$ip is in firehol_level1"
            found=1
        fi
        if ipset test eterban_white "$ip" 2>/dev/null ; then
            echo "$ip is WHITELISTED (in eterban_white)"
            found=1
        fi
    fi
    if [ "$found" = "0" ] ; then
        echo "$ip is NOT banned"
    fi
    exit
fi

if [ "$command" = "search" ] ; then
    mask="$1"
    ipset list "$setname" | grep --color=auto -F -- "$mask"
    ipset list "$setname_ipv6" | grep --color=auto -F -- "$mask"
    exit
fi

if [ "$command" = "clear" ] ; then
    if [ "$1" != "--force" ] ; then
        echo "Refusing to clear all bans without --force" >&2
        echo "Usage: eterban clear --force" >&2
        exit 2
    fi
    exec /usr/bin/python3 /usr/share/eterban/autoban_cli.py clear
fi

if [ "$command" = "reload-whitelist" ] ; then
    systemctl kill --signal=HUP eterban.service
    exit $?
fi

if [ "$command" = "info" ] ; then
    exec /usr/bin/python3 /usr/share/eterban/autoban_cli.py info "$1"
fi

if [ "$command" = "reset" ] ; then
    exec /usr/bin/python3 /usr/share/eterban/autoban_cli.py reset "$1"
fi

if [ "$command" = "pending" ] ; then
    exec /usr/bin/python3 /usr/share/eterban/autoban_cli.py pending
fi

if [ "$command" = "permanent" ] ; then
    exec /usr/bin/python3 /usr/share/eterban/autoban_cli.py permanent
fi

cat <<EOF
Usage:
    eterban <command> [args]

Commands:
    count         - print count of banned IPs
    list          - list all banned IPs
    check <ip>    - check if IP is banned (exact match)
    search <ip>   - search for ip in the list of banned IPs
    unban <ip>    - unban IP
    ban <ip>      - ban IP
    clear --force - queue removal of all active bans
    reload-whitelist - reload whitelist.txt without restarting eterban

Auto-unban commands:
    info <ip>     - show ban info and history for IP
    reset <ip>    - reset offense counter for IP
    pending       - list pending auto-unbans
    permanent     - list permanent bans
EOF
