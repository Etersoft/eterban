#!/usr/bin/python3
import sys, redis

f = open ('/etc/eterban/eterban.conf','r')
line = f.readline()
f.close()
if line[:10] == "host_redis":
    i = 10
    while (line[i] == ' '):
        i+=1
    i+=1
    while (line[i] == ' '):
        i+=1

    if line[-1] == '\n':
        host_redis = line[i:-1]
    else:
        host_redis = line[i:]
r = redis.Redis (host=host_redis)
r.publish ('ban', sys.argv[1])