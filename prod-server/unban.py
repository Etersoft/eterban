#!/usr/bin/python3
import redis
import os
import subprocess

ban_list_name = 'nginx-limit-req'

pid = str( os.getpid()) + '\n'
pidfile = open ('/var/run/unban.pid', 'w')
pidfile.write(pid)
pidfile.close()

host_redis = '192.168.101.101'
r = redis.Redis ( host = host_redis)
p = r.pubsub()
p.subscribe( 'unban')

for message in p.listen():
    if message is not None and message['type'] =='message':
        ip = message['data'].decode('utf-8')
        unban = 'fail2ban-client set ' + ban_list_name + ' unbanip ' + ip
        subprocess.Popen( unban, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.Popen( unban, shell = True)
    else:
        pass