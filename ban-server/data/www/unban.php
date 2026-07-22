<?php
header('Content-Type: text/html; charset=utf-8');
session_start();

$ip = $_SERVER['REMOTE_ADDR'] ?? '';
$settings = parse_ini_file('/etc/eterban/settings.ini');
$host_redis = is_array($settings) ? ($settings['redis_server'] ?? '') : '';
$redis_username = is_array($settings) ? ($settings['redis_username'] ?? '') : '';
$redis_password = is_array($settings) ? ($settings['redis_password'] ?? '') : '';
$redis_tls = is_array($settings) && filter_var($settings['redis_tls'] ?? false, FILTER_VALIDATE_BOOLEAN);
$hostname = is_array($settings) ? ($settings['hostname'] ?? '') : '';

if (!filter_var($ip, FILTER_VALIDATE_IP) || empty($host_redis)) {
    http_response_code(503);
    error_log('eterban: invalid client IP or Redis configuration for web unban');
    exit('Unban service is temporarily unavailable.');
}

if (empty($hostname)) {
    $hostname = gethostname();
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    $nonce = bin2hex(random_bytes(16));
    $_SESSION['eterban_unban_nonce'] = $nonce;
    $_SESSION['eterban_unban_expires'] = time() + 300;
    ?>
<!doctype html>
<html><head><meta charset="utf-8"><title>Unban request</title></head>
<body><p>Preparing unban request…</p>
<noscript>JavaScript is required to submit an unban request.</noscript>
<form id="unban-form" method="post">
  <input type="hidden" name="nonce" value="<?= htmlspecialchars($nonce, ENT_QUOTES, 'UTF-8') ?>">
  <input type="hidden" id="proof" name="proof">
</form>
<script>
async function submitUnban() {
  const nonce = document.querySelector('[name=nonce]').value;
  const bytes = new TextEncoder().encode('eterban-unban-v1:' + nonce);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  document.getElementById('proof').value = [...new Uint8Array(digest)]
    .map(value => value.toString(16).padStart(2, '0')).join('');
  document.getElementById('unban-form').submit();
}
submitUnban();
</script></body></html>
<?php
    exit;
}

$nonce = $_POST['nonce'] ?? '';
$proof = $_POST['proof'] ?? '';
$expires = $_SESSION['eterban_unban_expires'] ?? 0;
$session_nonce = $_SESSION['eterban_unban_nonce'] ?? '';
$expected = hash('sha256', 'eterban-unban-v1:' . $session_nonce);
unset($_SESSION['eterban_unban_nonce'], $_SESSION['eterban_unban_expires']);
if (!is_string($nonce) || !is_string($proof) || time() > $expires ||
    !hash_equals($session_nonce, $nonce) ||
    !hash_equals($expected, $proof)) {
    http_response_code(400);
    exit('Invalid or expired unban challenge.');
}

try {
    $redis = new Redis();
    if (!$redis->connect($host_redis, 6379, 2.5, null, 0, 0, $redis_tls ? ['stream' => ['verify_peer' => true]] : [])) {
        throw new RedisException('connection failed');
    }
    if ($redis_password !== '' && !$redis->auth($redis_username !== '' ? [$redis_username, $redis_password] : $redis_password)) {
        throw new RedisException('authentication failed');
    }
    $redis->xAdd('eterban:commands', '*', [
        'command' => 'unban',
        'ip' => $ip,
        'by' => $ip . ' was unblocked by ' . $hostname,
    ]);
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
