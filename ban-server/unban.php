<?php
 $ip = $_SERVER['REMOTE_ADDR'];
 $old_addr = $_SERVER['HTTP_REFERER'];
 $host_redis = '192.168.101.101';
 $redis = new Redis();
 $redis->pconnect($host_redis,6379);
 $redis->publish('unban', $ip);
 $redis->close();
 echo "Wait 5 secons, please"
?>
<script>
 function update()
 {
  window.location.href = "/";
 }
 setTimeout("update()", 5000);

</script>