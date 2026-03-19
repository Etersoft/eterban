# Проверка eterban после деплоя

## Подготовка

На priv (ssh -p32 91.232.225.1):
```bash
# Проверить что eterban запущен
sudo systemctl status eterban
# Проверить ipset
sudo eterban count
# Проверить iptables правила
sudo iptables -t nat -L PREROUTING -n | grep -E 'eterban|firehol|vmbr0'
sudo ip6tables -t nat -L PREROUTING -n | grep eterban
```

## 1. Внешний IPv4 (DNAT по source)

Забанить sprintbox, проверить с него через hetzner, разбанить:
```bash
# На priv:
sudo eterban ban 138.249.117.171

# С hetzner (ssh -p32 root@hetzner.egw.eterhost.ru):
ssh root@138.249.117.171 'curl -s --connect-timeout 5 http://etersoft.ru/ | grep title'
# Ожидание: <title>Ваш IP-адрес заблокирован на сервере. You are banned!</title>

# На priv:
sudo eterban unban 138.249.117.171
```

## 2. Внешний IPv6 (DNAT по source)

Забанить IPv6 vdska, проверить с него, разбанить:
```bash
# На priv:
sudo eterban ban 2a0d:6c2:25::3

# С vdska (ssh root@vdska.egw.eterhost.ru):
curl -6 -s --connect-timeout 5 http://etersoft.ru/ | grep title
# Ожидание: <title>Ваш IP-адрес заблокирован на сервере. You are banned!</title>

# На priv:
sudo eterban unban 2a0d:6c2:25::3
```

## 3. Внутренний IPv4 (DNAT по destination)

Обратиться с офисной машины к забаненному IPv4:
```bash
# С builder или epm-sisyphus:
curl -s --connect-timeout 5 http://210.79.191.76/ | grep title
# Ожидание: <title>Eterban ban</title>
```

## 4. Внутренний IPv6 (DNAT по destination)

Забанить тестовый IPv6, обратиться к нему изнутри, разбанить:
```bash
# На priv:
sudo eterban ban 2a0d:6c2:25::3

# С epm-sisyphus:
curl -6 -s --connect-timeout 5 http://[2a0d:6c2:25::3]/ | grep title
# Ожидание: <title>Ваш IP-адрес заблокирован на сервере. You are banned!</title>

# На priv:
sudo eterban unban 2a0d:6c2:25::3
```

## 5. Проверка int2.py (внутренний сервер плашки)

```bash
# На priv:
sudo systemctl status eterban-internal
# Должен быть active (running)
# Слушает на ban_server:82

curl -s http://91.232.225.67:82/ | grep title
# Ожидание: <title>Eterban ban</title>
```

## Примечания

- SSH к sprintbox доступен только с 91.232.225.0/24 и hetzner (135.181.95.108)
- КАТЕГОРИЧЕСКИ нельзя банить hetzner (135.181.95.108) — через него идут GRE/VPN туннели
- НЕ банить другие рабочие серверы (sprintbox и т.д.) без крайней необходимости
- int2.py использует SO_ORIGINAL_DST для определения оригинального IP назначения
- IPv6 адрес 2a03:5a00:c:20::67 должен быть назначен на vmbr0
