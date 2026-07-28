# Production deployment — 2026-07-28

## Scope

The `eterban` production installation on the physical router `priv` was
updated to `0.11-alt3`.

The update contains the Redis Stream reconnection work, reliable public and
internal ban-page routing, packaging fixes, and service hardening introduced
in the preceding commits.

Relevant commits:

- `c6a35f5` — route public ban redirects to port 81;
- `7f2a9fb` — require TCP for public DNAT rules;
- `d92ef7e` and `eeb66fc` — fix Redis Stream reconnect and RESP3 handling;
- `685dcba` — do not restore legacy ipset snapshots over active sets;
- `3a4c9b2` — release `0.11-alt3`.

## Safety measures

- The configuration was backed up before updating:
  `/etc/eterban/settings.ini.pre-0.11-alt2-20260728012450`.
- RPMs were copied to `/var/tmp/` and their SHA-256 checksums were compared
  before installation.
- The whole set of mutually versioned packages was installed together:
  `eterban-common`, `eterban-gateway`, `eterban-web`, and
  `eterban-fail2ban`.

## Important incident during deployment

The first `0.11-alt2` start exposed a legacy migration defect: snapshots in
`/usr/share/eterban/` attempted to recreate ipsets which were already active
and referenced by firewall rules. The switcher consequently failed to start.

This was fixed in `0.11-alt3`: a legacy snapshot is restored only when the
corresponding ipset does not exist. No live ipsets or Redis ban data were
deleted. After the corrected package was installed, the switcher restored the
active bans from Redis normally.

## Resulting state

- Installed packages: all four `eterban` subpackages are `0.11-alt3`.
- `/etc/eterban/settings.ini`: mode `0640`, owner `root:_webserver`.
- `eterban.service`, `eterban-internal.service`, `nginx`, and `redis` are
  active.
- `eterban-api.service` remains inactive because it was inactive before the
  deployment; it was intentionally not enabled as part of this update.
- Redis Stream consumer group `eterban-switcher` has zero pending messages
  and zero lag.
- The switcher restored 3327 active bans from Redis after the final restart.
- Public DNAT rules on all configured WAN interfaces use TCP and redirect to
  `91.232.225.67:81`.

## Functional checks

- The public ban page on port 81 responded with the public self-unban text.
- The internal ban page on port 82 responded with the distinct `You accessed:`
  message.
- A live blocked address, `41.60.23.246`, was verified consistently in all
  three authoritative views:
  - `/usr/bin/eterban check` reported it as banned;
  - `ipset test eterban_1` confirmed membership;
  - Redis `SISMEMBER eterban:active_bans` returned `1`.

## Follow-up

Keep the RPM files in `/var/tmp/` on `priv` until the next maintenance window
so that the installed production artifacts remain available for inspection.
