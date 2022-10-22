#!/bin/sh

setname="eterban_1"
setname_ipv6="eterban_1_ipv6"

command="$1"
[ -n "$command" ] && shift

if [ "$command" = "count" ] ; then
    echo "Count of banned:"
    # TODO: some quiet to ignore headers
    ipset list $setname | wc -l
    ipset list $setname_ipv6 | wc -l
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

if [ "$command" = "search" ] ; then
    mask="$(echo "$1" | sed -e 's|\.|\\.|g')"
    ipset list $setname | grep --color "$mask"
    ipset list $setname_ipv6 | grep --color "$mask"
    exit
fi

cat <<EOF
Usage:
    eterban [count|list|search <ip>]

       count       - print count of banned IPs
       list        - list all banned IPs
       search <ip> - search for ip in the list of banned IPs
       unban <ip>  - unban IP
       ban <ip>    - ban IP
EOF
