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
ipset_eterban_white_ipv6 = 'eterban_white_ipv6'

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
    internal_interface = config.get("Settings", "internal_interface", fallback = "")
    whitelist_file = config.get("Settings", "whitelist_file", fallback = "/etc/eterban/whitelist.txt")

    # Build list of WAN interfaces: prefer i_interfaces, fallback to i_interface/i_interface2
    i_interfaces_raw = config.get("Settings", "i_interfaces", fallback = "")
    i_interface = config.get("Settings", "i_interface", fallback = "")
    i_interface2 = config.get("Settings", "i_interface2", fallback = "")

    if i_interfaces_raw:
        wan_ifaces = [x.strip() for x in i_interfaces_raw.replace(',', ' ').split() if x.strip()]
        if i_interface or i_interface2:
            info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            info += " WARNING: both i_interfaces and i_interface/i_interface2 set, using i_interfaces\n"
            with open(path_to_log, "a") as log_file:
                log_file.write(info)
    else:
        wan_ifaces = []
        if i_interface:
            wan_ifaces.append(i_interface)
        if i_interface2:
            wan_ifaces.append(i_interface2)

    if redis_server == "redis_server" or ban_server == "ban_server" or not wan_ifaces:
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info +=' ' + 'Problem in config file (' + path_to_config + '). Check him!'
        with open(path_to_log, "a") as log_file:
            log_file.write(info)
        sys.exit()
    else:
        maxelem = config.getint("Settings", "maxelem", fallback=2000000)
        return (redis_server, ban_server, ban_server_ipv6, wan_ifaces, internal_interface, maxelem, whitelist_file)

def save_ipset_eterban_1():
    global ipset_eterban_1, ipset_eterban_1_ipv6, ipset_firehol, path_to_eterban
    # whitelist is not saved: it is rebuilt from whitelist_file on startup
    name_list = [ipset_eterban_1, ipset_eterban_1_ipv6, ipset_firehol]
    for name in name_list:
        command = 'ipset save ' + name + ' --file ' + path_to_eterban + name
        subprocess.call (command, shell = True)

def restore_ipset_eterban_1():
    global ipset_eterban_1, ipset_eterban_1_ipv6, ipset_firehol, path_to_eterban
    name_list = [ipset_eterban_1, ipset_eterban_1_ipv6, ipset_firehol]
    for name in name_list:
        command='ipset restore --file ' + path_to_eterban + name
        subprocess.call (command, shell = True)


def load_whitelist():
    global whitelist_file, ipset_eterban_white, ipset_eterban_white_ipv6, ban_server_ipv6, log
    # Always flush first so the file is the single source of truth
    subprocess.call('ipset flush ' + ipset_eterban_white, shell = True)
    if ban_server_ipv6:
        subprocess.call('ipset flush ' + ipset_eterban_white_ipv6, shell = True)
    if not whitelist_file or not os.path.exists(whitelist_file):
        return 0
    loaded = 0
    skipped = 0
    with open(whitelist_file) as f:
        for raw in f:
            entry = raw.strip()
            if not entry or entry.startswith('#'):
                continue
            try:
                net = ipaddress.ip_network(entry, strict=False)
            except ValueError:
                info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                info += " whitelist: invalid entry '" + entry + "'\n"
                log.write(info)
                skipped += 1
                continue
            if isinstance(net, ipaddress.IPv6Network):
                if not ban_server_ipv6:
                    skipped += 1
                    continue
                cmd = 'ipset add ' + ipset_eterban_white_ipv6 + ' ' + str(net) + ' -exist'
            else:
                cmd = 'ipset add ' + ipset_eterban_white + ' ' + str(net) + ' -exist'
            if subprocess.call(cmd, shell = True) == 0:
                loaded += 1
            else:
                skipped += 1
    info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    info += " whitelist: loaded " + str(loaded) + " entries from " + whitelist_file
    if skipped:
        info += " (" + str(skipped) + " skipped)"
    info += "\n"
    log.write(info)
    log.flush()
    return loaded


def is_whitelisted(ip_str):
    """Return True if ip_str matches any entry in the whitelist ipset."""
    global ipset_eterban_white, ipset_eterban_white_ipv6, ban_server_ipv6
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        if not ban_server_ipv6:
            return False
        setname = ipset_eterban_white_ipv6
    else:
        setname = ipset_eterban_white
    rc = subprocess.call(
        'ipset test ' + setname + ' ' + ip_str,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell = True)
    return rc == 0

