#!/usr/bin/python3
import redis
import subprocess
import time
import sys
import configparser
import os

def createConfig(path_to_config, path_to_log):
    """
    Create a config file
    """
    config = configparser.ConfigParser()
    config.add_section("Settings")
    config.set("Settings", "redis_server", "10.20.30.101")
    config.set("Settings", "hostname", "")
    
    with open(path_to_config, "w") as config_file:
        config.write(config_file)
    info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
    info +=" Created a config file (" + path_to_config + "). Update him!"
    with open(path_to_log, "a") as log_file:
        log_file.write(info)
    sys.exit()

def get_ip_redis_server (path_to_config, path_to_log):
    if not os.path.exists(path_to_config):
        createConfig (path_to_config, path_to_log)

    config = configparser.ConfigParser()
    config.read(path_to_config)

    # Читаем некоторые значения из конфиг. файла.
    
    redis_server = config.get("Settings", "redis_server", fallback = "No such things as redis_server")
    if redis_server == "No such things as redis_server":
        config.set("Settings", "redis_server", "10.20.30.101")
        with open(path_to_config, "w") as config_file:
            config_file.write(config)
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info +=" " + redis_server + ". Added to config file (" + path_to_config + ") redis_server. Update him!"
        with open(path_to_log, "a") as log_file:
            log_file.write(info)
        sys.exit()
    else:
        return (redis_server)

try:
    path_to_log = '/var/log/eterban/eterban.log'
    log = open (path_to_log, 'a')
except:
    try:
        path_to_log = '/var/log/eterban.log'
        log = open (path_to_log,'a')
    except:
        print ("Unknown error with logfile")
        sys.exit()


path_to_config = '/etc/eterban/settings.ini'
redis_server = get_ip_redis_server (path_to_config, path_to_log)



#print ("done!")
#print (time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime()))
#subprocess.call ('ipset create blacklist hash:ip', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)

r = redis.Redis(host=redis_server)
p = r.pubsub()

p.subscribe('ban', 'unban', 'by')

for message in p.listen():
    if message is not None and  message['type']=='message' and message['channel'] == b'ban':
        ip = message['data'].decode('utf-8')
        ip = message['data'].decode('utf-8')
        #ban = 'ipset -A blacklist ' + ip
        ban = 'fail2ban-client set blacklist  banip ' + ip
        #subprocess.call (ban, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        subprocess.call (ban, shell = True)
        tcp_drop = 'conntrack -D -s ' + ip
        subprocess.Popen(tcp_drop, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.Popen(tcp_drop, shell = True)
    elif message is not None and message['type'] =='message' and message['channel'] == b'unban' :
        #print (message)
        ip = message['data'].decode('utf-8')
        #unban = 'ipset -D blacklist ' + ip
        unban = 'fail2ban-client set blacklist unbanip ' + ip
        subprocess.call (unban, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.call (unban, shell = True)
        tcp_drop = 'conntrack -D -s ' + ip
        subprocess.Popen(tcp_drop, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.Popen(tcp_drop, shell = True)
    elif message is not None and message['type'] =='message' and message['channel'] == b'by':
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info += " " + message['data'].decode('utf-8') + "\n"
        #print (info)
        log.write(info)
        log.flush()
    elif message is not None:
        #print ("AHTUNG!!1!", message)
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info += " Unknown message: " + str(message) + "\n"
        #print (info)
        log.write(info)
        log.flush()
    else:
        pass
