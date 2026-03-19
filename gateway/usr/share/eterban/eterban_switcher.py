#!/usr/bin/python3
import redis
import subprocess
import time
import sys
import configparser
import os
import signal
import socket
import ipaddress
import threading
import re
from autoban_manager import AutoBanManager

path_to_config      = '/etc/eterban/settings.ini'
path_to_eterban     = '/usr/share/eterban/'
ipset_eterban_1     = 'eterban_1'
ipset_eterban_1_ipv6     = 'eterban_1_ipv6'
ipset_firehol       = 'firehol_level1'
ipset_eterban_white = 'eterban_white'

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


def parse_config (path_to_config, path_to_log):
    if not os.path.exists(path_to_config):
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info +=' ' + 'Problem in config file (' + path_to_config + '). Check him!'
        with open(path_to_log, "a") as log_file:
            log_file.write(info)
        sys.exit()

    config = configparser.ConfigParser()
    config.read(path_to_config)

    # Читаем некоторые значения из конфиг. файла.
    
    redis_server = config.get("Settings", "redis_server", fallback = "redis_server")
    ban_server = config.get("Settings", "ban_server", fallback = "ban_server")
    ban_server_ipv6 = config.get("Settings", "ban_server_ipv6", fallback = "")
    i_interface = config.get("Settings", "i_interface", fallback = "i_interface")
    i_interface2 = config.get("Settings", "i_interface2", fallback = "")
    internal_interface = config.get("Settings", "internal_interface", fallback = "")
    if redis_server == "redis_server" or ban_server == "ban_server" or i_interface == "i_interface":
        #config.set("Settings", "redis_server", "10.20.30.101")
        #with open(path_to_config, "w") as config_file:
        #    config_file.write(config)
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info +=' ' + 'Problem in config file (' + path_to_config + '). Check him!'
        with open(path_to_log, "a") as log_file:
            log_file.write(info)
        sys.exit()
    else:
        maxelem = config.getint("Settings", "maxelem", fallback=2000000)
        return (redis_server, ban_server, ban_server_ipv6, i_interface, i_interface2, internal_interface, maxelem)

def save_ipset_eterban_1():
    global ipset_eterban_1, ipset_eterban_1_ipv6, ipset_firehol, ipset_eterban_white, path_to_eterban
    name_list = [ipset_eterban_1, ipset_eterban_1_ipv6, ipset_firehol, ipset_eterban_white]
    for name in name_list:
        command = 'ipset save ' + name + ' --file ' + path_to_eterban + name
        subprocess.call (command, shell = True)

def restore_ipset_eterban_1():
    global ipset_eterban_1, ipset_eterban_1_ipv6, ipset_firehol, ipset_eterban_white, path_to_eterban
    name_list = [ipset_eterban_1, ipset_eterban_1_ipv6, ipset_firehol, ipset_eterban_white]
    for name in name_list:
        command='ipset restore --file ' + path_to_eterban + name
        subprocess.call (command, shell = True)

def create_iptables_rules():
    global ban_server, ipset_eterban_1, ipset_firehol, ipset_eterban_white, i_interface, i_interface2, internal_interface, maxelem
    commands=['ipset create ' + ipset_eterban_1 + ' hash:ip maxelem ' + str(maxelem),
        'ipset create ' + ipset_firehol + ' hash:net',
        'ipset create ' + ipset_eterban_white + ' hash:ip',
        'iptables -t nat -I PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_firehol + ' src -j DNAT --to-destination ' + ban_server,
        'iptables -t nat -I PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_1 + ' src -j DNAT --to-destination ' + ban_server,
        'iptables -t nat -I PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_white + ' src -j ACCEPT',
        #'iptables -t nat -I PREROUTING -i ' + i_interface + ' -m set ! --match-set ' + ipset_eterban_1 + ' src -d ' + ban_server + ' -p tcp -m multiport --destination-port 80,443 -j DNAT --to-destination ' + ban_server + ':81',
        #'iptables -t nat -I PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_1 + ' src  -p tcp --dport 443 -j DNAT --to-destination ' + ban_server + ':80',
        'iptables -I FORWARD -i ' + i_interface + ' -p tcp -m multiport ! --dport 80,81,443 -m set --match-set ' + ipset_eterban_1 + ' src -j REJECT']
    for command in commands:
        subprocess.call (command, shell = True)

    if i_interface2:
        commands=[
            'iptables -t nat -I PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_firehol + ' src -j DNAT --to-destination ' + ban_server,
            'iptables -t nat -I PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_eterban_1 + ' src -j DNAT --to-destination ' + ban_server,
            'iptables -t nat -I PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_eterban_white + ' src -j ACCEPT',
            'iptables -I FORWARD -i ' + i_interface2 + ' -p tcp -m multiport ! --dport 80,81,443 -m set --match-set ' + ipset_eterban_1 + ' src -j REJECT']
        for command in commands:
            subprocess.call (command, shell = True)

    # Internal interface: block outgoing connections to banned IPs (DNAT by destination)
    if internal_interface:
        commands=[
            'iptables -t nat -I PREROUTING -i ' + internal_interface + ' -m set --match-set ' + ipset_eterban_1 + ' dst -p tcp -m multiport --dports 80,443 -j DNAT --to-destination ' + ban_server + ':82',
            'iptables -t nat -I PREROUTING -i ' + internal_interface + ' -m set --match-set ' + ipset_firehol + ' dst -p tcp -m multiport --dports 80,443 -j DNAT --to-destination ' + ban_server + ':82']
        for command in commands:
            subprocess.call (command, shell = True)


