#!/usr/bin/python3

import redis
import sys
import configparser
import os
import socket

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

r = redis.Redis (host=redis_server)
r.publish ('ban', sys.argv[1])
try:
    message = sys.argv[1] + " was blocked by " + hostname + ": " + sys.argv[2]
except:
    message = sys.argv[1] + " was blocked by " + hostname + " (set block: [name=NAME_OF_RULE] on " + hostname + ":/etc/fail2ban/jail.conf)"

r.publish ('by', message)
