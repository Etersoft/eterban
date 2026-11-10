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

Забаненные внешние клиенты перенаправляются на публичную страницу
`ban_server:81` (IPv6 — `ban_server_ipv6`). Внутренние клиенты (интерфейс
`internal_interface`), обращающиеся по 80/443 к забаненным адресам,
перенаправляются на внутреннюю страницу `ban_server_internal:82`
(IPv6 — `ban_server_internal_ipv6`). Если `ban_server_internal` не задан,
используется `ban_server`, если не задан `ban_server_internal_ipv6` —
`ban_server_ipv6`. IPv6-правила создаются, только если задан `ban_server_ipv6`.


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

### Шлюз и отдельный веб-узел

Публичную страницу блокировки (eterban-web: nginx, php-fpm, порт 81) можно
вынести со шлюза на отдельный узел. Внутренняя страница (сервис
eterban-internal из eterban-gateway, порт 82) остаётся на шлюзе: она узнаёт
адрес, к которому обращался клиент, через SO_ORIGINAL_DST, а это работает
только на узле, где выполняется DNAT.

```
внешний клиент --> шлюз: DNAT на ban_server:81 ----------> веб-узел: eterban-web
внутренний клиент --> шлюз: DNAT на ban_server_internal:82 --> шлюз: eterban-internal
веб-узел (unban.php) и шлюз (eterban-internal) --> Redis: XADD eterban:commands
```

settings.ini на шлюзе:

```
[Settings]
redis_server = <адрес Redis>
redis_username = switcher
redis_password = <пароль-шлюза>
ban_server = <адрес веб-узла>
ban_server_ipv6 = <IPv6 веб-узла>
ban_server_internal = <адрес шлюза для внутренних клиентов>
ban_server_internal_ipv6 = <IPv6 шлюза для внутренних клиентов>
internal_interface = <внутренний интерфейс>
i_interfaces = <WAN-интерфейсы>
```

На веб-узле ставится только eterban-web (с ним eterban-common), без
eterban-gateway. Странице разбана нужны только параметры Redis:

```
[Settings]
redis_server = <адрес Redis>
redis_username = web
redis_password = <пароль-веб-узла>
#redis_port = 6379
#redis_tls = false
#hostname = <имя для поля by, по умолчанию hostname узла>
```

Минимальный ACL веб-узла: unban.php только добавляет команду в поток
(AUTH и XADD), ban.php и страницы index.html, unban.html к Redis не
обращаются:

```
ACL SETUSER web on >пароль-веб-узла ~eterban:commands +xadd
```

Важно: unban.php разбанивает адрес клиента (`REMOTE_ADDR`), поэтому DNAT
на шлюзе должен доходить до веб-узла без SNAT, а ответы веб-узла забаненным
клиентам должны возвращаться через шлюз (маршрут к внешним сетям у
веб-узла — через шлюз), иначе обратная трансляция адреса не выполнится и
клиент не увидит страницу.

Порядок переноса:

1. Обновить шлюз до версии с `ban_server_internal`, задать
   `ban_server_internal` (и `ban_server_internal_ipv6`) — адрес шлюза,
   доступный внутренним клиентам; перезапустить `eterban` и
   `eterban-internal`. Проверка: `iptables -t nat -S PREROUTING | grep :82`,
   `ss -ltn | grep :82`.
2. Подготовить веб-узел: установить eterban-web, создать в Redis
   пользователя `web` (ACL выше), заполнить settings.ini, включить nginx и
   php-fpm версии по умолчанию (`systemctl enable --now nginx php<версия>-fpm`).
3. Проверить веб-узел по временному адресу: страница на порту 81 и разбан
   тестового адреса (в Redis появляется XADD в `eterban:commands`).
4. Перенести публичный адрес (`ban_server`, `ban_server_ipv6`) со шлюза на
   веб-узел и настроить маршрут ответов через шлюз; если адрес меняется —
   поменять `ban_server` на шлюзе и перезапустить `eterban`.
5. Убрать публичную страницу со шлюза: удалить eterban-web (права
   settings.ini вернутся к 0600 root:root) или отключить его конфиг nginx.
6. Проверка: забанить тестовый адрес (`eterban ban`), открыть с него любой
   сайт по 80 порту — страница блокировки с веб-узла, разбан с неё
   снимает бан (`eterban check`).

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

### Локальные файлы старых установок

На установках, настроенных до пакетирования страниц, могут остаться файлы
вне пакетов. Они перекрывают пакетные и должны быть удалены:

- конфиги nginx `notyeteterban.conf` (`listen 91.232.225.67:81`, страница
  «Вас пока не заблокировали») и `eterban.eterhost.ru.conf`. Пакетный
  `/etc/nginx/sites-enabled.d/eterban.conf` слушает `listen 81` на всех
  адресах, а nginx выбирает сервер с более точным адресом в `listen`,
  поэтому с 0.11 (внешние баны перенаправляются на порт 81) забаненные
  видят «не заблокировали». Удалить, затем `nginx -t && systemctl reload nginx`;
- `/var/www/html/eterban/int2.py` — теперь это пакетный
  `/usr/share/eterban/eterban_internal.py` (сервис eterban-internal);
- `/var/www/html/eterban/unban-cli.php`, `/var/www/html/eterban/unban-int.php`
  — ручные страницы разбана, не входят в пакет; разбан старым `PUBLISH`
  шлюз 0.11+ не слушает (пакетные unban.php и eterban-internal шлют XADD);
- `/etc/systemd/system/eterban-internal.service` — локальный юнит перекрывает
  пакетный `/lib/systemd/system/eterban-internal.service`. Удалить, затем
  `systemctl daemon-reload` и `systemctl restart eterban-internal`.

### PHP

eterban-web требует PHP версии по умолчанию ветки (`%php_defver`, в Sisyphus
— 8.5): пакеты `php8.5-fpm-fcgi`, `php8.5-redis`, `php8.5-openssl`, nginx
обращается к сокету `/var/run/php8.5-fpm/php8.5-fpm.sock`. После обновления
включите php-fpm этой версии (`systemctl enable --now php8.5-fpm`) и
отключите прежний, если он больше не нужен.

### fail2ban

`bantime` в jail — только локальная задержка fail2ban. Реальный срок бана
задаёт шлюз в секции [AutoUnban] своего settings.ini. Пример jail — в
разделе «Установка» выше.
