#!/usr/bin/python3
import sys, redis

f = open ('/etc/eterban/eterban.conf','r')
line = f.readline()
f.close()
if line[:10] == "host_redis":
    if line[-1] == '\n':
        host_redis = line[-16:-1]
    else:
        host_redis = line[-15:]
r = redis.Redis (host=host_redis)
r.publish ('ban', sys.argv[1])