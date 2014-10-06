# base dockerfile for creating salt master and clients in a cluster,
# this base image uses ubuntu trusty; base imges may be mixed and matched
# one salt minion per container, and one salt master to rule them all

FROM ubuntu:14.04
ENV DEBIAN_FRONTEND noninteractive

RUN echo "deb http://archive.ubuntu.com/ubuntu trusty main universe" > /etc/apt/sources.list
RUN apt-get update && apt-get install -y apt-utils

# we don't need these for trusty
# set up ppa for zmq3 and get it, required by salt
#RUN add-apt-repository ppa:chris-lea/zeromq && apt-get update && apt-get install -y libzmq3 libzmq3-dev

RUN apt-get install -y apt-utils redis-server
EXPOSE 6379
RUN cat /etc/redis/redis.conf | sed -e 's/^bind/#bind/g;' > /etc/redis/redis.conf.new
RUN mv /etc/redis/redis.conf.new /etc/redis/redis.conf

# ssh access into container
RUN apt-get install -y openssh-server && mkdir -p /var/run/sshd  && echo 'root:testing' |chpasswd

EXPOSE 22

# make sshd response quicker; allow login as root with password
RUN cat /etc/ssh/sshd_config | sed -e 's/#GSSAPIAuthentication no/GSSAPIAuthentication no/; s/PermitRootLogin without-password/PermitRootLogin yes/' > /etc/ssh/sshd_config.new
RUN mv /etc/ssh/sshd_config.new /etc/ssh/sshd_config

# workaround for auditd or unwriteable /proc or broken pam loginuid module
RUN cat /etc/pam.d/sshd | sed -e 's/session    required     pam_loginuid.so/#session    required     pam_loginuid.so/' > /etc/pam.d/sshd.new
RUN mv /etc/pam.d/sshd.new /etc/pam.d/sshd

CMD /etc/init.d/redis-server start && /usr/sbin/sshd -D
