#!/usr/bin/python3
"""
CLI для команд автоматической разблокировки eterban.

Команды:
    info <ip>   - показать информацию о бане и историю
    reset <ip>  - сбросить счётчик нарушений
    pending     - показать запланированные авто-разбаны
    permanent   - показать постоянные баны
"""

import sys
import time
import configparser
import redis

# Пути
CONFIG_PATH = '/etc/eterban/settings.ini'

# Ключи Redis
META_PREFIX = 'eterban:meta:'
SCHEDULE_KEY = 'eterban:unban_schedule'
PERMANENT_KEY = 'eterban:permanent'


def format_duration(seconds):
    """Форматировать длительность в человекочитаемый вид."""
    if seconds <= 0:
        return "permanent"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_time(timestamp):
    """Форматировать Unix timestamp."""
    if timestamp <= 0:
        return "permanent"
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))


def get_redis():
    """Получить подключение к Redis."""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    redis_server = config.get('Settings', 'redis_server', fallback='localhost')
    return redis.Redis(host=redis_server)


def cmd_info(ip):
    """Показать информацию о бане IP."""
    r = get_redis()
    meta = r.hgetall(f"{META_PREFIX}{ip}")

    if not meta:
        print(f"No ban history for {ip}")
        return

    # Декодируем значения
    data = {k.decode(): v.decode() for k, v in meta.items()}

    offense_count = int(data.get('offense_count', 0))
    ban_time = int(data.get('ban_time', 0))
    unban_time = int(data.get('unban_time', 0))
    last_offense = int(data.get('last_offense', 0))
    source = data.get('source', 'unknown')
    reason = data.get('reason', 'unknown')

    # Рассчитываем длительность
    if unban_time > 0:
        duration = unban_time - ban_time
        status = "temporary"
        remaining = unban_time - int(time.time())
        if remaining < 0:
            remaining_str = "expired (waiting for unban)"
        else:
            remaining_str = format_duration(remaining)
    else:
        duration = 0
        status = "permanent"
        remaining_str = "permanent"

    # Проверяем, в каком списке
    is_scheduled = r.zscore(SCHEDULE_KEY, ip) is not None
    is_permanent = r.sismember(PERMANENT_KEY, ip)

    print(f"Ban info for {ip}:")
    print(f"  Offense count:  {offense_count}")
    print(f"  Status:         {status}")
    print(f"  Ban duration:   {format_duration(duration)}")
    print(f"  Remaining:      {remaining_str}")
    print(f"  Ban time:       {format_time(ban_time)}")
    print(f"  Unban time:     {format_time(unban_time)}")
    print(f"  Last offense:   {format_time(last_offense)}")
    print(f"  Source:         {source}")
    print(f"  Reason:         {reason}")
    print(f"  In schedule:    {'yes' if is_scheduled else 'no'}")
    print(f"  In permanent:   {'yes' if is_permanent else 'no'}")


def cmd_reset(ip):
    """Сбросить счётчик нарушений для IP."""
    r = get_redis()
    meta_key = f"{META_PREFIX}{ip}"

    if not r.exists(meta_key):
        print(f"No ban history for {ip}")
        return

    r.delete(meta_key)
    print(f"Reset offense counter for {ip}; active ban state is unchanged")


def cmd_pending():
    """Показать запланированные авто-разбаны."""
    r = get_redis()
    pending = r.zrangebyscore(SCHEDULE_KEY, 0, '+inf', withscores=True)

    if not pending:
        print("No pending auto-unbans")
        return

    now = int(time.time())
    print(f"Pending auto-unbans ({len(pending)} total):")
    print()

    for ip, unban_time in pending:
        ip = ip.decode() if isinstance(ip, bytes) else ip
        unban_time = int(unban_time)
        remaining = unban_time - now

        if remaining < 0:
            remaining_str = "EXPIRED"
        else:
            remaining_str = format_duration(remaining)

        print(f"  {ip:20s}  unban at {format_time(unban_time)}  ({remaining_str})")


def cmd_permanent():
    """Показать постоянные баны."""
    r = get_redis()
    members = r.smembers(PERMANENT_KEY)

    if not members:
        print("No permanent bans")
        return

    print(f"Permanent bans ({len(members)} total):")
    print()

    for ip in sorted(members):
        ip = ip.decode() if isinstance(ip, bytes) else ip
        # Получаем дополнительную информацию
        meta = r.hgetall(f"{META_PREFIX}{ip}")
        if meta:
            data = {k.decode(): v.decode() for k, v in meta.items()}
            offense_count = data.get('offense_count', '?')
            source = data.get('source', 'unknown')
            print(f"  {ip:20s}  offenses: {offense_count}  source: {source}")
        else:
            print(f"  {ip}")


def usage():
    print("""Usage: autoban_cli.py <command> [args]

Commands:
    info <ip>   - show ban info and history for IP
    reset <ip>  - reset offense counter for IP
    pending     - list pending auto-unbans
    permanent   - list permanent bans
""")
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        usage()

    cmd = sys.argv[1]

    if cmd == 'info':
        if len(sys.argv) < 3:
            print("Error: IP address required")
            sys.exit(1)
        cmd_info(sys.argv[2])

    elif cmd == 'reset':
        if len(sys.argv) < 3:
            print("Error: IP address required")
            sys.exit(1)
        cmd_reset(sys.argv[2])

    elif cmd == 'pending':
        cmd_pending()

    elif cmd == 'permanent':
        cmd_permanent()

    else:
        print(f"Unknown command: {cmd}")
        usage()


if __name__ == '__main__':
    main()
