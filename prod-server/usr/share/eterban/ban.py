#!/usr/bin/python3

import redis
import sys
import configparser
import os
import socket
import ipaddress


def get_ip_argument(argv):
    if len(argv) < 2:
        raise ValueError("Usage: ban.py <ip> [reason]")
    return str(ipaddress.ip_address(argv[1]))

def get_settings (path_to_config):
    if not os.path.exists(path_to_config):
        print("Missed config file")
        sys.exit()

    config = configparser.ConfigParser()
    config.read(path_to_config)

    # Читаем некоторые значения из конфиг. файла.
    redis_server = config.get("Settings", "redis_server", fallback = "localhost")
    hostname = config.get("Settings", "hostname", fallback = socket.gethostname())
    return (redis_server, hostname)

path_to_config = '/etc/eterban/settings.ini'
redis_server, hostname = get_settings (path_to_config)

try:
    ip = get_ip_argument(sys.argv)
except ValueError as error:
    print(error, file=sys.stderr)
    sys.exit(2)

reason = sys.argv[2] if len(sys.argv) > 2 else "(set block: [name=NAME_OF_RULE] on " + hostname + ":/etc/fail2ban/jail.conf)"
message = ip + " was blocked by " + hostname + ": " + reason

try:
    r = redis.Redis(host=redis_server, socket_connect_timeout=5, socket_timeout=5)
    r.xadd('eterban:commands', {'command': 'ban', 'ip': ip, 'by': message})
except redis.exceptions.RedisError as error:
    print("Unable to publish ban event: " + str(error), file=sys.stderr)
    sys.exit(1)
