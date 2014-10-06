#!/bin/bash
# add/change the appropriate lines in either the master or
# minion config file to enable the redis returner

if [ -z $1 -o -z $2 ]; then
    echo "Usage: $0 redis-container-ip master"
    echo "       or"
    echo "       $0 redis-container-ip minion"
    echo "to alter the master or the minion config file"
    echo
    echo "This script must be run from the master or"
    echo "minion with the config file to be altered."
    exit 1
fi

if [ "$2" != "master" -a "$2" != "minion" ]; then
    echo "Second argument must be 'master' or 'minion'"
    exit 1
fi

redishost="$1"
configfile="/etc/salt/$2"
echostring="redis.host: '"$redishost"'"

present=`grep 'redis.host' /etc/salt/master`
if [ "$present" ]; then
    grep -v 'redis.host' $configfile > ${configfile}.new
    echo $echostring >> ${configfile}.new
    cp ${configfile}.new $configfile
else
    echo "redis.db: '0'" >> $configfile
    echo $echostring >> $configfile
    echo "redis.port: 6379" >> $configfile
fi

"/etc/init.d/salt-${2}" restart
