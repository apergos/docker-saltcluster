#!/bin/bash

if [ -z "$1" -o -z "$2" ]; then
    echo "This script wil ssh into a salt minion as root."
    echo
    echo "Usage: $0 tag-string-here minion-number [salt-minion-basename]"
    echo
    echo "Example: $0 v0.15.0 3"
    exit 1
fi

if [ ! -z "$3" ]; then
    HOST="${3}-${2}-${1}"
else
    HOST="minion-${2}-${1}"
fi

IPADDR=`docker inspect "-format={{.NetworkSettings.IPAddress}}" "$HOST"`

if [ -z "$IPADDR" ]; then
    echo "Failed to find IP address for $HOST"
    exit 1
else
    echo "$IPADDR"
fi

ssh -l root "$IPADDR"
