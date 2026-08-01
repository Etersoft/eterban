#!/usr/bin/python3
"""Drop FireHOL netset entries covered by the live whitelist.

firehol_level1 intentionally carries bogon/RFC1918 ranges (useful on WAN to
reject spoofed sources).  When those ranges are also whitelisted internally,
they would otherwise let our own IPs appear inside the ban set imported by
get_firehol_ip.sh.  This filter reads the active eterban_white ipset and drops
any imported network that lies entirely inside a whitelisted network, so the
imported data stays clean.

The iptables whitelist-ACCEPT rule created by create_iptables_rules() is the
final enforcement and does not depend on this filter; it only keeps the
imported data tidy.  If the whitelist ipset is missing or unreadable the
netset is passed through unchanged so the import is not blocked.
"""
import ipaddress
import subprocess
import sys

WHITELIST_SET = 'eterban_white'


def load_whitelist_networks(setname=WHITELIST_SET):
    """Return whitelist networks from the live ipset, or () on any failure."""
    try:
        result = subprocess.run(
            ['ipset', 'save', setname],
            text=True, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ()
    if result.returncode != 0:
        return ()
    networks = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] == 'add' and fields[1] == setname:
            try:
                networks.append(ipaddress.ip_network(fields[2], strict=False))
            except ValueError:
                continue
    return tuple(networks)


def covered_by(network, whitelist_networks):
    """True if network is equal to or nested inside a whitelisted network."""
    for white in whitelist_networks:
        if network.version == white.version and network.subnet_of(white):
            return True
    return False


def filter_netset(lines, whitelist_networks, setname):
    """Map netset lines to 'add SETNAME CIDR' lines, dropping covered networks.

    Returns (add_lines, dropped_count).  Blank lines, comments and anything
    that is not a valid CIDR are silently ignored (same as the old sed filter).
    """
    dropped = 0
    out = []
    for raw in lines:
        entry = raw.strip()
        if not entry or entry.startswith('#'):
            continue
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        if covered_by(network, whitelist_networks):
            dropped += 1
            continue
        out.append('add ' + setname + ' ' + str(network))
    return out, dropped


def main(argv):
    setname = argv[1] if len(argv) > 1 else 'firehol_tmp'
    whitelist_networks = load_whitelist_networks()
    out, dropped = filter_netset(sys.stdin, whitelist_networks, setname)
    for line in out:
        print(line)
    if dropped:
        sys.stderr.write(
            'filter_firehol: dropped {} entries covered by {}\n'.format(
                dropped, WHITELIST_SET))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
