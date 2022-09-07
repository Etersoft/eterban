#!/bin/sh

setname="eterban_1"

command="$1"
[ -n "$command" ] && shift

if [ "$command" = "count" ] ; then
    echo "Count of banned:"
    ipset list $setname | wc -l
    exit
fi

if [ "$command" = "list" ] ; then
    ipset list $setname
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
