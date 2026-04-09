import socket
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import redis
import configparser
import os


# Чтение настроек из INI-файла
def read_settings(settings_file):
    config = configparser.ConfigParser()
    config.read(settings_file)
    return config['Settings']


# Функция для получения оригинального адреса назначения
def get_original_dst(sock):
    try:
        # Используем SO_ORIGINAL_DST для получения оригинального адреса назначения
        # SO_ORIGINAL_DST = 80 (для Linux)
        dst = sock.getsockopt(socket.SOL_IP, 80, 16)
        ip, port = struct.unpack("!IH", dst[4:10])
        return f"{socket.inet_ntoa(struct.pack('!I', ip))}:{port}"
    except Exception as e:
        return f"Error: {e}"


# Кастомный обработчик HTTP-запросов
class OriginalDstHandler(BaseHTTPRequestHandler):
    timeout = 5

    def do_GET(self):
        # Получаем оригинальный адрес назначения
        original_dst = get_original_dst(self.request)
        if ":" in original_dst:
            ip, port = original_dst.split(":", 1)
        else:
            ip, port = original_dst, "0"

        client_ip = self.headers.get('X-Forwarded-For', self.client_address[0])


        # Обработка запроса на разблокировку
        if self.path.startswith("/unban"):
            # Извлекаем IP из параметра запроса
            import urllib.parse
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            target_ip = params.get("ip", [None])[0]


            # Получаем предыдущий адрес (HTTP_REFERER)
            #old_addr = self.headers.get('Referer', '')

            if not target_ip:
                response_message = "No IP provided for unban."

                # Возвращаем ответ
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(response_message.encode("utf-8"))
                return

            # Читаем настройки из файла
            settings_file = '/etc/eterban/settings.ini'
            settings = read_settings(settings_file)

            # Подключаемся к Redis
            host_redis = settings.get('redis_server', 'localhost')

            try:
                r = redis.Redis(host=host_redis, port=6379, socket_timeout=5)
                r.publish('unban', ip)
                r.publish('by', f"{ip} was unblocked by {client_ip}")
                r.close()
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(f"Error connecting to Redis: {e}".encode("utf-8"))
                return

            # Возвращаем HTML-страницу с сообщением и JavaScript для перенаправления
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            response = f"""
            <html>
                <head><title>Unban IP</title></head>
                <body>
                    <p>IP {ip} has been unblocked. Wait 5 seconds, please.</p>
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
                <p>You accessed: <strong>{ip}</strong> from your IP {client_ip}</p>
                <p>
                    <a href="/unban.php?ip={ip}">
                        <button>Unban IP: {ip}</button>
                    </a>
                </p>
            </body>
        </html>
        """
        self.wfile.write(response.encode("utf-8"))

# Запуск HTTP-сервера
def run_server(port=82):
    server_address = ("91.232.225.67", port)
    httpd = ThreadingHTTPServer(server_address, OriginalDstHandler)
    httpd.timeout = 5
    print(f"Starting server on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
