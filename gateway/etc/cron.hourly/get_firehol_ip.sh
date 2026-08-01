#!/bin/sh
set -eu

firehol_name="firehol_level1"
firehol_tmp="firehol_tmp"
filter="/usr/share/eterban/filter_firehol.py"
workdir="$(mktemp -d /tmp/eterban-firehol.XXXXXX)"
trap 'rm -rf "$workdir"' EXIT HUP INT TERM

download="$workdir/firehol_level1.netset"
wget --https-only --timeout=30 --tries=2 \
    https://iplists.firehol.org/files/firehol_level1.netset -O "$download"

test -s "$download"
grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(/[0-9]+)?$' "$download"

ipset destroy "$firehol_tmp" 2>/dev/null || :
ipset create "$firehol_tmp" hash:net

# Filter the netset through the whitelist: any network covered by eterban_white
# (typically bogon/RFC1918 that we whitelisted) is dropped before import.
(
    echo "create $firehol_tmp hash:net family inet hashsize 1024 maxelem 65536"
    python3 "$filter" "$firehol_tmp" < "$download"
) | ipset -exist restore

ipset swap "$firehol_tmp" "$firehol_name"
ipset destroy "$firehol_tmp"
