# Eterban on `priv`: administrator notes

This note is for the administrator of the physical router `priv.etersoft.ru`.
It describes the production `eterban` installation after the 2026-07-28
deployment.

## Current production baseline

- Installed release: `eterban 0.11-alt3`.
- Install all four subpackages at the same EVR:
  `eterban-common`, `eterban-gateway`, `eterban-web`, and
  `eterban-fail2ban`.
- Main configuration: `/etc/eterban/settings.ini`.
- Configuration permissions must be `0640 root:_webserver` while the web
  subpackage is installed. The file can contain Redis credentials; do not make
  it world-readable.
- Switcher unit: `eterban.service`.
- Internal page unit: `eterban-internal.service`.
- Public page: nginx vhost from `eterban-web`, TCP port 81.
- Internal diagnostic page: TCP port 82.
- Redis server for the current production configuration:
  `10.20.30.101`.

`eterban-api.service` was inactive before the 2026-07-28 deployment and was
left inactive. Do not enable it without deciding who needs the API and, for a
non-loopback listener, configuring an API token.

## Normal health checks

Run as an administrator with `sudo`:

```sh
systemctl is-active eterban.service eterban-internal.service nginx redis
ipset list -n | grep -E '^(eterban_1|eterban_white|firehol_level1)$'
redis-cli -h 10.20.30.101 XINFO GROUPS eterban:commands
```

Healthy Redis Stream output for group `eterban-switcher` has `pending` equal
to `0` and `lag` equal to `0` when no commands are waiting.

Inspect recent switcher events with:

```sh
journalctl -u eterban.service -n 100 --no-pager
tail -n 100 /var/log/eterban/eterban.log
```

Expected start messages include `Connected to Redis Stream`, `Restored ... ban
entries from Redis`, and `whitelist: loaded ... entries`.

## Checking one address

The supported public CLI remains unchanged:

```sh
/usr/bin/eterban check 203.0.113.10
```

For a deeper consistency check, compare the CLI, ipset and durable Redis set:

```sh
ip=203.0.113.10
/usr/bin/eterban check "$ip"
ipset test eterban_1 "$ip"
redis-cli -h 10.20.30.101 SISMEMBER eterban:active_bans "$ip"
```

For an actively banned IPv4 address, the last command must return `1`.

## Redirect topology

Do not merge the public and internal flows.

| Traffic | Firewall match | Redirect | Page behaviour |
| --- | --- | --- | --- |
| External client | banned **source** on a configured WAN interface | `ban_server:81` | public page and self-unban workflow |
| Internal client | banned **destination** on `internal_interface` | `ban_server:82` | diagnostic page with original destination |

All public DNAT rules must contain `-p tcp` and destination port `81`. Verify:

```sh
iptables -t nat -S PREROUTING | grep -- '--to-destination 91.232.225.67:81'
```

The internal and public pages can be checked locally without creating a ban:

```sh
curl --noproxy '*' --max-time 5 -fsS http://91.232.225.67:81/ | \
    grep -F 'Для разблокировки нажмите:'
curl --noproxy '*' --max-time 5 -fsS 'http://91.232.225.67:82/?ip=198.51.100.1' | \
    grep -F 'You accessed:'
```

## Redis restart and recovery

The switcher reconnects to Redis and restores active bans from
`eterban:active_bans`. After planned Redis maintenance, verify:

```sh
systemctl is-active eterban.service redis
redis-cli -h 10.20.30.101 XINFO GROUPS eterban:commands
tail -n 30 /var/log/eterban/eterban.log
```

Do not delete `eterban:active_bans` or `eterban:commands` during ordinary
maintenance. They are the durable source for current bans and queued commands.

## Updating the package

1. Build or obtain RPMs for exactly one common EVR.
2. Transfer all four RPMs to a temporary directory on `priv`.
3. Verify their checksums.
4. Back up `settings.ini`.
5. Install all four RPMs in one apt transaction.
6. Check services, Redis Stream, ipsets and both pages.

Example:

```sh
backup=/etc/eterban/settings.ini.pre-update-$(date +%Y%m%d%H%M%S)
cp -a /etc/eterban/settings.ini "$backup"

apt-get -y install /var/tmp/eterban-common-*.rpm \
    /var/tmp/eterban-gateway-*.rpm \
    /var/tmp/eterban-web-*.rpm \
    /var/tmp/eterban-fail2ban-*.rpm

systemctl reset-failed eterban.service
systemctl restart eterban.service
```

Do **not** update only `eterban-common` and `eterban-gateway`: `web` and
`fail2ban` require the same common EVR, so the package manager may remove them
to satisfy dependencies.

## ipset safety

Live ipsets are referenced by kernel firewall rules. Never destroy
`eterban_1`, `eterban_white`, or `firehol_level1` while the switcher is
running. Do not manually restore old snapshot files from `/usr/share/eterban/`
over live sets; current switcher code imports such a snapshot only when its
target set does not exist.

If the service is failed after an interrupted maintenance operation, collect
the journal first. A safe first recovery action is:

```sh
systemctl reset-failed eterban.service
systemctl restart eterban.service
systemctl --no-pager --full status eterban.service
```

Do not flush ipsets or delete Redis data as a first-line recovery step.

## Whitelist

Whitelist entries reside in `/etc/eterban/whitelist.txt`, one IPv4, IPv6, or
CIDR network per line. Reload after editing without changing firewall topology:

```sh
systemctl kill -s HUP eterban.service
```

Confirm the reload in `/var/log/eterban/eterban.log`.
