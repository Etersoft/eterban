#!/usr/bin/python3
import redis
import subprocess

f = open ('/etc/eterban/eterban_swicher.conf','r')
line = f.readline()
f.close()
if line[:10] == "host_redis":
    if line[-1] == '\n':
        host_redis = line[-16:-1]
    else:
        host_redis = line[-15:]
del(line)
del(f)

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
