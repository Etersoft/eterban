#!/usr/bin/python3
"""Simple HTTP API to check if an IP is banned in eterban."""

import http.server
import json
import subprocess
import ipaddress
import configparser
import hmac
import os
import sys
import threading
import time
from collections import defaultdict, deque

LISTEN_HOST = '127.0.0.1'
LISTEN_PORT = 8275

IPSET_V4 = 'eterban_1'
IPSET_V6 = 'eterban_1_ipv6'
IPSET_FIREHOL = 'firehol_level1'
IPSET_WHITE = 'eterban_white'
IPSET_WHITE_V6 = 'eterban_white_ipv6'

path_to_config = '/etc/eterban/settings.ini'
API_TOKEN = ''
API_RATE_LIMIT = 60
request_times = defaultdict(deque)
request_lock = threading.Lock()


def is_loopback_host(host):
    """Return True only for literal loopback addresses."""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def ipset_test(setname, ip):
    """Check an IP in an ipset.

    Returns True or False for a successful query and None if the set cannot be
    queried.  ``ipset test`` uses exit status 1 both for a missing set and an
    address which is not present, so verify that the set exists first.
    """
    try:
        listed = subprocess.run(
            ['ipset', 'list', setname],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5
        )
        if listed.returncode != 0:
            return None
        result = subprocess.run(
            ['ipset', 'test', setname, ip],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5
        )
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        return None
    except (OSError, subprocess.SubprocessError):
        return None


def check_ip(ip_str):
    """Check IP against all ban lists. Returns dict with results."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return {'error': 'invalid IP address'}

    if isinstance(addr, ipaddress.IPv6Address):
        checks = [('banned', IPSET_V6), ('whitelisted', IPSET_WHITE_V6)]
    else:
        checks = [
            ('banned', IPSET_V4),
            ('firehol', IPSET_FIREHOL),
            ('whitelisted', IPSET_WHITE),
        ]

    result = {'ip': ip_str, 'ipset': checks[0][1]}
    for field, setname in checks:
        value = ipset_test(setname, ip_str)
        if value is None:
            return {'error': 'ipset query failed'}
        result[field] = value

    return result


class EterbanAPIHandler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, status, result):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def _authorized(self):
        if not API_TOKEN:
            return True
        header = self.headers.get('Authorization', '')
        return header.startswith('Bearer ') and hmac.compare_digest(header[7:], API_TOKEN)

    def _rate_limited(self):
        now = time.monotonic()
        client = self.client_address[0]
        with request_lock:
            timestamps = request_times[client]
            while timestamps and timestamps[0] <= now - 60:
                timestamps.popleft()
            if len(timestamps) >= API_RATE_LIMIT:
                return True
            timestamps.append(now)
        return False

    def do_GET(self):
        if self._rate_limited():
            self._send_json(429, {'error': 'rate limit exceeded'})
            return
        if not self._authorized():
            self._send_json(401, {'error': 'authentication required'})
            return
        # /check/<ip>
        if self.path.startswith('/check/'):
            ip_str = self.path[len('/check/'):]
            result = check_ip(ip_str)
            status = 400 if result.get('error') == 'invalid IP address' else 503 if 'error' in result else 200
            self._send_json(status, result)
            return

        # /health
        if self.path == '/health':
            self._send_json(200, {'status': 'ok'})
            return

        self._send_json(404, {'error': 'not found', 'usage': '/check/<ip>'})

    def log_message(self, format, *args):
        sys.stderr.write('%s - %s\n' % (self.client_address[0], format % args))


def main():
    global API_TOKEN, API_RATE_LIMIT
    host = LISTEN_HOST
    port = LISTEN_PORT

    try:
        # Allow override from config
        if os.path.exists(path_to_config):
            config = configparser.ConfigParser()
            config.read(path_to_config)
            host = config.get('API', 'listen_host', fallback=LISTEN_HOST)
            port = config.getint('API', 'listen_port', fallback=LISTEN_PORT)
            API_TOKEN = config.get('API', 'api_token', fallback='').strip()
            API_RATE_LIMIT = config.getint('API', 'rate_limit_per_minute', fallback=60)

        if not is_loopback_host(host) and not API_TOKEN:
            raise ValueError('API token is required for a non-loopback listen_host')
        if API_RATE_LIMIT < 1:
            raise ValueError('API rate_limit_per_minute must be positive')
    except (ValueError, configparser.Error) as error:
        print('Invalid Eterban API configuration: ' + str(error), file=sys.stderr)
        raise SystemExit(78)

    server = http.server.HTTPServer((host, port), EterbanAPIHandler)
    print(f"Eterban API listening on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == '__main__':
    main()
