#!/bin/sh
firehol_name="firehol_level1"
firehol_tmp="firehol_tmp"
wget https://iplists.firehol.org/files/firehol_level1.netset -O $firehol_name

ipset create $firehol_tmp hash:net

( echo "create $firehol_tmp hash:net family inet hashsize 1024 maxelem 65536" ;\
	cat $firehol_name | grep -v "^#" | sed -e "s|^\([0-9].*\)|add $firehol_tmp \1|" ) | ipset -exist restore

ipset swap $firehol_tmp $firehol_name
ipset destroy $firehol_tmp