def create_iptables_rules():
    global ban_server, ipset_eterban_1, ipset_firehol, ipset_eterban_white, wan_ifaces, internal_interface, maxelem
    # Create ipsets (once)
    commands=['ipset create ' + ipset_eterban_1 + ' hash:ip maxelem ' + str(maxelem),
        'ipset create ' + ipset_firehol + ' hash:net',
        'ipset create ' + ipset_eterban_white + ' hash:net']
    for command in commands:
        subprocess.call (command, shell = True)

    # Per-WAN-interface rules
    for iface in wan_ifaces:
        commands=[
            'iptables -t nat -I PREROUTING -i ' + iface + ' -m set --match-set ' + ipset_firehol + ' src -j DNAT --to-destination ' + ban_server,
            'iptables -t nat -I PREROUTING -i ' + iface + ' -m set --match-set ' + ipset_eterban_1 + ' src -j DNAT --to-destination ' + ban_server,
            'iptables -t nat -I PREROUTING -i ' + iface + ' -m set --match-set ' + ipset_eterban_white + ' src -j ACCEPT',
            'iptables -I FORWARD -i ' + iface + ' -p tcp -m multiport ! --dport 80,81,443 -m set --match-set ' + ipset_eterban_1 + ' src -j REJECT']
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
    global ban_server_ipv6, ipset_eterban_1_ipv6, ipset_eterban_white_ipv6, wan_ifaces, internal_interface, maxelem
    if not ban_server_ipv6:
        return
    # Create ipsets (once)
    commands=['ipset create ' + ipset_eterban_1_ipv6 + ' hash:ip family inet6 maxelem ' + str(maxelem),
        'ipset create ' + ipset_eterban_white_ipv6 + ' hash:net family inet6']
    for command in commands:
        subprocess.call (command, shell = True)

    # Per-WAN-interface rules
    for iface in wan_ifaces:
        commands=[
            'ip6tables -t nat -I PREROUTING -i ' + iface + ' -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j DNAT --to-destination ' + ban_server_ipv6,
            'ip6tables -t nat -I PREROUTING -i ' + iface + ' -m set --match-set ' + ipset_eterban_white_ipv6 + ' src -j ACCEPT',
            'ip6tables -I FORWARD -i ' + iface + ' -p tcp -m multiport ! --dport 80,443 -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j REJECT']
        for command in commands:
            subprocess.call (command, shell = True)

    # Internal interface: block outgoing connections to banned IPv6 IPs (DNAT by destination)
    if internal_interface:
        commands=[
            'ip6tables -t nat -I PREROUTING -i ' + internal_interface + ' -m set --match-set ' + ipset_eterban_1_ipv6 + ' dst -p tcp -m multiport --dports 80,443 -j DNAT --to-destination [' + ban_server_ipv6 + ']:82']
        for command in commands:
            subprocess.call (command, shell = True)


def destroy_iptables_rules ():
    global ban_server, ipset_eterban_1, ipset_firehol, ipset_eterban_white, wan_ifaces, internal_interface
    # Per-WAN-interface rules
    for iface in wan_ifaces:
        commands=[
            'iptables -t nat -D PREROUTING -i ' + iface + ' -m set --match-set ' + ipset_firehol + ' src -j DNAT --to-destination ' + ban_server,
            'iptables -t nat -D PREROUTING -i ' + iface + ' -m set --match-set ' + ipset_eterban_1 + ' src -j DNAT --to-destination ' + ban_server,
            'iptables -t nat -D PREROUTING -i ' + iface + ' -m set --match-set ' + ipset_eterban_white + ' src -j ACCEPT',
            'iptables -D FORWARD -i ' + iface + ' -p tcp -m multiport ! --dport 80,81,443 -m set --match-set ' + ipset_eterban_1 + ' src -j REJECT']
        for command in commands:
            subprocess.call (command, shell = True)

    # Destroy ipsets
    for name in [ipset_eterban_1, ipset_firehol, ipset_eterban_white]:
        subprocess.call('ipset destroy ' + name, shell = True)

    # Internal interface: remove outgoing block rules
    if internal_interface:
        commands=[
            'iptables -t nat -D PREROUTING -i ' + internal_interface + ' -m set --match-set ' + ipset_eterban_1 + ' dst -p tcp -m multiport --dports 80,443 -j DNAT --to-destination ' + ban_server + ':82',
            'iptables -t nat -D PREROUTING -i ' + internal_interface + ' -m set --match-set ' + ipset_firehol + ' dst -p tcp -m multiport --dports 80,443 -j DNAT --to-destination ' + ban_server + ':82']
        for command in commands:
            subprocess.call (command, shell = True)


