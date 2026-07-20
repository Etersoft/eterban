<?php
header('Content-Type: text/html; charset=utf-8');

$ip = $_SERVER['REMOTE_ADDR'] ?? '';
$settings = parse_ini_file('/etc/eterban/settings.ini');
$host_redis = is_array($settings) ? ($settings['redis_server'] ?? '') : '';
$hostname = is_array($settings) ? ($settings['hostname'] ?? '') : '';

if (!filter_var($ip, FILTER_VALIDATE_IP) || empty($host_redis)) {
    http_response_code(503);
    error_log('eterban: invalid client IP or Redis configuration for web unban');
    exit('Unban service is temporarily unavailable.');
}

if (empty($hostname)) {
    $hostname = gethostname();
}

try {
    $redis = new Redis();
    if (!$redis->connect($host_redis, 6379, 2.5)) {
        throw new RedisException('connection failed');
    }
    $subscribers = $redis->publish('unban', $ip);
    if ($subscribers < 1) {
        throw new RedisException('no Redis subscribers');
    }
    $redis->publish('by', $ip . ' was unblocked by ' . $hostname);
    $redis->close();
} catch (RedisException $error) {
    http_response_code(503);
    error_log('eterban: web unban request was not delivered: ' . $error->getMessage());
    exit('Unban service is temporarily unavailable. Please contact an administrator.');
}

echo 'Unban request accepted. Wait 5 seconds, please.';
?>
<script>
 function update()
 {
  window.location.href = "/";
 }
 setTimeout("update()", 5000);

</script>