def create_ip6tables_rules():
    global ban_server_ipv6, ipset_eterban_1_ipv6, i_interface, i_interface2, maxelem
    if not ban_server_ipv6:
        return
    commands=['ipset create ' + ipset_eterban_1_ipv6 + ' hash:ip family inet6 maxelem ' + str(maxelem),
        #'ipset create ' + ipset_firehol + ' hash:net',
        #'ipset create ' + ipset_eterban_white + ' hash:ip',
        #'ip6tables -t nat -I PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_firehol + ' src -j DNAT --to-destination ' + ban_server,
        'ip6tables -t nat -I PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j DNAT --to-destination ' + ban_server_ipv6,
        #'ip6tables -t nat -I PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_white + ' src -j ACCEPT',
        #'iptables -t nat -I PREROUTING -i ' + i_interface + ' -m set ! --match-set ' + ipset_eterban_1 + ' src -d ' + ban_server + ' -p tcp -m multiport --destination-port 80,443 -j DNAT --to-destination ' + ban_server + ':81',
        #'iptables -t nat -I PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_1 + ' src  -p tcp --dport 443 -j DNAT --to-destination ' + ban_server + ':80',
        'ip6tables -I FORWARD -i ' + i_interface + ' -p tcp -m multiport ! --dport 80,443 -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j REJECT']
    for command in commands:
        subprocess.call (command, shell = True)

    if not i_interface2:
        return

    commands=[
        #'iptables -t nat -I PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_firehol + ' src -j DNAT --to-destination ' + ban_server,
        'ip6tables -t nat -I PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j DNAT --to-destination ' + ban_server,
        #'iptables -t nat -I PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_eterban_white + ' src -j ACCEPT',
        #'iptables -t nat -I PREROUTING -i ' + i_interface2 + ' -m set ! --match-set ' + ipset_eterban_1 + ' src -d ' + ban_server + ' -p tcp -m multiport --destination-port 80,443 -j DNAT --to-destination ' + ban_server + ':81',
        #'iptables -t nat -I PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_eterban_1 + ' src  -p tcp --dport 443 -j DNAT --to-destination ' + ban_server + ':80',
        'ip6tables -I FORWARD -i ' + i_interface2 + ' -p tcp -m multiport ! --dport 80,443 -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j REJECT']
    for command in commands:
        subprocess.call (command, shell = True)


