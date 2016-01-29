#!/bin/bash

if [ -z "$1" ]; then
    echo "This script will ssh into the salt master as root."
    echo
    echo "Usage: $0 <mastertag> [<salt-master-basename>]"
    echo
    echo "Example: $0 precise:0.17.1-1precise_all:deb"
    exit 1
fi

tagspec=`echo "$1" | sed -e 's/:/-/g; s/[^a-zA-Z0-9_.\-]//g;'`

if [ ! -z "$2" ]; then
    HOST="${2}-${tagspec}"
else
    HOST="master-${tagspec}"
fi

IPADDR=`docker inspect "--format={{.NetworkSettings.IPAddress}}" "$HOST"`

if [ -z "$IPADDR" ]; then
    echo "Failed to find IP address for $HOST"
    exit 1
else
    echo "$IPADDR"
fi

ssh -l root -o "StrictHostKeyChecking no" -o "UserKnownHostsFile /dev/null" "$IPADDR"
