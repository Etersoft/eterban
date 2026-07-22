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
import queue
import logging
from autoban_manager import AutoBanManager

path_to_config      = '/etc/eterban/settings.ini'
ipset_eterban_1     = 'eterban_1'
ipset_eterban_1_ipv6     = 'eterban_1_ipv6'
ipset_firehol       = 'firehol_level1'
ipset_eterban_white = 'eterban_white'
ipset_eterban_white_ipv6 = 'eterban_white_ipv6'
redis_bans_key = 'eterban:active_bans'
redis_bans_initialized_key = 'eterban:active_bans:initialized'
redis_commands_stream = 'eterban:commands'
redis_commands_group = 'eterban-switcher'
redis_commands_consumer = socket.gethostname()
interface_name_re = re.compile(r'^[A-Za-z0-9_.:-]+$')

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

    try:
        ban_server = str(ipaddress.ip_address(ban_server))
        if ban_server_ipv6:
            ipv6_address = ipaddress.ip_address(ban_server_ipv6)
            if not isinstance(ipv6_address, ipaddress.IPv6Address):
                raise ValueError("ban_server_ipv6 is not IPv6")
            ban_server_ipv6 = str(ipv6_address)
        if not all(interface_name_re.fullmatch(interface) for interface in wan_ifaces):
            raise ValueError("invalid WAN interface name")
        if internal_interface and not interface_name_re.fullmatch(internal_interface):
            raise ValueError("invalid internal interface name")
        maxelem = config.getint("Settings", "maxelem", fallback=2000000)
        if maxelem < 1:
            raise ValueError("maxelem must be positive")
    except (ValueError, TypeError) as error:
        info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        info += " Problem in config file (" + path_to_config + "): " + str(error) + "\n"
        with open(path_to_log, "a") as log_file:
            log_file.write(info)
        sys.exit()

    if redis_server == "redis_server" or ban_server == "ban_server" or not wan_ifaces:
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info +=' ' + 'Problem in config file (' + path_to_config + '). Check him!'
        with open(path_to_log, "a") as log_file:
            log_file.write(info)
        sys.exit()
    else:
        return (redis_server, ban_server, ban_server_ipv6, wan_ifaces, internal_interface, maxelem, whitelist_file)


def redis_connection_options(config):
    options = {}
    username = config.get('Settings', 'redis_username', fallback='').strip()
    password = config.get('Settings', 'redis_password', fallback='')
    if username:
        options['username'] = username
    if password:
        options['password'] = password
    if config.getboolean('Settings', 'redis_tls', fallback=False):
        options['ssl'] = True
    return options

def restore_legacy_ipsets():
    """One-time migration fallback for snapshots made by older releases."""
    global ipset_eterban_1, ipset_eterban_1_ipv6, ipset_firehol
    name_list = [ipset_eterban_1, ipset_eterban_1_ipv6, ipset_firehol]
    for name in name_list:
        snapshot = '/usr/share/eterban/' + name
        if os.path.exists(snapshot):
            subprocess.run(['ipset', 'restore', '--file', snapshot], check=True, timeout=10)


