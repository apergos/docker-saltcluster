#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage $0 redis-host-ip"
    exit 1
fi

redishost="$1"

script="enable-redis-returner-local.sh"
scriptpath="/root/${script}"

if [ -f "$scriptpath" ]; then
    echo "Proceeding..."
else
    echo "Missing $scriptpath, has it been copied to the master?"
fi

echo "configuring master for redis"
bash "$scriptpath" "$redishost" master

# give master time to recover
sleep 10

echo "copying scripts to minion(s)"
salt-cp '*' "$scriptpath" /root/

echo "installing redis client on minions"
salt '*' cmd.run 'apt-get install -y python-redis'

echo "configuring minions for redis"
salt '*' cmd.run "bash $scriptpath $redishost minion"
salt '*' cmd.run 'cat /etc/salt/minion'

echo 'checking that master and minions are running'
salt '*' test.ping
echo 'please check that all minions replied to pings'

echo 'checking that redis returner is operational'
salt '*' test.ping --return redis
salt '*' ret.get_fun redis test.ping
echo 'did clients respond with information about the test.ping run?'
