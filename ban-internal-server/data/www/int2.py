import socket
import struct
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from urllib.parse import quote

import redis
import configparser
import ipaddress


logger = logging.getLogger(__name__)


# Чтение настроек из INI-файла
def read_settings(settings_file):
    config = configparser.ConfigParser()
    config.read(settings_file)
    return config['Settings']


def redis_connection_options(settings):
    """Build Redis options, including optional ACL credentials and TLS."""
    options = {
        'host': settings.get('redis_server', 'localhost'),
        'port': settings.getint('redis_port', 6379),
        'socket_timeout': 5,
    }
    username = settings.get('redis_username', '').strip()
    password = settings.get('redis_password', '').strip()
    if username:
        options['username'] = username
    if password:
        options['password'] = password
    if settings.getboolean('redis_tls', False):
        options['ssl'] = True
    return options


# Функция для получения оригинального адреса назначения
def get_original_dst(sock):
    try:
        dst = sock.getsockopt(socket.SOL_IP, 80, 16)  # SO_ORIGINAL_DST
        return str(ipaddress.IPv4Address(dst[4:8])), struct.unpack('!H', dst[2:4])[0]
    except OSError:
        try:
            dst = sock.getsockopt(socket.IPPROTO_IPV6, 80, 28)  # IP6T_SO_ORIGINAL_DST
            return str(ipaddress.IPv6Address(dst[8:24])), struct.unpack('!H', dst[2:4])[0]
        except OSError:
            return None, None


# Кастомный обработчик HTTP-запросов
class OriginalDstHandler(BaseHTTPRequestHandler):
    timeout = 5

    def do_GET(self):
        # Получаем оригинальный адрес назначения
        ip, port = get_original_dst(self.request)
        if not ip:
            self.send_error(502, 'Original destination is unavailable')
            return
        client_ip = self.client_address[0]


        # Обработка запроса на разблокировку
        if self.path.startswith("/unban"):
            # Читаем настройки из файла
            settings_file = '/etc/eterban/settings.ini'
            settings = read_settings(settings_file)

            # Подключаемся к Redis
            try:
                r = redis.Redis(**redis_connection_options(settings))
                r.xadd('eterban:commands', {
                    'command': 'unban', 'ip': ip,
                    'by': f"{ip} was unblocked by {client_ip}",
                })
                r.close()
            except (redis.RedisError, ValueError):
                logger.exception('Unable to enqueue internal unban request')
                self.send_error(503, 'Unable to process unban request')
                return

            # Возвращаем HTML-страницу с сообщением и JavaScript для перенаправления
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            response = f"""
            <html>
                <head><title>Unban IP</title></head>
                <body>
                    <p>IP {escape(ip)} has been unblocked. Wait 5 seconds, please.</p>
                    <script>
                        function update() {{
                            window.location.href = "/";
                        }}
                        setTimeout(update, 5000);
                    </script>
                </body>
            </html>
            """
            self.wfile.write(response.encode("utf-8"))
            return


        # Формируем ответ для основного запроса
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        # Возвращаем HTML-страницу с информацией и кнопкой разблокировки
        response = f"""
        <html>
            <head><title>Eterban ban</title></head>
            <body>
                <h2>Eterban note.</h2>
                <h3>Access to this IP address is restricted due to it suspicious activity.</h3>
                <p>You accessed: <strong>{escape(ip)}</strong> from your IP {escape(client_ip)}</p>
                <p>
                    <a href="/unban.php?ip={quote(ip, safe='')}">
                        <button>Unban IP: {escape(ip)}</button>
                    </a>
                </p>
            </body>
        </html>
        """
        self.wfile.write(response.encode("utf-8"))

# Запуск HTTP-сервера
def run_server(host, port=82):
    address = ipaddress.ip_address(host)
    if isinstance(address, ipaddress.IPv6Address):
        class IPv6ThreadingHTTPServer(ThreadingHTTPServer):
            address_family = socket.AF_INET6
        server_class = IPv6ThreadingHTTPServer
    else:
        server_class = ThreadingHTTPServer
    server_address = (str(address), port)
    httpd = server_class(server_address, OriginalDstHandler)
    httpd.timeout = 5
    print(f"Starting server on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    try:
        settings = read_settings('/etc/eterban/settings.ini')
        run_server(settings['ban_server'])
    except (KeyError, ValueError, configparser.Error) as error:
        logger.error('Invalid Eterban configuration: %s', error)
        raise SystemExit(78)
