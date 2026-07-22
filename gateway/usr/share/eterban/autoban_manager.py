#!/usr/bin/python3
"""
AutoBanManager - управление автоматической разблокировкой с экспоненциальным увеличением времени бана.

Логика:
- Первый бан: 1 час
- Второй бан: 4 часа (4^1)
- Третий бан: 16 часов (4^2)
- Четвёртый бан: 64 часа (4^3)
- Пятый+ бан: постоянный

Если IP чист 1 год - счётчик сбрасывается.
"""

import time
import logging

log = logging.getLogger(__name__)


class AutoBanManager:
    """Менеджер автоматической разблокировки с экспоненциальным backoff."""

    def __init__(self, redis_client, config):
        """
        Инициализация менеджера.

        Args:
            redis_client: Подключение к Redis
            config: ConfigParser с секцией [AutoUnban]
        """
        self.r = redis_client

        # Читаем конфигурацию с fallback значениями
        self.enabled = config.getboolean('AutoUnban', 'enabled', fallback=True)
        self.base_ban_seconds = config.getint('AutoUnban', 'base_ban_seconds', fallback=3600)
        self.backoff_multiplier = config.getint('AutoUnban', 'backoff_multiplier', fallback=4)
        self.max_offense_level = config.getint('AutoUnban', 'max_offense_level', fallback=4)
        self.reset_period_seconds = config.getint('AutoUnban', 'reset_period_days', fallback=365) * 86400
        self.check_interval = config.getint('AutoUnban', 'check_interval_seconds', fallback=60)

        # Ключи Redis
        self.META_PREFIX = 'eterban:meta:'
        self.SCHEDULE_KEY = 'eterban:unban_schedule'
        self.PERMANENT_KEY = 'eterban:permanent'

    def calculate_ban_duration(self, offense_count):
        """
        Рассчитать длительность бана.

        Args:
            offense_count: Номер нарушения (1, 2, 3, ...)

        Returns:
            Длительность в секундах, или 0 для постоянного бана
        """
        if offense_count > self.max_offense_level:
            return 0  # Permanent
        return self.base_ban_seconds * (self.backoff_multiplier ** (offense_count - 1))

    def on_ban(self, ip, source='unknown', reason='auto'):
        """
        Обработка нового бана.

        Args:
            ip: IP-адрес
            source: Источник бана (hostname сервера)
            reason: Причина бана (SSH, HTTP, etc.)

        Returns:
            dict с метаданными бана
        """
        if not self.enabled:
            return None

        try:
            meta_key = f"{self.META_PREFIX}{ip}"
            now = int(time.time())

            # Получаем существующие метаданные
            existing = self.r.hgetall(meta_key)
            is_permanent = self.r.sismember(self.PERMANENT_KEY, ip)

            if existing:
                offense_count = int(existing.get(b'offense_count', 0))
                last_offense = int(existing.get(b'last_offense', 0))

                # Проверяем, прошёл ли период сброса (1 год)
                if now - last_offense > self.reset_period_seconds:
                    offense_count = 0

                offense_count += 1
            else:
                # Permanent state is authoritative even if old metadata was
                # removed by a previous release's TTL or an admin reset.
                offense_count = self.max_offense_level + 1 if is_permanent else 1

            # Рассчитываем время бана
            ban_duration = self.calculate_ban_duration(offense_count)
            unban_time = now + ban_duration if ban_duration > 0 else 0

            # Сохраняем метаданные
            metadata = {
                'offense_count': offense_count,
                'ban_time': now,
                'unban_time': unban_time,
                'last_offense': now,
                'source': source,
                'reason': reason
            }
            pipeline = self.r.pipeline(transaction=True)
            pipeline.hset(meta_key, mapping=metadata)

            # Добавляем в расписание авто-разбана или в постоянные
            if unban_time > 0:
                # Temporary ban history can be reset after a clean period.
                pipeline.expire(meta_key, self.reset_period_seconds)
                pipeline.zadd(self.SCHEDULE_KEY, {ip: unban_time})
                pipeline.srem(self.PERMANENT_KEY, ip)  # На случай если был permanent
            else:
                # Permanent state must not disappear when temporary metadata
                # would otherwise reach its one-year TTL.
                pipeline.persist(meta_key)
                pipeline.sadd(self.PERMANENT_KEY, ip)
                pipeline.zrem(self.SCHEDULE_KEY, ip)  # Убираем из расписания
            pipeline.execute()

            return metadata

        except Exception as e:
            log.error(f"AutoBanManager.on_ban error: {e}")
            return None

    def on_unban(self, ip, reset_counter=False):
        """
        Обработка разблокировки.

        Args:
            ip: IP-адрес
            reset_counter: Сбросить счётчик нарушений
        """
        if not self.enabled:
            return

        try:
            # Удаляем из расписания и постоянных
            self.r.zrem(self.SCHEDULE_KEY, ip)
            self.r.srem(self.PERMANENT_KEY, ip)

            if reset_counter:
                self.r.delete(f"{self.META_PREFIX}{ip}")

        except Exception as e:
            log.error(f"AutoBanManager.on_unban error: {e}")

    def get_expired_bans(self):
        """
        Получить список IP с истёкшим временем бана.

        Returns:
            Список IP-адресов для разблокировки
        """
        if not self.enabled:
            return []

        try:
            now = int(time.time())
            expired = self.r.zrangebyscore(self.SCHEDULE_KEY, 0, now)
            return [ip.decode() if isinstance(ip, bytes) else ip for ip in expired]
        except Exception as e:
            log.error(f"AutoBanManager.get_expired_bans error: {e}")
            return []

    def remove_from_schedule(self, ip):
        """Удалить IP из расписания после авто-разбана."""
        try:
            self.r.zrem(self.SCHEDULE_KEY, ip)
        except Exception as e:
            log.error(f"AutoBanManager.remove_from_schedule error: {e}")

    def get_ban_info(self, ip):
        """
        Получить информацию о бане для CLI.

        Args:
            ip: IP-адрес

        Returns:
            dict с метаданными или None
        """
        try:
            meta = self.r.hgetall(f"{self.META_PREFIX}{ip}")
            if not meta:
                return None
            return {k.decode(): v.decode() for k, v in meta.items()}
        except Exception as e:
            log.error(f"AutoBanManager.get_ban_info error: {e}")
            return None

    def get_pending_unbans(self):
        """
        Получить список запланированных разбанов.

        Returns:
            Список кортежей (ip, unban_time)
        """
        try:
            pending = self.r.zrangebyscore(self.SCHEDULE_KEY, 0, '+inf', withscores=True)
            return [(ip.decode() if isinstance(ip, bytes) else ip, int(score))
                    for ip, score in pending]
        except Exception as e:
            log.error(f"AutoBanManager.get_pending_unbans error: {e}")
            return []

    def get_permanent_bans(self):
        """
        Получить список постоянных банов.

        Returns:
            Список IP-адресов
        """
        try:
            members = self.r.smembers(self.PERMANENT_KEY)
            return [ip.decode() if isinstance(ip, bytes) else ip for ip in members]
        except Exception as e:
            log.error(f"AutoBanManager.get_permanent_bans error: {e}")
            return []

    def reset_offense_counter(self, ip):
        """
        Сбросить историю нарушений, не меняя текущий ban.

        Args:
            ip: IP-адрес
        """
        try:
            self.r.delete(f"{self.META_PREFIX}{ip}")
        except Exception as e:
            log.error(f"AutoBanManager.reset_offense_counter error: {e}")

    def format_duration(self, seconds):
        """Форматировать длительность в человекочитаемый вид."""
        if seconds <= 0:
            return "permanent"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
