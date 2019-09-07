#!/usr/bin/python3
mport sys, radom, redis
host_redis = '192.168.101.101'
r = redis.Redis (host=host_redis)
r.publish ('ban', sys.argv[1])