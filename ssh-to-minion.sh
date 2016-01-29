#!/bin/bash

if [ -z "$1" -o -z "$2" ]; then
    echo "This script will ssh into a salt minion as root."
    echo
    echo "Usage: $0 <miniontags> <minion-number> [<minion-basename>]"
    echo
    echo "Example: $0 3:precise:0.17.1-1precise_all:deb 2"
    exit 1
fi

if [ -z "$3" ]; then
    prefix="minion"
else
    prefix="$3"
fi
number="$2"

IFS=','
minion_tags=($1)
unset IFS

count=0
for entry in "${minion_tags[@]}"; do
    IFS=':'
    fields=($entry)
    tag_count=${fields[0]}
    unset IFS
    count=$(( $count + $tag_count ))
    if [ $count -ge $number ]; then
        image=${fields[1]}
        version=${fields[2]}
	version=`echo "$version" | sed -e 's/[^a-zA-Z0-9_.\-]//g;'`
        package=${fields[3]}
        name="${image}-${version}-${package}"
        break
    fi
done

HOST="${prefix}-${number}-${name}"

IPADDR=`docker inspect "--format={{.NetworkSettings.IPAddress}}" "$HOST"`

if [ -z "$IPADDR" ]; then
    echo "Failed to find IP address for $HOST"
    exit 1
else
    echo "$IPADDR"
fi

ssh -l root -o "StrictHostKeyChecking no" -o "UserKnownHostsFile /dev/null" "$IPADDR"
