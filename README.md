Eterban - система централизованного блокирования ip-адресов для автономной системы.

Средствами fail2ban на целевых машинах выбираются нежелательные ip-адреса. Эти адреса высылаются на единый сервер блокировки через занесение в redis.
Шлюз принимает эти адреса, вносит в ipset eterban_1 и силами iptables перенаправляет обращения по 80 и 443 порту на бан-сервер.

Конфигурационный файл:
/etc/eterban/settings.ini

В котором указывается 
```
redis_server = 192.168.0.0
ban_server = 192.168.0.1
```
Так же можно определить
```
hostname = myserver
```
Иначе будет использоваться hostname машины.


## Установка:

### eterban-fail2ban

На серверы, имеющие доступ к интернету, устанавливается пакет eterban-fail2ban. В настройках fail2ban: /etc/fail2ban/jail.d/ssh.conf

Например:
```
[ssh-eterban]
enabled  = true
filter   = sshd
action   = eterban[name=SSH]
logpath = %(sshd_log)s
backend = %(sshd_backend)s
maxretry = 3
findtime = 1200
# This is only Fail2Ban's local cooldown. The gateway [AutoUnban] policy
# determines the actual centralized ban duration.
bantime  = 1
```

Важно: в графе action выставлять значение eterban. Желательно в name указывать причину блокировки.

### eterban-gateway

На шлюз, где будет выполняться централизованная блокировка ip-трафика, устанвливается пакет eterban-gateway.
Работает как сервис:
```
/etc/systemd/system/eterban.service 
```

### eterban-web

На сервер для заблокированных (бан-сервер) устанвливается eterban-web.

Страница блокировки находится в /var/www/html/eterban

## Обновление с предыдущих версий

### 0.10 и старше → 0.11 и новее: несовместимость протокола

До 0.10 включительно клиенты публиковали баны в Redis Pub/Sub (`PUBLISH ban`).
С 0.11 клиенты (`ban.py` из eterban-common, его вызывает eterban-fail2ban) и
шлюз (eterban-gateway) обмениваются командами через Redis Stream
`eterban:commands` (XADD/XREADGROUP), канал `ban` шлюз больше не слушает.

Поэтому клиенты и шлюз нужно обновлять согласованно: клиент 0.10 со шлюзом
0.11+ не работает, причём ошибок не выдаёт — его баны молча теряются.

Порядок обновления:

1. Сначала шлюз (все подпакеты одной версии одной транзакцией:
   eterban-common, eterban-gateway и, если установлены, eterban-web и
   eterban-fail2ban).
2. Затем все клиенты (eterban-common и eterban-fail2ban).

Проверка после обновления каждого клиента (тестовый адрес — из
документационных диапазонов, например 192.0.2.10):

```
# на клиенте
/usr/bin/python3 /usr/share/eterban/ban.py 192.0.2.10 upgrade-test
# на шлюзе
eterban check 192.0.2.10
eterban info 192.0.2.10
eterban unban 192.0.2.10
eterban reset 192.0.2.10
```

### Шлюз

Перед обновлением сохраните копию настроек:

```
cp -a /etc/eterban/settings.ini /etc/eterban/settings.ini.pre-update-$(date +%Y%m%d%H%M%S)
```

Активные баны с 0.11 хранятся в Redis, в множестве `eterban:active_bans`;
при старте шлюз восстанавливает из него ipset-ы. При первом запуске 0.11+
старый снимок ipset из /usr/share/eterban восстанавливается, только если
такого набора ещё нет, а содержимое набора однократно переносится в
`eterban:active_bans`. Не восстанавливайте старые снимки вручную поверх
работающих наборов.

После обновления:

```
systemctl status eterban
redis-cli -h <redis_server> XINFO GROUPS eterban:commands
eterban count
```

В выводе `XINFO GROUPS` должна быть группа `eterban-switcher`, при пустой
очереди — с `pending` и `lag`, равными 0.
Если в Redis включена авторизация, добавьте к redis-cli
`--user switcher --askpass`.

### Права на /etc/eterban/settings.ini

Файл может содержать пароль Redis. Скрипты пакетов выставляют права сами:
на узле с eterban-web (страница разбана читает настройки) — 0640
root:_webserver, на остальных узлах, в том числе на клиентах, — 0600
root:root. Не делайте файл доступным на чтение всем.

### Авторизация в Redis

Параметры подключения задаются в секции [Settings]:

```
redis_username = client
redis_password = <пароль>
redis_tls = false
```

Рекомендуемая схема Redis ACL:

```
ACL SETUSER default off
ACL SETUSER switcher on >пароль-шлюза ~eterban:* +@all
ACL SETUSER client on >пароль-клиентов ~eterban:commands +xadd
```

Пользователь `switcher` — для шлюза (сервис eterban, команда eterban,
страницы разбана), `client` может только добавлять команды в
`eterban:commands` и предназначен для клиентов с eterban-fail2ban.

Внимание: если включить пароль (выключить `default`) на Redis раньше, чем
все клиенты обновлены и получили redis_username/redis_password, клиенты
перестанут банить.

### fail2ban

`bantime` в jail — только локальная задержка fail2ban. Реальный срок бана
задаёт шлюз в секции [AutoUnban] своего settings.ini. Пример jail — в
разделе «Установка» выше.
