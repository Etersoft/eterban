#!/usr/bin/python3
"""Simple HTTP API to check if an IP is banned in eterban."""

import http.server
import json
import subprocess
import ipaddress
import configparser
import os
import sys

LISTEN_HOST = '127.0.0.1'
LISTEN_PORT = 8275

IPSET_V4 = 'eterban_1'
IPSET_V6 = 'eterban_1_ipv6'
IPSET_FIREHOL = 'firehol_level1'
IPSET_WHITE = 'eterban_white'

path_to_config = '/etc/eterban/settings.ini'


def ipset_test(setname, ip):
    """Check if IP is in ipset. Returns True if found."""
    result = subprocess.run(
        ['ipset', 'test', setname, ip],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return result.returncode == 0


def check_ip(ip_str):
    """Check IP against all ban lists. Returns dict with results."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return {'error': 'invalid IP address'}

    if isinstance(addr, ipaddress.IPv6Address):
        banned = ipset_test(IPSET_V6, ip_str)
        ipset_name = IPSET_V6
    else:
        banned = ipset_test(IPSET_V4, ip_str)
        ipset_name = IPSET_V4

    result = {
        'ip': ip_str,
        'banned': banned,
        'ipset': ipset_name,
    }

    # Check firehol (IPv4 only, it's hash:net)
    if isinstance(addr, ipaddress.IPv4Address):
        result['firehol'] = ipset_test(IPSET_FIREHOL, ip_str)

    # Check whitelist
    if isinstance(addr, ipaddress.IPv4Address):
        result['whitelisted'] = ipset_test(IPSET_WHITE, ip_str)

    return result


class EterbanAPIHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # /check/<ip>
        if self.path.startswith('/check/'):
            ip_str = self.path[len('/check/'):]
            result = check_ip(ip_str)
            status = 400 if 'error' in result else 200
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            return

        # /health
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
            return

        self.send_response(404)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': 'not found', 'usage': '/check/<ip>'}).encode())

    def log_message(self, format, *args):
        pass  # suppress default logging


def main():
    host = LISTEN_HOST
    port = LISTEN_PORT

    # Allow override from config
    if os.path.exists(path_to_config):
        config = configparser.ConfigParser()
        config.read(path_to_config)
        host = config.get('API', 'listen_host', fallback=LISTEN_HOST)
        port = config.getint('API', 'listen_port', fallback=LISTEN_PORT)

    server = http.server.HTTPServer((host, port), EterbanAPIHandler)
    print(f"Eterban API listening on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == '__main__':
    main()
