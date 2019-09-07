#!/bin/bash
iptables -F -t nat
iptables -X -t nat
iptables -t nat -I PREROUTING  -i enp0s8 -m set --match-set blacklist src -j DNAT --to-destination 192.168.101.99
iptables -t nat -I PREROUTING  -i enp0s8 -m set --match-set blacklist src -j LOG --log-prefix "REDIRECT blacklist entry PREROUTING"

iptables -t nat -A PREROUTING -i enp0s8 -j DNAT --to-destination 192.168.101.101
#iptables -t nat -A POSTROUTING -o enp0s9 -j SNAT --to-source 192.168.101.50
#iptables -A FORWARD -i enp0s8 -o enp0s9 -d 192.168.101.101 -j ACCEPT
#iptables -A FORWARD -i enp0s8 -o enp0s9 -d 192.168.101.99 -j ACCEPT
#iptables -t nat -A PREROUTING -i enp0s9 -j DNAT --to-destination 192.168.100.100
iptables -t nat -A POSTROUTING  -o enp0s8 -j SNAT --to-source 192.168.100.50
iptables -P FORWARD ACCEPT