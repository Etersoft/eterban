#!/usr/bin/python3
import redis
import subprocess
import os

pidfile = open ('/var/run/action.pid', 'w')
pid = str(os.getpid()) + '\n'
pidfile.write(pid)
pidfile.close()


IP_addr_gateway = '192.168.100.50'
host_redis = '192.168.101.101'

subprocess.call ('ipset create blacklist hash:ip', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)

r = redis.Redis(host=host_redis)
p = r.pubsub()

p.subscribe('ban', 'unban')

for message in p.listen():
    if message is not None and  message['type']=='message' and message['channel'] == b'ban':
        #print (message)
        ip = message['data'].decode('utf-8')
        #ban = 'ipset -A blacklist ' + ip
        ban = 'fail2ban-client set blacklist  banip ' + ip
        #subprocess.call (ban, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        subprocess.call (ban, shell = True)
        tcp_drop = 'conntrack -D -s ' + ip
        subprocess.Popen(tcp_drop, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.Popen(tcp_drop, shell = True)
    elif message is not None and message['type'] =='message' and message['channel'] == b'unban' :
        #print (message)
        ip = message['data'].decode('utf-8')
        #unban = 'ipset -D blacklist ' + ip
        unban = 'fail2ban-client set blacklist unbanip ' + ip
        subprocess.call (unban, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.call (unban, shell = True)
        tcp_drop = 'conntrack -D -s ' + ip
        subprocess.Popen(tcp_drop, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
        #subprocess.Popen(tcp_drop, shell = True)
    elif message is not None:
        #print ("AHTUNG!!1!", message)
        pass
    else:
        pass
