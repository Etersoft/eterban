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

## Implementation details

### Durable ban state and Redis reconnect

Earlier versions relied on a one-time Redis Pub/Sub subscription. A dropped
TCP connection or Redis restart could leave the process alive while it no
longer received ban or unban events.

The switcher now uses the Redis Stream `eterban:commands` and the durable
consumer group `eterban-switcher` instead of relying on a transient
subscription:

1. Producers write commands with `XADD`; an entry contains `command`, `ip`
   and, when available, `by`.
2. On startup the switcher creates the group with `MKSTREAM` if it does not
   exist and reads its own pending entries before waiting for new entries.
3. A command is acknowledged with `XACK` only after its handler completed
   successfully. This prevents a restart from silently discarding an
   unprocessed command.
4. Idle pending entries are reclaimed with `XAUTOCLAIM` at most once per
   minute. The previous per-iteration call was a busy-loop risk.
5. Redis connection failures are caught, logged, and followed by repeated
   reconnection attempts. The client uses a 5-second connect timeout, a
   10-second socket timeout, TCP keepalive and Redis health checks.
6. Redis-py 8 with RESP3 can represent an empty Stream response as
   `{stream: [[]]}`. The switcher normalizes both RESP2 and RESP3 replies
   before deciding whether entries exist; otherwise it would continuously
   read pending ID `0` and never request new messages with `>`.

Active ban addresses are additionally persisted in the Redis set
`eterban:active_bans`. At switcher start they are restored to temporary ipsets
and atomically swapped into place. This preserves bans over a service restart
and supports recovery after ipset state has been lost.

### Firewall and user-facing redirects

The two ban flows are deliberately separate:

| Flow | Match | Destination | User-facing page |
| --- | --- | --- | --- |
| External client | source address belongs to a ban ipset on a WAN interface | `ban_server:81` | public page with the self-unban flow |
| Internal client | destination address belongs to a ban ipset on `internal_interface` | `ban_server:82` | internal diagnostic page showing the original destination |

The public nginx vhost listens on port 81. The internal Python service listens
on port 82 and obtains the original destination from the socket metadata.

All external IPv4 and IPv6 DNAT rules now explicitly specify `-p tcp`.
Without this, iptables rejects a rule containing a destination port. The
corresponding removal rules use the same match fields, preventing stale rules.
The IPv4 and IPv6 `FORWARD` exceptions include port 81 so redirected public
HTTP traffic is not rejected after DNAT.

### ipset migration compatibility

Old releases can leave ipset snapshot files in `/usr/share/eterban/`. The
compatibility restore is now strictly conditional: a snapshot is imported only
when the corresponding ipset does not already exist. Production already had
live ipsets referenced by firewall rules, so attempting to recreate them made
`ipset restore` fail and caused the initial `alt2` switcher start to fail.

The `alt3` fix retains the live sets, rebuilds the current state from Redis,
and avoids removing kernel-referenced ipsets. This was verified in production
with 3327 restored ban entries.

### Service and package behaviour

- Systemd units use `Restart=always` plus baseline hardening:
  `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectHome=true`,
  `ProtectSystem=full`, and `UMask=0077`.
- The public CLI continues to be `/usr/bin/eterban`; installed Python scripts
  are invoked explicitly through `/usr/bin/python3`, so its interface did not
  change while installed source files can remain non-executable.
- The package owns `ban.py` in `eterban-common`, making it available to both
  the public CLI and the fail2ban action.
- `settings.ini` is a `%config(noreplace)` file. Post-install scripts set it
  to `root:_webserver` mode `0640` while the web package is installed, allowing
  PHP to read Redis connection settings without making them world-readable.
- `eterban-gateway` explicitly depends on `crontabs` and `logrotate`; the
  supplied logrotate configuration is owned by that subpackage.

### Automated and integration checks

`tests/static-checks.sh` now performs syntax checks for shipped Python, PHP
and shell files, validates the public CLI contract, and covers the packaging
and routing invariants. It includes targeted checks for:

- external port 81 versus internal port 82;
- TCP-qualified IPv4 and IPv6 DNAT rules;
- service hardening directives;
- invalid configuration exit behaviour;
- API failure reporting when ipset cannot be queried;
- Redis RESP3 empty Stream reply normalization.

The release was built with `rpmbsh -i` in hasher. On the isolated test VM,
Redis was restarted and a subsequent Stream ban command was verified in
`eterban_1`; the Stream consumer had zero pending messages and zero lag.

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
