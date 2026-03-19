<?php
 $ip = $_SERVER['REMOTE_ADDR'];
 $old_addr = $_SERVER['HTTP_REFERER'];
 $settings = '/etc/eterban/settings.ini';
 $ini_array = parse_ini_file ("$settings");
 //print_r($ini_array);
 //print_r($ini_array['redis_server']);
 $host_redis = $ini_array['redis_server'];
 //print_r($host_redis);
 $hostname = $ini_array['hostname'];
 if (empty($hostname)) {
  $hostname=gethostname();
  //print_r ($hostname);
 }
 $redis = new Redis();
 $redis->pconnect($host_redis,6379);
 $redis->publish('unban', $ip);
 $redis->publish('by', $ip . " was unblocked by $hostname");
 $redis->close();
 echo "Wait 5 seconds, please"
?>
<script>
 function update()
 {
  window.location.href = "/";
 }
 setTimeout("update()", 5000);

</script>
