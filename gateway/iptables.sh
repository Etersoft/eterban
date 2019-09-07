Добавить правило  в iptables:
iptables -t nat -v -I PREROUTING -i INTERFACE -m set --match-set balscklist src -j DNAT --to-destination BAN_SERVER_ADDR

Где INTERFACE и BAN_SERVER_ADDR надо указать пользователю.