def destroy_ip6tables_rules ():
    global ban_server_ipv6, ipset_eterban_1_ipv6, ipset_eterban_white_ipv6, wan_ifaces, internal_interface
    if not ban_server_ipv6:
        return
    # Per-WAN-interface rules
    for iface in wan_ifaces:
        commands=[
            'ip6tables -t nat -D PREROUTING -i ' + iface + ' -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j DNAT --to-destination ' + ban_server_ipv6,
            'ip6tables -t nat -D PREROUTING -i ' + iface + ' -m set --match-set ' + ipset_eterban_white_ipv6 + ' src -j ACCEPT',
            'ip6tables -D FORWARD -i ' + iface + ' -p tcp -m multiport ! --dport 80,443 -m set --match-set ' + ipset_eterban_1_ipv6 + ' src -j REJECT']
        for command in commands:
            subprocess.call (command, shell = True)

    # Destroy ipsets
    for name in [ipset_eterban_1_ipv6, ipset_eterban_white_ipv6]:
        subprocess.call('ipset destroy ' + name, shell = True)

    if internal_interface:
        commands=[
            'ip6tables -t nat -D PREROUTING -i ' + internal_interface + ' -m set --match-set ' + ipset_eterban_1_ipv6 + ' dst -p tcp -m multiport --dports 80,443 -j DNAT --to-destination [' + ban_server_ipv6 + ']:82']
        for command in commands:
            subprocess.call (command, shell = True)


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
redis_server, ban_server, ban_server_ipv6, wan_ifaces, internal_interface, maxelem, whitelist_file = parse_config (path_to_config, path_to_log)

#destroy_iptables_rules ()
#sys.exit()
#print ("done!")
#print (time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime()))
#subprocess.call ('ipset create blacklist hash:ip', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)

def log_redis_error(message):
    info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    info += " " + message + "\n"
    print(info, end='')
    log.write(info)
    log.flush()


def connect_redis():
    """Connect to Redis and subscribe, retrying after a connection failure."""
    while True:
        try:
            redis_client = redis.Redis(
                host=redis_server,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
            redis_client.ping()
            pubsub = redis_client.pubsub()
            pubsub.subscribe('ban', 'unban', 'by')
            log_redis_error("Connected to Redis and subscribed to ban, unban, by")
            return redis_client, pubsub
        except (redis.exceptions.RedisError, OSError) as error:
            log_redis_error("Unable to connect to Redis: " + str(error) + "; retrying in 5 seconds")
            time.sleep(5)


r, p = connect_redis()

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
load_whitelist()


def process_message(message):
    if message is not None and  message['type']=='message' and message['channel'] == b'ban':
        ip = message['data'].decode('utf-8')
        ipo = ipaddress.ip_address(ip)
        if is_whitelisted(ip):
            info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            info += " " + ip + " skipped: matched whitelist\n"
            print(info)
            log.write(info)
            log.flush()
            return
        if isinstance(ipo, ipaddress.IPv6Address):
            ban = 'ipset -A ' + ipset_eterban_1_ipv6 + ' ' + ip
        else:
            ban = 'ipset -A ' + ipset_eterban_1 + ' ' + ip
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
                if is_whitelisted(ip):
                    # Whitelisted IPs are not actually banned, so no offense tracking
                    return
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


while True:
    try:
        for message in p.listen():
            process_message(message)
    except (redis.exceptions.RedisError, OSError) as error:
        log_redis_error("Redis subscription lost: " + str(error) + "; reconnecting")
        try:
            p.close()
        except (redis.exceptions.RedisError, OSError):
            pass
        r, p = connect_redis()
        auto_mgr.r = r