def load_whitelist():
    global whitelist_file, ipset_eterban_white, ipset_eterban_white_ipv6, ban_server_ipv6, log
    if not whitelist_file or not os.path.exists(whitelist_file):
        return 0
    targets = [(ipset_eterban_white, 'inet')]
    if ban_server_ipv6:
        targets.append((ipset_eterban_white_ipv6, 'inet6'))
    temporary = {name: name + '_new' for name, family in targets}
    for name, family in targets:
        subprocess.call(['ipset', 'destroy', temporary[name]], stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
        command = ['ipset', 'create', temporary[name], 'hash:net']
        if family == 'inet6':
            command.extend(['family', 'inet6'])
        if subprocess.call(command) != 0:
            raise OSError('unable to create temporary whitelist set ' + temporary[name])
    loaded = 0
    skipped = 0
    try:
        with open(whitelist_file) as f:
            for raw in f:
                entry = raw.strip()
                if not entry or entry.startswith('#'):
                    continue
                try:
                    net = ipaddress.ip_network(entry, strict=False)
                except ValueError:
                    skipped += 1
                    continue
                name = ipset_eterban_white_ipv6 if isinstance(net, ipaddress.IPv6Network) else ipset_eterban_white
                if name not in temporary:
                    skipped += 1
                    continue
                if subprocess.call(['ipset', 'add', temporary[name], str(net), '-exist']) != 0:
                    raise OSError('unable to add whitelist entry ' + str(net))
                loaded += 1
        for name, family in targets:
            if subprocess.call(['ipset', 'swap', name, temporary[name]]) != 0:
                raise OSError('unable to activate whitelist set ' + name)
    finally:
        for name in temporary.values():
            subprocess.call(['ipset', 'destroy', name], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    info += " whitelist: loaded " + str(loaded) + " entries from " + whitelist_file
    if skipped:
        info += " (" + str(skipped) + " skipped)"
    info += "\n"
    log.write(info)
    log.flush()
    return loaded


def ensure_firewall_rule(command):
    """Insert a rule only when the exact rule is not already present."""
    check_command = command.copy()
    try:
        check_command[check_command.index('-I')] = '-C'
    except ValueError:
        return subprocess.call(command)
    if subprocess.call(check_command) != 0:
        return subprocess.call(command)
    return 0


def remove_firewall_rule(command):
    """Remove all duplicate copies of a rule during cleanup."""
    result = 0
    while subprocess.call(command) == 0:
        result = 0
    return result


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
    rc = subprocess.call(['ipset', 'test', setname, ip_str],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return rc == 0

def create_iptables_rules():
    global ban_server, ipset_eterban_1, ipset_firehol, ipset_eterban_white, wan_ifaces, internal_interface, maxelem
    # Create ipsets (once)
    commands=[['ipset', 'create', ipset_eterban_1, 'hash:ip', 'maxelem', str(maxelem)],
        ['ipset', 'create', ipset_firehol, 'hash:net'],
        ['ipset', 'create', ipset_eterban_white, 'hash:net']]
    for command in commands:
        subprocess.run(command + ['-exist'], check=True, timeout=10)

    # Per-WAN-interface rules
    for iface in wan_ifaces:
        commands=[
            ['iptables', '-t', 'nat', '-I', 'PREROUTING', '-i', iface, '-m', 'set', '--match-set', ipset_firehol, 'src', '-j', 'DNAT', '--to-destination', ban_server],
            ['iptables', '-t', 'nat', '-I', 'PREROUTING', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_1, 'src', '-j', 'DNAT', '--to-destination', ban_server],
            ['iptables', '-t', 'nat', '-I', 'PREROUTING', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_white, 'src', '-j', 'ACCEPT'],
            ['iptables', '-I', 'FORWARD', '-i', iface, '-p', 'tcp', '-m', 'multiport', '!', '--dport', '80,81,443', '-m', 'set', '--match-set', ipset_eterban_1, 'src', '-j', 'REJECT'],
            ['iptables', '-I', 'FORWARD', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_white, 'src', '-j', 'ACCEPT']]
        for command in commands:
            ensure_firewall_rule(command)

    # Internal interface: block outgoing connections to banned IPs (DNAT by destination)
    if internal_interface:
        commands=[
            ['iptables', '-t', 'nat', '-I', 'PREROUTING', '-i', internal_interface, '-m', 'set', '--match-set', ipset_eterban_1, 'dst', '-p', 'tcp', '-m', 'multiport', '--dports', '80,443', '-j', 'DNAT', '--to-destination', ban_server + ':82'],
            ['iptables', '-t', 'nat', '-I', 'PREROUTING', '-i', internal_interface, '-m', 'set', '--match-set', ipset_firehol, 'dst', '-p', 'tcp', '-m', 'multiport', '--dports', '80,443', '-j', 'DNAT', '--to-destination', ban_server + ':82']]
        for command in commands:
            ensure_firewall_rule(command)


def create_ip6tables_rules():
    global ban_server_ipv6, ipset_eterban_1_ipv6, ipset_eterban_white_ipv6, wan_ifaces, internal_interface, maxelem
    if not ban_server_ipv6:
        return
    # Create ipsets (once)
    commands=[['ipset', 'create', ipset_eterban_1_ipv6, 'hash:ip', 'family', 'inet6', 'maxelem', str(maxelem)],
        ['ipset', 'create', ipset_eterban_white_ipv6, 'hash:net', 'family', 'inet6']]
    for command in commands:
        subprocess.run(command + ['-exist'], check=True, timeout=10)

    # Per-WAN-interface rules
    for iface in wan_ifaces:
        commands=[
            ['ip6tables', '-t', 'nat', '-I', 'PREROUTING', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_1_ipv6, 'src', '-j', 'DNAT', '--to-destination', ban_server_ipv6],
            ['ip6tables', '-t', 'nat', '-I', 'PREROUTING', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_white_ipv6, 'src', '-j', 'ACCEPT'],
            ['ip6tables', '-I', 'FORWARD', '-i', iface, '-p', 'tcp', '-m', 'multiport', '!', '--dport', '80,443', '-m', 'set', '--match-set', ipset_eterban_1_ipv6, 'src', '-j', 'REJECT'],
            ['ip6tables', '-I', 'FORWARD', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_white_ipv6, 'src', '-j', 'ACCEPT']]
        for command in commands:
            ensure_firewall_rule(command)

    # Internal interface: block outgoing connections to banned IPv6 IPs (DNAT by destination)
    if internal_interface:
        commands=[
            ['ip6tables', '-t', 'nat', '-I', 'PREROUTING', '-i', internal_interface, '-m', 'set', '--match-set', ipset_eterban_1_ipv6, 'dst', '-p', 'tcp', '-m', 'multiport', '--dports', '80,443', '-j', 'DNAT', '--to-destination', '[' + ban_server_ipv6 + ']:82']]
        for command in commands:
            ensure_firewall_rule(command)


def destroy_iptables_rules ():
    global ban_server, ipset_eterban_1, ipset_firehol, ipset_eterban_white, wan_ifaces, internal_interface
    # Per-WAN-interface rules
    for iface in wan_ifaces:
        commands=[
            ['iptables', '-t', 'nat', '-D', 'PREROUTING', '-i', iface, '-m', 'set', '--match-set', ipset_firehol, 'src', '-j', 'DNAT', '--to-destination', ban_server],
            ['iptables', '-t', 'nat', '-D', 'PREROUTING', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_1, 'src', '-j', 'DNAT', '--to-destination', ban_server],
            ['iptables', '-t', 'nat', '-D', 'PREROUTING', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_white, 'src', '-j', 'ACCEPT'],
            ['iptables', '-D', 'FORWARD', '-i', iface, '-p', 'tcp', '-m', 'multiport', '!', '--dport', '80,81,443', '-m', 'set', '--match-set', ipset_eterban_1, 'src', '-j', 'REJECT'],
            ['iptables', '-D', 'FORWARD', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_white, 'src', '-j', 'ACCEPT']]
        for command in commands:
            remove_firewall_rule(command)

    # Destroy ipsets
    for name in [ipset_eterban_1, ipset_firehol, ipset_eterban_white]:
        subprocess.call(['ipset', 'destroy', name])

    # Internal interface: remove outgoing block rules
    if internal_interface:
        commands=[
            ['iptables', '-t', 'nat', '-D', 'PREROUTING', '-i', internal_interface, '-m', 'set', '--match-set', ipset_eterban_1, 'dst', '-p', 'tcp', '-m', 'multiport', '--dports', '80,443', '-j', 'DNAT', '--to-destination', ban_server + ':82'],
            ['iptables', '-t', 'nat', '-D', 'PREROUTING', '-i', internal_interface, '-m', 'set', '--match-set', ipset_firehol, 'dst', '-p', 'tcp', '-m', 'multiport', '--dports', '80,443', '-j', 'DNAT', '--to-destination', ban_server + ':82']]
        for command in commands:
            remove_firewall_rule(command)


def destroy_ip6tables_rules ():
    global ban_server_ipv6, ipset_eterban_1_ipv6, ipset_eterban_white_ipv6, wan_ifaces, internal_interface
    if not ban_server_ipv6:
        return
    # Per-WAN-interface rules
    for iface in wan_ifaces:
        commands=[
            ['ip6tables', '-t', 'nat', '-D', 'PREROUTING', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_1_ipv6, 'src', '-j', 'DNAT', '--to-destination', ban_server_ipv6],
            ['ip6tables', '-t', 'nat', '-D', 'PREROUTING', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_white_ipv6, 'src', '-j', 'ACCEPT'],
            ['ip6tables', '-D', 'FORWARD', '-i', iface, '-p', 'tcp', '-m', 'multiport', '!', '--dport', '80,443', '-m', 'set', '--match-set', ipset_eterban_1_ipv6, 'src', '-j', 'REJECT'],
            ['ip6tables', '-D', 'FORWARD', '-i', iface, '-m', 'set', '--match-set', ipset_eterban_white_ipv6, 'src', '-j', 'ACCEPT']]
        for command in commands:
            remove_firewall_rule(command)

    # Destroy ipsets
    for name in [ipset_eterban_1_ipv6, ipset_eterban_white_ipv6]:
        subprocess.call(['ipset', 'destroy', name])

    if internal_interface:
        commands=[
            ['ip6tables', '-t', 'nat', '-D', 'PREROUTING', '-i', internal_interface, '-m', 'set', '--match-set', ipset_eterban_1_ipv6, 'dst', '-p', 'tcp', '-m', 'multiport', '--dports', '80,443', '-j', 'DNAT', '--to-destination', '[' + ban_server_ipv6 + ']:82']]
        for command in commands:
            remove_firewall_rule(command)


def exit_gracefully(signum, frame):

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
def log_redis_error(message):
    info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    info += " " + message + "\n"
    print(info, end='')
    log.write(info)
    log.flush()


def reload_whitelist(signum, frame):
    """Reload the configured whitelist without changing firewall topology."""
    try:
        loaded = load_whitelist()
        log_redis_error("Whitelist reloaded: " + str(loaded) + " entries")
    except (OSError, subprocess.SubprocessError) as error:
        log_redis_error("Unable to reload whitelist: " + str(error))


def configure_autoban_logging():
    autoban_log = logging.getLogger('autoban_manager')
    autoban_log.setLevel(logging.ERROR)
    autoban_log.propagate = False
    handler = logging.StreamHandler(log)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    autoban_log.addHandler(handler)


configure_autoban_logging()
signal.signal(signal.SIGHUP, reload_whitelist)


conntrack_queue = queue.Queue(maxsize=1024)
conntrack_pending = set()
conntrack_pending_lock = threading.Lock()


def conntrack_worker():
    while True:
        ip = conntrack_queue.get()
        try:
            subprocess.run(
                ['conntrack', '-D', '-s', ip],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.SubprocessError) as error:
            log_redis_error("conntrack cleanup failed for " + ip + ": " + str(error))
        finally:
            with conntrack_pending_lock:
                conntrack_pending.discard(ip)
            conntrack_queue.task_done()


def queue_conntrack_cleanup(ip):
    with conntrack_pending_lock:
        if ip in conntrack_pending:
            return
        conntrack_pending.add(ip)
    try:
        conntrack_queue.put_nowait(ip)
    except queue.Full:
        with conntrack_pending_lock:
            conntrack_pending.discard(ip)
        log_redis_error("conntrack cleanup queue full; skipped " + ip)


for _ in range(4):
    threading.Thread(target=conntrack_worker, daemon=True).start()


def get_ipset_members(setname):
    """Return valid address members from an ipset without parsing human output."""
    try:
        result = subprocess.run(
            ['ipset', 'save', setname], text=True, capture_output=True,
            check=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        log_redis_error("Unable to read " + setname + " for Redis migration: " + str(error))
        return []

    members = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[0] != 'add' or fields[1] != setname:
            continue
        try:
            members.append(str(ipaddress.ip_address(fields[2])))
        except ValueError:
            log_redis_error("Ignoring invalid legacy ipset entry: " + fields[2])
    return members


def initialize_ban_state():
    """Import the old ipset snapshot once, then make Redis authoritative."""
    try:
        if r.exists(redis_bans_initialized_key):
            return
        members = get_ipset_members(ipset_eterban_1)
        members.extend(get_ipset_members(ipset_eterban_1_ipv6))
        pipeline = r.pipeline()
        if members:
            pipeline.sadd(redis_bans_key, *members)
        pipeline.set(redis_bans_initialized_key, '1')
        pipeline.execute()
        log_redis_error("Initialized Redis ban state with " + str(len(members)) + " migrated entries")
    except redis.exceptions.RedisError as error:
        log_redis_error("Unable to initialize Redis ban state: " + str(error))


def restore_bans_from_redis():
    """Rebuild the local ban ipsets from the durable Redis set."""
    try:
        members = r.smembers(redis_bans_key)
    except redis.exceptions.RedisError as error:
        log_redis_error("Unable to read Redis ban state: " + str(error))
        return

    grouped = {ipset_eterban_1: [], ipset_eterban_1_ipv6: []}
    for member in members:
        ip = member.decode('utf-8') if isinstance(member, bytes) else member
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            log_redis_error("Ignoring invalid Redis ban state entry: " + str(ip))
            continue
        setname = ipset_eterban_1_ipv6 if isinstance(address, ipaddress.IPv6Address) else ipset_eterban_1
        grouped[setname].append(str(address))

    for setname, addresses in grouped.items():
        try:
            subprocess.run(['ipset', 'flush', setname], check=True, timeout=10)
            for ip in addresses:
                subprocess.run(['ipset', 'add', setname, ip, '-exist'], check=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as error:
            log_redis_error("Unable to restore " + setname + " from Redis: " + str(error))
            continue
    log_redis_error("Restored " + str(sum(len(addresses) for addresses in grouped.values())) + " ban entries from Redis")


def persist_ban(ip):
    try:
        r.sadd(redis_bans_key, ip)
        return True
    except redis.exceptions.RedisError as error:
        log_redis_error("Unable to persist ban " + ip + " in Redis: " + str(error))
        return False


def remove_persisted_ban(ip):
    try:
        r.srem(redis_bans_key, ip)
        return True
    except redis.exceptions.RedisError as error:
        log_redis_error("Unable to remove ban " + ip + " from Redis: " + str(error))
        return False


def connect_redis():
    """Connect to Redis and create the durable command consumer group."""
    while True:
        try:
            redis_client = redis.Redis(
                host=redis_server,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
                **redis_options,
            )
            redis_client.ping()
            try:
                redis_client.xgroup_create(redis_commands_stream, redis_commands_group,
                                           id='0', mkstream=True)
            except redis.exceptions.ResponseError as error:
                if 'BUSYGROUP' not in str(error):
                    raise
            log_redis_error("Connected to Redis Stream " + redis_commands_stream)
            return redis_client
        except (redis.exceptions.RedisError, OSError) as error:
            log_redis_error("Unable to connect to Redis: " + str(error) + "; retrying in 5 seconds")
            time.sleep(5)


config = configparser.ConfigParser()
config.read(path_to_config)
redis_options = redis_connection_options(config)
r = connect_redis()

# Инициализация AutoBanManager
auto_mgr = AutoBanManager(r, config)


def apply_unban(ip):
    """Remove one ban locally and update Redis only after ipset succeeds."""
    try:
        network = ipaddress.ip_network(ip, strict=False)
    except ValueError:
        log_redis_error("Not parsed as IP, skipped " + str(ip))
        return False

    setname = ipset_eterban_1_ipv6 if isinstance(network, ipaddress.IPv6Network) else ipset_eterban_1
    command = ['ipset', 'del', setname, ip, '-exist']
    try:
        subprocess.run(command, check=True, timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError) as error:
        log_redis_error("Unable to remove ban from ipset: " + ip + "; " + str(error))
        return False

    if not remove_persisted_ban(ip):
        return False

    queue_conntrack_cleanup(ip)
    if auto_mgr.enabled:
        auto_mgr.on_unban(ip)
    return True


def auto_unban_checker():
    """Фоновый поток для проверки и выполнения авто-разбанов."""
    while True:
        time.sleep(auto_mgr.check_interval)
        if not auto_mgr.enabled:
            continue

        try:
            expired = auto_mgr.get_expired_bans()
            for ip in expired:
                if apply_unban(ip):
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

# Older releases also kept the FireHOL set in this snapshot.  The manual ban
# sets are flushed below and rebuilt from Redis, so the snapshot is only a
# migration source for them.
try:
    restore_legacy_ipsets()
    create_iptables_rules()
    create_ip6tables_rules()
except (OSError, subprocess.SubprocessError) as error:
    log_redis_error("Unable to initialize firewall state: " + str(error))
    sys.exit(1)
initialize_ban_state()
restore_bans_from_redis()
load_whitelist()


def process_message_inner(message):
    if message is not None and  message['type']=='message' and message['channel'] == b'ban':
        ip = message['data'].decode('utf-8')
        ipo = ipaddress.ip_address(ip)
        if is_whitelisted(ip):
            info = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            info += " " + ip + " skipped: matched whitelist\n"
            print(info)
            log.write(info)
            log.flush()
            return True
        if isinstance(ipo, ipaddress.IPv6Address):
            ban = ['ipset', '-A', ipset_eterban_1_ipv6, ip]
        else:
            ban = ['ipset', '-A', ipset_eterban_1, ip]
        print (ban)
        print (message)
        if subprocess.call(ban) != 0:
            log_redis_error("Unable to add ban to ipset: " + ip)
            return False
        if not persist_ban(ip):
            return False
        queue_conntrack_cleanup(ip)
        return True

    elif message is not None and message['type'] =='message' and message['channel'] == b'unban' :
        print (message)
        ip = message['data'].decode('utf-8')
        return apply_unban(ip)
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
        return True
    elif message is not None:
        print ("AHTUNG!!1!", message)
        info = time.strftime( "%Y-%m-%d %H:%M:%S", time.localtime())
        info += " Unknown message: " + str(message) + "\n"
        print (info)
        log.write(info)
        log.flush()
        return True
    else:
        return True


def process_message(message):
    """Handle malformed Pub/Sub payloads without losing the subscription."""
    try:
        return process_message_inner(message)
    except (KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
        log_redis_error("Invalid Redis message skipped: " + str(error) + "; payload=" + repr(message)[:200])
        return True


def process_stream_entry(fields):
    """Adapt a durable Stream command to the established command handlers."""
    command = fields.get(b'command', b'')
    ip = fields.get(b'ip', b'')
    message = {'type': 'message', 'channel': command, 'data': ip}
    success = process_message(message)
    by_message = fields.get(b'by')
    if by_message:
        success = process_message({'type': 'message', 'channel': b'by', 'data': by_message}) and success
    return success


while True:
    try:
        claimed = r.xautoclaim(redis_commands_stream, redis_commands_group,
                               redis_commands_consumer, min_idle_time=60000,
                               start_id='0-0', count=10)
        entries = [(redis_commands_stream, claimed[1])] if claimed[1] else []
        if not entries:
            pending = r.xreadgroup(redis_commands_group, redis_commands_consumer,
                                   {redis_commands_stream: '0'}, count=10)
            entries = pending or r.xreadgroup(redis_commands_group, redis_commands_consumer,
                                              {redis_commands_stream: '>'}, count=10, block=5000)
        for stream, messages in entries:
            for message_id, fields in messages:
                if process_stream_entry(fields):
                    r.xack(stream, redis_commands_group, message_id)
    except (redis.exceptions.RedisError, OSError) as error:
        log_redis_error("Redis Stream read failed: " + str(error) + "; reconnecting")
        r = connect_redis()
        auto_mgr.r = r
