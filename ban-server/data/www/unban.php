<?php
 $ip = $_SERVER['REMOTE_ADDR'];
 $old_addr = $_SERVER['HTTP_REFERER'];
 $host_redis = '10.20.30.101';
 $redis = new Redis();
 $redis->pconnect($host_redis,6379);
 $redis->publish('unban', $ip);
 $redis->publish('by', $ip . " was unblocked by ckick");
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