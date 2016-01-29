#!/bin/bash

if [ -z "$1" ]; then
    echo "This script will scp the trigger repo in trigger/ to the salt deployment server."
    echo "It will, sadly, prompt you twice for the password. Sorry."
    echo "Default root password when prompted: testing"
    echo
    echo "Usage: $0 <depserver-tag> [<salt-minion-basename>]"
    echo
    echo "Example: $0 precise:0.17.1-1precise_all:deb"
    exit 1
fi

tagspec=`echo "$1" | sed -e 's/:/-/g; s/[^a-zA-Z0-9_.\-]//g;'`

if [ ! -z "$2" ]; then
    HOST="${2}-${tagspec}"
else
    HOST="minion-${tagspec}"
fi

IPADDR=`docker inspect "--format={{.NetworkSettings.IPAddress}}" "$HOST"`

if [ -z "$IPADDR" ]; then
    echo "Failed to find IP address for $HOST"
    exit 1
else
    echo "$IPADDR"
fi

ssh -l root -o "StrictHostKeyChecking no" -o "UserKnownHostsFile /dev/null" "$IPADDR" "mkdir -p /root/trigger-tmp/trigger"
scp -r -o "StrictHostKeyChecking no" -o "UserKnownHostsFile /dev/null" trigger/* "root@${IPADDR}:/root/trigger-tmp/trigger"
