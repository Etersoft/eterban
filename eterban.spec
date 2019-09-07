Name: eterban
Version: 0.1
Release: alt1

Summary: Etersoft ban service

License: AGPLv3
Group: Development/Other
Url: http://wiki.etersoft.ru/eterban

Packager: Vitaly Lipatov <lav@altlinux.ru>

# Source-git: https://gitlab.eterfund.ru/diff/eterban.git
Source: %name-%version.tar

BuildArchitectures: noarch

# error: File must begin with "/": %webserver_htdocsdir/maintenance/
BuildRequires: rpm-macros-webserver-common

#Requires: nginx >= 1.8.1

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
install -m 755 gateway/usr/share/* %buildroot%_datadir/%name/
install -m 644 gateway/etc/eterban/* %buildroot/etc/%name/
install -m 644 gateway/etc/fail2ban/action.d/* %buildroot/etc/fail2ban/action.d/
install -m 644 gateway/etc/fail2ban/jail.d/* %buildroot/etc/fail2ban/jail.d/
install -m 644 gateway/etc/systemd/system/* %buildroot/etc/systemd/system/
install -m 644 ban-server/data/www/* %buildroot/ban-server/data/www/


#mkdir -p %buildroot%_datadir/%name/images/
#install -m644 share/images/* %buildroot%_datadir/%name/images/

#mkdir -p %buildroot%webserver_htdocsdir/maintenance/
#install -m644 www/* %buildroot%webserver_htdocsdir/maintenance/

%files gateway
#%dir %_sysconfdir/nginx/include/
#%config(noreplace) %_sysconfdir/nginx/include/*

%files web
%webserver_htdocsdir/%name/

#%files fail2ban
#%_datadir/%name/file

%changelog
* Sat Sep 07 2019 Vitaly Lipatov <lav@altlinux.ru> 0.1-alt1
- initial build for ALT Sisyphus
