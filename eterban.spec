Name: eterban
Version: 0.2
Release: eter1

Summary: Etersoft ban service

License: AGPLv3
Group: Development/Other
Url: http://wiki.etersoft.ru/eterban

Packager: Ruzal Gimazov <diff@etersoft.ru>

# Source-git: https://gitlab.eterfund.ru/diff/eterban.git
Source: %name-%version.tar

BuildArchitectures: noarch

# error: File must begin with "/": %webserver_htdocsdir/maintenance/
BuildRequires: rpm-macros-webserver-common

#Requires: python3 python3-module-redis-py

%description
Etersoft ban service.


%package gateway
Summary: Etersoft ban service: gateway
Group: Development/Other

%description gateway
Etersoft ban service.


%package web
Summary: Etersoft ban service: web
Group: Development/Other
Requires: php7-redis

%description web
Etersoft ban service.


%package fail2ban
Summary: Etersoft ban service: fail2ban
Group: Development/Other
Requires: redis
%description fail2ban
Etersoft ban service.

%prep
%setup

%install
#mkdir -p %buildroot%_sysconfdir/nginx/include/limits/
#install -m644 include/*.conf %buildroot/etc/nginx/include/
#install -m644 include/*.inc %buildroot%_sysconfdir/nginx/include/
#install -m644 include/limits/* %buildroot%_sysconfdir/nginx/include/limits/
mkdir -p %buildroot%_datadir/%name/
mkdir -p %buildroot/etc/%name/
mkdir -p %buildroot/etc/fail2ban/action.d/
mkdir -p %buildroot/etc/systemd/system/
mkdir -p %buildroot/var/log/eterban/
mkdir -p %buildroot%webserver_htdocsdir/%name/
mkdir -p %buildroot/etc/fail2ban/jail.d/

cp -a gateway/usr/share/%name/* %buildroot%_datadir/%name/
install -m 644 gateway/etc/eterban/* %buildroot/etc/%name/
install -m 644 gateway/etc/fail2ban/action.d/* %buildroot/etc/fail2ban/action.d/
install -m 644 gateway/etc/fail2ban/jail.d/* %buildroot/etc/fail2ban/jail.d/
install -m 644 gateway/etc/systemd/system/* %buildroot/etc/systemd/system/

install -m 644 ban-server/data/www/* %buildroot%webserver_htdocsdir/%name/

install -m 644 prod-server/etc/fail2ban/action.d/* %buildroot/etc/fail2ban/action.d/

cp -a prod-server/usr/share/%name/* %buildroot%_datadir/%name/

%files gateway
%config(noreplace) /etc/%name/settings.ini
%config(noreplace) /etc/fail2ban/action.d/ban.conf
%config(noreplace) /etc/fail2ban/jail.d/blacklist.conf
/etc/systemd/system/
/var/log/eterban/
%_datadir/%name/eterban_switcher.py

%files web
%webserver_htdocsdir/%name/

%files fail2ban
%config(noreplace) /etc/%name/settings.ini
%_datadir/%name/ban.py
%config(noreplace) /etc/fail2ban/action.d/eterban.conf

%changelog
* Sun Nov 10 2019 Ruzal Gimazov <diff@etersoft.ru> 0.2-eter1
- remove eterban.service on the prod-server
- create rule on prod-serv in jail.d
- add configparser, 2 functions with it, changed config name to settings.ini, created logfile
- added configparser, renamed configfile to settings.ini, added new message to chanal 'by'
- changed config

* Sat Sep 07 2019 Vitaly Lipatov <lav@altlinux.ru> 0.1-alt1
- initial build for ALT Sisyphus
