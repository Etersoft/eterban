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
bantime  = 5
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
