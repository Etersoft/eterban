#!/usr/bin/python3
"""Check the DNAT targets of eterban_switcher.py without touching the firewall.

parse_config and the create/destroy rule functions are extracted from the
switcher source and run with stubbed iptables/ipset calls.
"""
import ast
import configparser
import ipaddress
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

SOURCE = pathlib.Path(__file__).resolve().parent.parent / 'gateway/usr/share/eterban/eterban_switcher.py'
FUNCTIONS = {'parse_config', 'create_iptables_rules', 'create_ip6tables_rules',
             'destroy_iptables_rules', 'destroy_ip6tables_rules'}


def load_switcher(commands):
    tree = ast.parse(SOURCE.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    assert {n.name for n in nodes} == FUNCTIONS
    ns = {
        'os': os, 'sys': sys, 'time': time, 'configparser': configparser,
        'ipaddress': ipaddress, 'interface_name_re': re.compile(r'^[A-Za-z0-9_.:-]+$'),
        'ipset_eterban_1': 'eterban_1', 'ipset_eterban_1_ipv6': 'eterban_1_ipv6',
        'ipset_firehol': 'firehol_level1', 'ipset_eterban_white': 'eterban_white',
        'ipset_eterban_white_ipv6': 'eterban_white_ipv6', 'maxelem': 10,
        # rule helpers: record the commands, report every rule as absent once
        'subprocess': type('S', (), {'run': staticmethod(lambda *a, **k: None)}),
        'ensure_firewall_rule': lambda command: commands.append(command),
        'remove_firewall_rule': lambda command: commands.append(command),
        'run_command': lambda command, **k: 0,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), ns)
    return ns


def run(settings):
    commands = []
    ns = load_switcher(commands)
    with tempfile.TemporaryDirectory() as tmp:
        config = os.path.join(tmp, 'settings.ini')
        log = os.path.join(tmp, 'eterban.log')
        with open(config, 'w') as f:
            f.write('[Settings]\nredis_server = 127.0.0.1\ni_interfaces = wan0\n'
                    'internal_interface = lan0\n' + settings)
        (ns['redis_server'], ns['ban_server'], ns['ban_server_ipv6'],
         ns['ban_server_internal'], ns['ban_server_internal_ipv6'],
         ns['wan_ifaces'], ns['internal_interface'], ns['maxelem'],
         ns['whitelist_file']) = ns['parse_config'](config, log)
    for name in ('create_iptables_rules', 'create_ip6tables_rules',
                 'destroy_iptables_rules', 'destroy_ip6tables_rules'):
        ns[name]()
    return commands


def targets(commands, iface):
    """Set of (tool, action, DNAT target) for one input interface."""
    result = set()
    for c in commands:
        if 'DNAT' in c and c[c.index('-i') + 1] == iface:
            action = '-I' if '-I' in c else '-D'
            result.add((c[0], action, c[c.index('--to-destination') + 1]))
    return result


def expect(commands, iface, expected):
    got = targets(commands, iface)
    want = {(tool, action, target) for tool, target in expected for action in ('-I', '-D')}
    assert got == want, (iface, sorted(got), sorted(want))


# Compatibility: no ban_server_internal* -> internal clients go to ban_server:82.
c = run('ban_server = 192.0.2.81\nban_server_ipv6 = 2001:db8::81\n')
expect(c, 'wan0', {('iptables', '192.0.2.81:81'), ('ip6tables', '[2001:db8::81]:81')})
expect(c, 'lan0', {('iptables', '192.0.2.81:82'), ('ip6tables', '[2001:db8::81]:82')})

# Separate internal page on the gateway, public page elsewhere.
c = run('ban_server = 192.0.2.81\nban_server_ipv6 = 2001:db8::81\n'
        'ban_server_internal = 10.0.0.1\nban_server_internal_ipv6 = fd00::1\n')
expect(c, 'wan0', {('iptables', '192.0.2.81:81'), ('ip6tables', '[2001:db8::81]:81')})
expect(c, 'lan0', {('iptables', '10.0.0.1:82'), ('ip6tables', '[fd00::1]:82')})

# Whitelist exceptions for internal clients are kept, create and destroy.
for tool, ipset in (('iptables', 'eterban_white'), ('ip6tables', 'eterban_white_ipv6')):
    for action in ('-I', '-D'):
        assert [tool, '-t', 'nat', action, 'PREROUTING', '-i', 'lan0', '-m', 'set',
                '--match-set', ipset, 'dst', '-j', 'ACCEPT'] in c, (tool, action)

# IPv4-only gateway with a separate internal page.
c = run('ban_server = 192.0.2.81\nban_server_internal = 10.0.0.1\n')
expect(c, 'wan0', {('iptables', '192.0.2.81:81')})
expect(c, 'lan0', {('iptables', '10.0.0.1:82')})

# Wrong address families are configuration errors (exit 78).
for bad in ('ban_server_internal = fd00::1\n', 'ban_server_ipv6 = 2001:db8::81\nban_server_internal_ipv6 = 10.0.0.1\n',
            'ban_server_internal = not-an-ip\n'):
    try:
        run('ban_server = 192.0.2.81\n' + bad)
    except SystemExit as error:
        assert error.code == 78, error.code
    else:
        raise AssertionError('accepted invalid setting: ' + bad)