def destroy_iptables_rules ():
    global ban_server, ipset_eterban_1, ipset_firehol, ipset_eterban_white, i_interface, i_interface2, internal_interface
    commands=[
        'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_firehol + ' src -j DNAT --to-destination ' + ban_server,
        'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_1 + ' src -j DNAT --to-destination ' + ban_server,
        'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_white + ' src -j ACCEPT',
        #'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set ! --match-set ' + ipset_eterban_1 + ' src -d ' + ban_server + ' -p tcp -m multiport --destination-port 80,443 -j DNAT --to-destination ' + ban_server + ':81',
        #'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_1 + ' src -p tcp --dport 443 -j DNAT --to-destination ' + ban_server + ':80',
        'iptables -D FORWARD -i ' + i_interface + ' -p tcp -m multiport ! --dport 80,81,443 -m set --match-set ' + ipset_eterban_1 + ' src -j REJECT',
        'ipset destroy ' + ipset_eterban_1,
        'ipset destroy ' + ipset_firehol,
        'ipset destroy ' + ipset_eterban_white]
    for command in commands:
        subprocess.call (command, shell = True)
        #print (command)

    if i_interface2:
        commands=[
            'iptables -t nat -D PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_firehol + ' src -j DNAT --to-destination ' + ban_server,
            'iptables -t nat -D PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_eterban_1 + ' src -j DNAT --to-destination ' + ban_server,
            'iptables -t nat -D PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_eterban_white + ' src -j ACCEPT',
            'iptables -D FORWARD -i ' + i_interface2 + ' -p tcp -m multiport ! --dport 80,81,443 -m set --match-set ' + ipset_eterban_1 + ' src -j REJECT']
        for command in commands:
            subprocess.call (command, shell = True)

    # Internal interface: remove outgoing block rules
    if internal_interface:
        commands=[
            'iptables -t nat -D PREROUTING -i ' + internal_interface + ' -m set --match-set ' + ipset_eterban_1 + ' dst -p tcp -m multiport --dports 80,443 -j DNAT --to-destination ' + ban_server + ':82',
            'iptables -t nat -D PREROUTING -i ' + internal_interface + ' -m set --match-set ' + ipset_firehol + ' dst -p tcp -m multiport --dports 80,443 -j DNAT --to-destination ' + ban_server + ':82']
        for command in commands:
            subprocess.call (command, shell = True)


def destroy_ip6tables_rules ():
    global ban_server_ipv6, ipset_eterban_1_ipv6, i_interface, i_interface2
    if not ban_server_ipv6:
        return
    commands=[
        #'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_firehol + ' src -j DNAT --to-destination ' + ban_server,
        'ip6tables -t nat -D PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j DNAT --to-destination ' + ban_server_ipv6,
        #'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_white + ' src -j ACCEPT',
        #'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set ! --match-set ' + ipset_eterban_1 + ' src -d ' + ban_server + ' -p tcp -m multiport --destination-port 80,443 -j DNAT --to-destination ' + ban_server + ':81',
        #'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_1 + ' src -p tcp --dport 443 -j DNAT --to-destination ' + ban_server + ':80',
        'ip6tables -D FORWARD -i ' + i_interface + ' -p tcp -m multiport ! --dport 80,443 -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j REJECT',
        'ipset destroy ' + ipset_eterban_1_ipv6,
        #'ipset destroy ' + ipset_firehol,
        #'ipset destroy ' + ipset_eterban_white
        ]
    for command in commands:
        subprocess.call (command, shell = True)
        #print (command)

    if not i_interface2:
        return

    commands=[
        #'iptables -t nat -D PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_firehol + ' src -j DNAT --to-destination ' + ban_server,
        'ip6tables -t nat -D PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j DNAT --to-destination ' + ban_server_ipv6,
        #'iptables -t nat -D PREROUTING -i ' + i_interface2 + ' -m set --match-set ' + ipset_eterban_white + ' src -j ACCEPT',
        #'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set ! --match-set ' + ipset_eterban_1 + ' src -d ' + ban_server + ' -p tcp -m multiport --destination-port 80,443 -j DNAT --to-destination ' + ban_server + ':81',
        #'iptables -t nat -D PREROUTING -i ' + i_interface + ' -m set --match-set ' + ipset_eterban_1 + ' src -p tcp --dport 443 -j DNAT --to-destination ' + ban_server + ':80',
        'ip6tables -D FORWARD -i ' + i_interface2 + ' -p tcp -m multiport ! --dport 80,443 -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j REJECT']

    for command in commands:
        subprocess.call (command, shell = True)
        #print (command)


def exit_gracefully(signum, frame):

    save_ipset_eterban_1()
    destroy_iptables_rules()
    destroy_ip6tables_rules()

    print ("End of the program. I was killed with ", signum,'\n')
    sys.exit()

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGQUIT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)


#print ('1')
redis_server, ban_server, ban_server_ipv6, i_interface, i_interface2, internal_interface, maxelem = parse_config (path_to_config, path_to_log)

