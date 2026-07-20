#!/bin/sh
set -eu

firehol_name="firehol_level1"
firehol_tmp="firehol_tmp"
workdir="$(mktemp -d /tmp/eterban-firehol.XXXXXX)"
trap 'rm -rf "$workdir"' EXIT HUP INT TERM

download="$workdir/firehol_level1.netset"
wget --https-only --timeout=30 --tries=2 \
    https://iplists.firehol.org/files/firehol_level1.netset -O "$download"

test -s "$download"
grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(/[0-9]+)?$' "$download"

ipset destroy "$firehol_tmp" 2>/dev/null || :
ipset create "$firehol_tmp" hash:net

(
    echo "create $firehol_tmp hash:net family inet hashsize 1024 maxelem 65536"
    sed -n -E 's/^([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(\/[0-9]+)?)$/add '"$firehol_tmp"' \1/p' "$download"
) | ipset -exist restore

ipset swap "$firehol_tmp" "$firehol_name"
ipset destroy "$firehol_tmp"
