#!/usr/bin/python3
import redis
import sys
import configparser
import os
import socket

def createConfig(path_to_config):
    """
    Create a config file
    """
    config = configparser.ConfigParser()
    config.add_section("Settings")
    config.set("Settings", "redis_server", "10.20.30.101")
    config.set("Settings", "hostname", socket.gethostname())
    
    with open(path_to_config, "w") as config_file:
        config.write(config_file)
    sys.exit()

def get_ip_redis_server (path_to_config):
    if not os.path.exists(path_to_config):
        createConfig (path_to_config)

    config = configparser.ConfigParser()
    config.read(path_to_config)

    # Читаем некоторые значения из конфиг. файла.
    
    redis_server = config.get("Settings", "redis_server", fallback = "No such things as redis_server")
    hostname = config.get("Settings", "hostname", fallback = socket.gethostname())
    if redis_server == "No such things as redis_server":
        config.set("Settings", "redis_server", "10.20.30.101")
        with open(path_to_config, "a") as config_file:
            config_file.write(config)
        sys.exit()
    else:
        return (redis_server, hostname)

path_to_config = '/etc/eterban/settings.ini'
redis_server, hostname = get_ip_redis_server (path_to_config)

r = redis.Redis (host=redis_server)
r.publish ('ban', sys.argv[1])
try:
    message = sys.argv[1] + " was blocked by " + hostname + ": " + sys.argv[2]
except:
    message = sys.argv[1] + " was blocked by " + hostname + " (set block: [name=NAME_OF_RULE] on " + hostname + ":/etc/fail2ban/jail.conf)"

r.publish ('by', message)