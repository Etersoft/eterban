Name: eterban
Version: 0.1
Release: alt1

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

%description web
Etersoft ban service.


%package fail2ban
Summary: Etersoft ban service: fail2ban
Group: Development/Other

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
mkdir -p %buildroot/etc/fail2ban/jail.d/
mkdir -p %buildroot/etc/systemd/system/

mkdir -p %buildroot%webserver_htdocsdir/%name/


cp -a gateway/usr/share/%name/* %buildroot%_datadir/%name/
install -m 644 gateway/etc/eterban/* %buildroot/etc/%name/
install -m 644 gateway/etc/fail2ban/action.d/* %buildroot/etc/fail2ban/action.d/
install -m 644 gateway/etc/fail2ban/jail.d/* %buildroot/etc/fail2ban/jail.d/

install -m 644 gateway/etc/systemd/system/* %buildroot/etc/systemd/system/

install -m 644 ban-server/data/www/* %buildroot%webserver_htdocsdir/%name/

install -m 644 prod-server/etc/fail2ban/action.d/* %buildroot/etc/fail2ban/action.d/
install -m 644 prod-server/etc/fail2ban/jail.d/* %buildroot/etc/fail2ban/jail.d/

cp -a prod-server/usr/share/%name/* %buildroot%_datadir/%name/

%files gateway
%config(noreplace) /etc/%name/eterban.conf
%config(noreplace) /etc/fail2ban/action.d/ban.conf
%config(noreplace) /etc/fail2ban/jail.d/blacklist.conf
/etc/systemd/system/
%_datadir/%name/eterban_switcher.py

%files web
%webserver_htdocsdir/%name/

%files fail2ban
%config(noreplace) /etc/%name/eterban.conf
%_datadir/%name/ban.py
%config(noreplace) /etc/fail2ban/action.d/eterban.conf
%config(noreplace) /etc/fail2ban/jail.d/eterban.conf
%changelog
* Sat Sep 07 2019 Vitaly Lipatov <lav@altlinux.ru> 0.1-alt1
- initial build for ALT Sisyphus
