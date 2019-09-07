//Где сменить IP-адреса серверов
<?php
$ip = $_SERVER['REMOTE_ADDR'];
echo "You are banned!, Your IP: $ip <br>";

$redis = new Redis;
$redis->pconnect ('192.168.0.99',6379);
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