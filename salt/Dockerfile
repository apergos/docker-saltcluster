# base dockerfile for creating salt master and clients in a cluster,
# one salt minion per container, and one salt master to rule them all

FROM ubuntu:12.04
ENV DEBIAN_FRONTEND noninteractive

RUN echo "deb http://archive.ubuntu.com/ubuntu precise main universe" > /etc/apt/sources.list
RUN apt-get update && apt-get install -y apt-utils

# set up ppa for hacked libselinux
RUN apt-get install -y python-software-properties && add-apt-repository ppa:ariel-wikimedia/ppa && apt-get update

# no steenkin selinux
RUN apt-get install -y libselinux1

# set up ppa for zmq3 and get it, required by salt
RUN add-apt-repository ppa:chris-lea/zeromq && apt-get update && apt-get install -y libzmq3 libzmq3-dev

# required for salt and/or pupaas
RUN apt-get install -y apt-utils python python-pkg-resources python-crypto python-jinja2 python-m2crypto python-zmq python-yaml dctrl-tools msgpack-python python-support

# salt source, so we can install from various branches
RUN apt-get install -y git && mkdir -p /src && git clone https://github.com/saltstack/salt.git /src/salt

# set up salt init scripts (can't rely on upstart)
RUN cat /src/salt/debian/salt-master.init | sed -e 's|usr/bin/salt-master|usr/local/bin/salt-master|g;' > /etc/init.d/salt-master
RUN cat /src/salt/debian/salt-minion.init | sed -e 's|usr/bin/salt-minion|usr/local/bin/salt-minion|g;' > /etc/init.d/salt-minion
RUN chmod 755 /etc/init.d/salt-master /etc/init.d/salt-minion

RUN mkdir -p /srv/runners /srv/salt /srv/pillars

# need these for master and minion
EXPOSE 4506 4505

# set up puppet for use via puppet apply
#
# conf file as provided by the package is installed
# in /etc/puppet/puppet.conf and doesn't need modification
# we need no certs or keys
RUN apt-get install -y puppet-common && mkdir -p /etc/puppet/files
ADD puppet-salt/fileserver.conf /etc/puppet/fileserver.conf
ADD puppet-salt/files/salt-master-config /etc/puppet/files/salt-master-config
ADD puppet-salt/templates/salt-minion-config.templ /etc/puppet/templates/salt-minion-config.templ
ADD puppet-salt/manifests/salt.pp /etc/puppet/manifests/salt.pp
# fixme this is horrible
ADD puppet-salt/salt_key_fingerprint.rb /usr/lib/ruby/1.8/facter/salt_key_fingerprint.rb

# set up puppet-as-a-service for post-startup config
# of container
RUN mkdir -p /src && git clone https://github.com/apergos/pupaas.git /src/pupaas
RUN cp /src/pupaas/pupaas.py /usr/sbin/
RUN mkdir -p /etc/pupaas && /bin/echo -e 'port=8010\nmanifests=/etc/puppet/' > /etc/pupaas/pupaas.conf

EXPOSE 8010

# ssh access into container
RUN apt-get install -y openssh-server && mkdir -p /var/run/sshd  && echo 'root:testing' |chpasswd

EXPOSE 22

#make sshd response quicker
RUN cat /etc/ssh/sshd_config | sed -e 's/#GSSAPIAuthentication no/GSSAPIAuthentication no/' > /etc/ssh/sshd_config.new
RUN mv /etc/ssh/sshd_config.new /etc/ssh/sshd_config

CMD python /usr/sbin/pupaas.py && /usr/sbin/sshd -D
