//Где сменить IP-адреса серверов
<?php
$ip = $_SERVER['REMOTE_ADDR'];
echo "You are banned!, Your IP: $ip <br>";

$settings = '/etc/eterban/settings.ini';
$ini_array = parse_ini_file ("$settings");
$host_redis = $ini_array['redis_server'];

$redis = new Redis;
$redis->pconnect ($host_redis,6379);
$key = $redis->get($ip);
?>

<button onclick="unban()">Unban</button>

<script type="text/javascript" src="//cdnjs.cloudflare.com/ajax/libs/jquery/2.2.0/jquery.js"></script>

<script>

function unban(){
    /*$.get("unban.php?&key=<?php echo $key;?>", function(data, status){
        });*/
    
    window.location.href = "unban.php?key=<?php echo $key; ?>";
}
</script>