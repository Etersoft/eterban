#!/usr/bin/python3
import redis
import subprocess
import time
import sys
import configparser
import os
import signal




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

def restore_ipset_eterban_1():
    command='ipset restore --file /usr/share/eterban/eterban_1'
    subprocess.call (command, shell = True)

def create_iptables_rules():
    commands=["ipset --create eterban_1 iphash",
        'iptables -t nat -I PREROUTING -i brlocal -m set --match-set eterban_1 src -j DNAT --to-destination 91.232.225.67',
        'iptables -t nat -I PREROUTING -i brlocal -m set ! --match-set eterban_1 src -d 91.232.225.67 -p tcp -m multiport --destination-port 80,443 -j DNAT --to-destination 91.232.225.67:81',
        'iptables -I FORWARD -i brlocal -p tcp -m multiport ! --dport 80,81,443 -m set --match-set eterban_1 src -j REJECT']
    for command in commands:
        subprocess.call (command, shell = True)

def destroy_iptables_rules ():
    commands=['iptables -t nat -D PREROUTING -i brlocal -m set --match-set eterban_1 src -j DNAT --to-destination 91.232.225.67',
        'iptables -t nat -D PREROUTING -i brlocal -m set ! --match-set eterban_1 src -d 91.232.225.67 -p tcp -m multiport --destination-port 80,443 -j DNAT --to-destination 91.232.225.67:81',
        'iptables -D FORWARD -i brlocal -p tcp -m multiport ! --dport 80,81,443 -m set --match-set eterban_1 src -j REJECT',
        'ipset destroy eterban_1']

    for command in commands:
        subprocess.call (command, shell = True)
        #print (command)

def exit_gracefully(signum, frame):
    destroy_iptables_rules()
    print ("End of the program. I was killed with ", signum,'\n')
    sys.exit()

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGQUIT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)


path_to_config = '/etc/eterban/settings.ini'
redis_server = get_ip_redis_server (path_to_config, path_to_log)

print ("done!")
#print (time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime()))
#subprocess.call ('ipset create blacklist hash:ip', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)

try:
    r = redis.Redis(host=redis_server)
    p = r.pubsub()

    p.subscribe('ban', 'unban', 'by')
except:
    print ("Enable to connect redes")
    sys.exit()

restore_ipset_eterban_1()
create_iptables_rules()


for message in p.listen():
    if message is not None and  message['type']=='message' and message['channel'] == b'ban':
        ip = message['data'].decode('utf-8')
        ip = message['data'].decode('utf-8')
        ban = 'ipset -A eterban_1 ' + ip
        print (message)
        #ban = 'fail2ban-client set blacklist  banip ' + ip
        #subprocess.call (ban, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        subprocess.call (ban, shell = True)
        tcp_drop = 'conntrack -D -s ' + ip
        subprocess.Popen(tcp_drop, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.Popen(tcp_drop, shell = True)
    elif message is not None and message['type'] =='message' and message['channel'] == b'unban' :
        print (message)
        ip = message['data'].decode('utf-8')
        unban = 'ipset -D eterban_1 ' + ip
        #unban = 'fail2ban-client set blacklist unbanip ' + ip
        subprocess.call (unban, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.call (unban, shell = True)
        tcp_drop = 'conntrack -D -s ' + ip
        subprocess.Popen(tcp_drop, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.Popen(tcp_drop, shell = True)
    elif message is not None and message['type'] =='message' and message['channel'] == b'by':
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info += " " + message['data'].decode('utf-8') + "\n"
        print (info)
        log.write(info)
        log.flush()
    elif message is not None:
        print ("AHTUNG!!1!", message)
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info += " Unknown message: " + str(message) + "\n"
        print (info)
        log.write(info)
        log.flush()
    else:
        pass
