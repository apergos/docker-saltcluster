#!/bin/bash

exec 3>&1

function get_container_id () {
    running="$1"
    prompt="$2"

    ids=($(echo "$running" | awk '{ print $1 }'))
    names=($(echo "$running" | awk '{ print $NF }'))

    num=${#ids[@]}

    if [ $num -gt 1 ]; then
        while true; do
            echo "please choose from among the following ${prompt}:" 1>&3
            for count in `seq 0  $(( $num - 1 ))`; do
                echo "${count}: ${redis_ids[$count]} (${names[$count]})" 1>&3
            done
            echo -n "number? [0] " 1>&3
            read choice
            if [ $choice -ge 0 -a $choice -lt $num ]; then
	        result=${ids[$choice]}
                break
            fi
        done
    elif [ $num -eq 0 ]; then
        echo "No ${prompt} are running. Please" 1>&3
        echo "start one up." 1>&3
        exit 1
    else
        result=${ids[0]}
    fi
    echo $result
}

redis_running=`docker ps | grep redis`
redis=$(get_container_id "$redis_running" 'redis containers')
status=$?
if [ $status -ne 0 ]; then
  exit $status
fi

masters_running=`docker ps | grep master`
master=$(get_container_id "$masters_running" 'salt masters')
status=$?
if [ $status -ne 0 ]; then
  exit $status
fi

master_ip=`docker inspect "--format={{.NetworkSettings.IPAddress}}" $master`
redis_ip=`docker inspect "--format={{.NetworkSettings.IPAddress}}" $redis`

../../expect_scp.sh ${master_ip} testing enable-redis-returner-local-coordinator.sh /root/
../../expect_scp.sh ${master_ip} testing enable-redis-returner-local.sh /root/
../../expect_ssh.sh ${master_ip} testing "bash /root/enable-redis-returner-local-coordinator.sh ${redis_ip}"