#destroy_iptables_rules ()
#sys.exit()
#print ("done!")
#print (time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime()))
#subprocess.call ('ipset create blacklist hash:ip', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)

try:
    r = redis.Redis(host=redis_server)
    p = r.pubsub()

    p.subscribe('ban', 'unban', 'by')
except:
    print ("Unable to connect redis")
    sys.exit(1)

# Инициализация AutoBanManager
config = configparser.ConfigParser()
config.read(path_to_config)
auto_mgr = AutoBanManager(r, config)

def auto_unban_checker():
    """Фоновый поток для проверки и выполнения авто-разбанов."""
    while True:
        time.sleep(auto_mgr.check_interval)
        if not auto_mgr.enabled:
            continue

        try:
            expired = auto_mgr.get_expired_bans()
            for ip in expired:
                # Публикуем разбан
                r.publish('unban', ip)
                r.publish('by', f"{ip} auto-unbanned after ban period expired")
                auto_mgr.remove_from_schedule(ip)
                info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                info += f" {ip} auto-unbanned\n"
                log.write(info)
                log.flush()
        except Exception as e:
            info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            info += f" auto_unban_checker error: {e}\n"
            log.write(info)
            log.flush()

# Запуск фонового потока
if auto_mgr.enabled:
    checker_thread = threading.Thread(target=auto_unban_checker, daemon=True)
    checker_thread.start()

restore_ipset_eterban_1()
create_iptables_rules()
create_ip6tables_rules()


for message in p.listen():
    if message is not None and  message['type']=='message' and message['channel'] == b'ban':
        ip = message['data'].decode('utf-8')
        ipo = ipaddress.ip_address(ip)
        if isinstance(ipo, ipaddress.IPv6Address):
            ban = 'ipset -A ' + ipset_eterban_1_ipv6 + ' ' + ip
        else:
            ban = 'ipset -A ' + ipset_eterban_1 + ' ' + ip
        #remove = 'ipset -D ' + ipset_eterban_white + ' ' + ip
        print (ban)
        print (message)
        subprocess.call (ban, shell = True)
        #subprocess.call (remove, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        tcp_drop = 'conntrack -D -s ' + ip
        subprocess.Popen(tcp_drop, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)

    elif message is not None and message['type'] =='message' and message['channel'] == b'unban' :
        print (message)
        ip = message['data'].decode('utf-8')
        ipo = ipaddress.ip_network(ip, strict=False)
        if isinstance(ipo, ipaddress.IPv6Address):
            unban = 'ipset -D ' + ipset_eterban_1_ipv6 + ' ' + ip
        elif isinstance(ipo, ipaddress.IPv4Network):
            unban = 'ipset -D ' + ipset_eterban_1 + ' ' + ip
        else:
            log.write("Not parsed as IP, skipped " + str(ip) + '\n')
        #add   = 'ipset -A ' + ipset_eterban_white + ' ' + ip
        subprocess.call (unban, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.call (add, shell = True)
        tcp_drop = 'conntrack -D -s ' + ip
        subprocess.Popen(tcp_drop, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)

        # AutoBan: обновляем метаданные (убираем из расписания)
        if auto_mgr.enabled:
            auto_mgr.on_unban(ip)
    elif message is not None and message['type'] =='message' and message['channel'] == b'by':
        by_msg = message['data'].decode('utf-8')
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info += " " + by_msg + "\n"
        print (info)
        log.write(info)
        log.flush()

        # AutoBan: парсим сообщение и сохраняем метаданные
        # Формат: "IP was blocked by HOSTNAME: REASON" или "IP was blocked by HOSTNAME (...)"
        if auto_mgr.enabled:
            match = re.match(r'^(\S+) was blocked by ([^:]+)(?:: (.+))?$', by_msg)
            if match:
                ip = match.group(1)
                source = match.group(2).strip()
                reason = match.group(3) if match.group(3) else 'auto'
                meta = auto_mgr.on_ban(ip, source=source, reason=reason)
                if meta:
                    ban_duration = meta.get('unban_time', 0) - int(time.time())
                    offense = meta.get('offense_count', 1)
                    if ban_duration > 0:
                        auto_info = f"  -> offense #{offense}, auto-unban in {auto_mgr.format_duration(ban_duration)}\n"
                    else:
                        auto_info = f"  -> offense #{offense}, PERMANENT ban\n"
                    print(auto_info)
                    log.write(auto_info)
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
