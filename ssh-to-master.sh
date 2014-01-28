#!/bin/bash

if [ -z "$1" ]; then
    echo "This script wil ssh into the salt master as root."
    echo
    echo "Usage: $0 tag-string-here [salt-master-basename]"
    echo
    echo "Example: $0 v0.15.0"
    exit 1
fi

if [ ! -z "$2" ]; then
    HOST="${2}-${1}"
else
    HOST="saltmaster-${1}"
fi

IPADDR=`docker inspect "-format={{.NetworkSettings.IPAddress}}" "$HOST"`

if [ -z "$IPADDR" ]; then
    echo "Failed to find IP address for $HOST"
    exit 1
else
    echo "$IPADDR"
fi

ssh -l root "$IPADDR"
