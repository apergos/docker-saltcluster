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
echo "waiting for master worker threads to get setup"
sleep 15

echo "making sure minions are reconnected and re-auth their keys"
salt '*' -v --timeout 120 --out raw test.ping

echo "copying scripts to minion(s)"
salt-cp '*' "$scriptpath" /root/

echo "installing redis client on minions"
salt '*' cmd.run 'apt-get install -y python-redis'

echo "configuring minions for redis"
salt '*' cmd.run "bash $scriptpath $redishost minion"

echo "giving minions time to reconnect"
sleep 5

echo 'checking that master and minions are running'
salt '*' -v --out raw test.ping
echo 'please check that all minions replied to pings'

echo 'checking that redis returner is operational'
salt '*' test.ping --return redis
salt '*' ret.get_fun redis test.ping
echo 'did clients respond with information about the test.ping run?'
