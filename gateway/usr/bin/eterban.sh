#!/bin/sh

setname="eterban_1"
setname_ipv6="eterban_1_ipv6"

command="$1"
[ -n "$command" ] && shift

if [ "$command" = "count" ] ; then
    echo "Count of banned:"
    # TODO: some quiet to ignore headers
    echo "$setname: $(ipset list $setname | wc -l)"
    echo "$setname_ipv6: $(ipset list $setname_ipv6 | wc -l)"
    exit
fi

if [ "$command" = "list" ] ; then
    ipset list $setname
    ipset list $setname_ipv6
    exit
fi

if [ "$command" = "unban" ] ; then
    /usr/share/eterban/unban.py $1
    exit
fi

if [ "$command" = "ban" ] ; then
    /usr/share/eterban/ban.py $1 "blocked with eterban manually"
    exit
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
    mask="$(echo "$1" | sed -e 's|\.|\\.|g')"
    ipset list $setname | grep --color "$mask"
    ipset list $setname_ipv6 | grep --color "$mask"
    exit
fi

if [ "$command" = "clear" ] ; then
    ipset flush $setname
    ipset flush $setname_ipv6
    exit
fi

if [ "$command" = "info" ] ; then
    /usr/share/eterban/autoban_cli.py info $1
    exit
fi

if [ "$command" = "reset" ] ; then
    /usr/share/eterban/autoban_cli.py reset $1
    exit
fi

if [ "$command" = "pending" ] ; then
    /usr/share/eterban/autoban_cli.py pending
    exit
fi

if [ "$command" = "permanent" ] ; then
    /usr/share/eterban/autoban_cli.py permanent
    exit
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
    clear         - remove all IPs from ban

Auto-unban commands:
    info <ip>     - show ban info and history for IP
    reset <ip>    - reset offense counter for IP
    pending       - list pending auto-unbans
    permanent     - list permanent bans
EOF
