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


if len(sys.argv) > 1:
    ip=sys.argv[1]
else:
    ip=""

if not ip:
    print("Run with IP arg")
    sys.exit()

try:
    r = redis.Redis (host=redis_server)
    r.publish ('unban', ip)
    message = ip + " was unblocked by admin on " + hostname
    r.publish ('by', message)
except:
    print("Error with connect to redis " + redis_server)
