#!/bin/bash

# for wmf testing purposes use a precise host for the deployment server

# check that we are on the salt master
is_master_running=`pgrep salt-master`
if [ -z "$is_master_running" ]; then
  echo "This script needs to be run on the salt master; please"
  echo "be sure you are on the right host and that the"
  echo "salt master is running."
  exit 1
fi

# check that we've been given the hostname of the redis/deploy server
if [ -z "$1" ]; then
  echo "Usage: $0 hostname"
  echo "where hostname is the name of the minion to be used as the"
  echo "development server and also the redis server."
  exit 1
fi

SOMETHING="$1"

if [ ! -e "/root/treb-tmp/trebuchet" ]; then
  echo "setting up trebuchet on master"

  mkdir -p /root/treb-tmp
  cd /root/treb-tmp

  # install trebuchet pieces to the right place
  git clone https://github.com/trebuchet-deploy/trebuchet.git
  mkdir -p /srv/salt/_returners /srv/salt/_modules /srv/runners

  cd trebuchet
  cp runners/deploy.py /srv/runners/
  cp returners/deploy_redis.py /srv/salt/_returners/
  # patch the module til it's updated for yaml arg syntax
  ( cat <<'EOF'
--- deploy.py   2015-05-04 20:25:09.965296025 +0000
+++ deploy.py.new       2015-05-04 20:25:52.188022818 +0000
@@ -235,20 +235,20 @@
                 continue
             # git clone does ignores umask and does explicit mkdir with 755
             __salt__['file.set_mode'](config['location'], 2775)
-            # Set the repo name in the repo's config
-            cmd = 'git config deploy.repo-name %s' % repo
-            status = __salt__['cmd.retcode'](cmd, cwd=config['location'],
+        # Set the repo name in the repo's config
+        cmd = 'git config deploy.repo-name %s' % repo
+        status = __salt__['cmd.retcode'](cmd, cwd=config['location'],
                                              runas=deploy_user, umask=002)
-            if status != 0:
+        if status != 0:
                 ret_status = 1
-            # Ensure checkout-submodules is also configured for trigger
-            if config['checkout_submodules']:
+        # Ensure checkout-submodules is also configured for trigger
+        if config['checkout_submodules']:
                 cmd = 'git config deploy.checkout-submodules true'
-            else:
+        else:
                 cmd = 'git config deploy.checkout-submodules false'
-            status = __salt__['cmd.retcode'](cmd, cwd=config['location'],
+        status = __salt__['cmd.retcode'](cmd, cwd=config['location'],
                                              runas=deploy_user, umask=002)
-            if status != 0:
+        if status != 0:
                 ret_status = 1
     return ret_status
EOF
  ) > /root/deploy.py.patch
  (cd modules; patch < /root/deploy.py.patch)
  cp modules/deploy.py /srv/salt/_modules/
  cd ..
fi

ipadded=`grep $SOMETHING /etc/hosts`
if [ -z "$ipadded" ]; then
  echo "adding deploy server ip to /etc/hosts on all hosts"

  output=`salt $SOMETHING cmd.run 'ip -4 addr show dev eth0 | grep inet'`
  IP=`echo $output | cut -f 3,3 -d ' ' | cut -f 1,1 -d /`

  echo "$IP   $SOMETHING"  >> /etc/hosts
  salt '*' cmd.run "echo $IP   $SOMETHING  >> /etc/hosts"
fi

masterconf_done=`grep pillar_roots /etc/salt/master`
if [ -z "$masterconf_done" ]; then
  echo "adding trebuchet options to saltmaster conf"
  # note that we add 'test' module commands to peer_run in case you need
  # to do basic debugging
  ( cat <<EOF
pillar_roots:
  base:
    - /srv/pillars

peer_run:
  $SOMETHING:
    - deploy.*
    - test.*
EOF
  ) >> /etc/salt/master
fi

# install python redis bindings everywhere
python_redis_installed=`salt $SOMETHING cmd.run 'dpkg -l | grep "python-redis" ' | grep -v ${SOMETHING}`
if [ -z "$python_redis_installed" ]; then
  echo "installing python redis bindings everywhere"
  apt-get -y install python-redis

  # run on all minions
  salt -l debug '*' --timeout 60 cmd.run 'apt-get -y install python-redis'
fi

# install redis on the right host and set up its config
redis_installed=`salt $SOMETHING cmd.run 'dpkg -l | grep "redis-server" ' | grep -v ${SOMETHING}`
if [ -z "$redis_installed" ]; then
  echo "installing/configuring redis server"
  salt "$SOMETHING" --timeout 60 cmd.run "apt-get install -y redis-server"
  salt "$SOMETHING" --timeout 60 cmd.run "cat /etc/redis/redis.conf | sed -e 's/^bind/#bind/g;' > /etc/redis/redis.conf.new"
  salt "$SOMETHING" --timeout 60 cmd.run "mv /etc/redis/redis.conf.new /etc/redis/redis.conf"
  salt "$SOMETHING" --timeout 60 cmd.run "/etc/init.d/redis-server start"
  salt "$SOMETHING" --timeout 60 cmd.run "apt-get -y install sudo"
fi

# clone and patch trigger
trigger_cloned=`salt $SOMETHING cmd.run 'ls -d /root/trigger-tmp/trigger 2>/dev/null' | grep -v ${SOMETHING}`
if [ -z "$trigger_cloned" ]; then
  echo "cloning trigger"
  salt "$SOMETHING" cmd.run "mkdir /root/trigger-tmp; cd /root/trigger-tmp; git clone https://github.com/trebuchet-deploy/trigger.git"
  echo "patching trigger"
  ( cat <<'EOF'
--- a/trigger/drivers/trebuchet/local.py
+++ b/trigger/drivers/trebuchet/local.py
@@ -19,6 +19,8 @@ import trigger.drivers as drivers
 
 import redis
 
+import salt.version
+
 from datetime import datetime
 from trigger.drivers import SyncDriverError
 from trigger.drivers import LockDriverError
@@ -94,8 +96,17 @@ class SyncDriver(drivers.SyncDriver):
     def _checkout(self, args):
         # TODO (ryan-lane): Check return values from these commands
         repo_name = self.conf.config['deploy.repo-name']
+        if args.force:
+            # see https://github.com/saltstack/salt/issues/18317
+            _version_ = salt.version.SaltStackVersion(*salt.version.__version_info__)
+            if (_version_ >= "2014.7.3"):
+                runner_args = '[' + repo_name + ',' + str(args.force) + ']'
+            else:
+                runner_args = repo_name + ',' + str(args.force)
+        else:
+            runner_args = repo_name
         p = subprocess.Popen(['sudo','salt-call','-l','quiet','publish.runner',
-                              'deploy.checkout', repo_name+','+str(args.force)],
+                              'deploy.checkout', runner_args],
                              stdout=subprocess.PIPE)
         p.communicate()
 
@@ -206,9 +217,18 @@ class ServiceDriver(drivers.ServiceDriver):
 
     def restart(self, args):
         repo_name = self.conf.config['deploy.repo-name']
+        if args.batch:
+            # see https://github.com/saltstack/salt/issues/18317
+            _version_ = salt.version.SaltStackVersion(*salt.version.__version_info__)
+            if (_version_ >= "2014.7.3"):
+                runner_args = '[' + repo_name + ',' + str(args.batch) + ']'
+            else:
+                runner_args = repo_name +',' + str(args.batch)
+        else:
+           runner_args = repo_name
         p = subprocess.Popen(['sudo','salt-call','-l','quiet','--out=json',
                               'publish.runner','deploy.restart',
-                              repo_name+','+str(args.batch)],
+                              runner_args],
                              stdout=subprocess.PIPE)
         out = p.communicate()[0]
         ## Disabled until salt bug is fixed:
EOF
  ) > /root/local.py.patch
  salt-cp "$SOMETHING" /root/local.py.patch /root/local.py.patch
  salt "$SOMETHING" cmd.run '(cd /root/trigger-tmp/trigger/trigger/drivers/trebuchet/; patch < /root/local.py.patch)'
fi


python_git_installed=`salt $SOMETHING cmd.run "dpkg -l | grep 'python-git' " | grep -v ${SOMETHING}`
if [ -z "${python_git_installed}" ]; then
  echo "installing python-git and depenencies"
  salt "$SOMETHING" cmd.run 'apt-get -y install python-setuptools'

  # ok on trusty and jessie but not precise, steal a backport.
  command='grep 12.04 /etc/issue; if [ $? -eq 1 ]; then apt-get -y install python-git; else apt-get install git-core; apt-get -y install curl; curl -o "/root/python-git_0.3.2.RC1-1_all.deb" "http://apt.wikimedia.org/wikimedia/pool/universe/p/python-git/python-git_0.3.2.RC1-1_all.deb"; curl -o "/root/python-async_0.6.1-1~precise1_amd64.deb" "http://apt.wikimedia.org/wikimedia/pool/universe/p/python-async/python-async_0.6.1-1~precise1_amd64.deb"; curl -o "/root/python-gitdb_0.5.4-1~precise1_amd64.deb" "http://apt.wikimedia.org/wikimedia/pool/universe/p/python-gitdb/python-gitdb_0.5.4-1~precise1_amd64.deb"; curl -o "/root/python-smmap_0.8.2-1~precise1_all.deb" "http://apt.wikimedia.org/wikimedia/pool/universe/p/python-smmap/python-smmap_0.8.2-1~precise1_all.deb"; dpkg -i "/root/python-smmap_0.8.2-1~precise1_all.deb"; dpkg -i "/root/python-async_0.6.1-1~precise1_amd64.deb"; dpkg -i "/root/python-gitdb_0.5.4-1~precise1_amd64.deb"; dpkg -i "/root/python-git_0.3.2.RC1-1_all.deb"; fi'
  echo "command is" $command
  salt "$SOMETHING" --timeout 60 cmd.run "$command"
fi

# put config files in place
if [ ! -e /srv/pillars/top.sls ]; then
  echo "setting up pillars"
  mkdir -p /srv/pillars
  ( cat <<'EOF'
base:
  'deployment_server:true':
    - match: grain
    - deployment.repo_config
    - deployment.deployment_config
  'deployment_target:*':
    - match: grain
    - deployment.repo_config
    - deployment.deployment_config
EOF
  ) > /srv/pillars/top.sls
fi

if [ ! -e /srv/pillars/deployment/deployment_config.sls ]; then
  echo "setting up more pillars"
  mkdir -p /srv/pillars/deployment
 ( cat <<EOF
{"deployment_config": {"parent_dir": "/srv/deployment", "redis": {"db": 0, "host": "$SOMETHING", "port": 6379}, "servers": {"default": "$SOMETHING"}}}
EOF
  ) > /srv/pillars/deployment/deployment_config.sls
  ( cat <<'EOF'
  {"repo_config": {"test/testrepo": {"checkout_submodules": true, "service_name": "puppet"}}}
EOF
  ) > /srv/pillars/deployment/repo_config.sls
fi

# set grains on minions
echo "setting grains on minions"
salt '*' grains.setval 'deployment_target' 'test/testrepo'
salt '*' grains.setval 'trebuchet_master' "$SOMETHING"
salt '*' grains.setval 'site' "default"
# don't really want the deployment server to be a deployment target I guess
salt "$SOMETHING" grains.delval 'deployment_target' destructive=True
salt "$SOMETHING" grains.setval 'deployment_server' 'true'
salt "$SOMETHING" grains.setval 'deployment_repo_user' 'root'

# set up deploy_runner.conf on master, some versions of trebuchet need it
if [ ! -e "/etc/salt/deploy_runner.conf" ]; then
  echo "setting up deploy_runner.conf"
  ( cat <<'EOF'
deployment_repo_grains: {'test/testrepo': 'test/testrepo',}
EOF
  ) > /etc/salt/deploy_runner.conf
fi

# push out module to minions
echo "refreshing modules out to minions"
/etc/init.d/salt-master restart

# let master wake up
sleep 15
salt '*' test.ping

salt '*' saltutil.refresh_modules
salt '*' saltutil.sync_all
salt '*' cmd.run '/etc/init.d/salt-minion restart'
# wait for minions to wake up
sleep 5
salt '*' test.ping

echo "configuring repo for git deploy"
salt "$SOMETHING" deploy.deployment_server_init

# make test repo on deployment server
gitconfig_exists=`salt $SOMETHING cmd.run 'ls /root/.gitconfig 2>/dev/null' | grep -v ${SOMETHING}`
if [ -z "$gitconfig_exists" ]; then
  echo "setting up git config for root"
  # fix the 'stdin: not a tty' error
  salt "$SOMETHING" cmd.run 'grep -v mesg /root/.profile > /root/.profile.new; mv /root/.profile.new /root/.profile'
  # set up the config
  salt "$SOMETHING" cmd.run "bash -c 'HOME=/root git config --global user.name \"A. Tester\"'"
  salt "$SOMETHING" cmd.run "bash -c 'HOME=/root git config --global user.email atester@noreply.com'"
fi

testrepo_exists=`salt $SOMETHING cmd.run 'ls /srv/deployment/test/testrepo/myfile.txt 2>/dev/null' | grep -v ${SOMETHING}`
if [ -z $testrepo_exists ]; then
  echo "setting up initial test repo"
  salt "$SOMETHING" cmd.run "mkdir -p /srv/deployment/test/testrepo"
  salt "$SOMETHING" cmd.run "cd /srv/deployment/test/testrepo; git init"
  salt "$SOMETHING" cmd.run 'echo "bla bla" > /srv/deployment/test/testrepo/myfile.txt'
  salt "$SOMETHING" cmd.run 'git --git-dir=/srv/deployment/test/testrepo/.git --work-tree=/srv/deployment/test/testrepo add myfile.txt'
  salt "$SOMETHING" cmd.run "bash -c 'HOME=/root git --git-dir=/srv/deployment/test/testrepo/.git --work-tree=/srv/deployment/test/testrepo commit -m junk_for_testing'"
fi

# set up apache on deployment server
apache_installed=`salt $SOMETHING cmd.run 'dpkg -l | grep apache2' | grep -v ${SOMETHING}`
if [ -z "$apache_installed" ]; then
  echo "installing apache"
  salt "$SOMETHING" cmd.run "apt-get -y install apache2"
fi

apache_conf_done=`salt $SOMETHING cmd.run 'ls /etc/apache2/sites-available/deployment.conf 2>/dev/null' | grep -v ${SOMETHING}`
if [ -z "$apache_conf_done" ]; then
  echo "setting up apache config"
  ( cat <<EOF
<VirtualHost *:80>
 ServerName $SOMETHING
 ServerAdmin atester@noreply.com
 DocumentRoot /srv/deployment

 <Directory /srv/deployment>
 Options Indexes FollowSymLinks MultiViews
 AllowOverride None
 Order Deny,Allow
 Allow from all
 </Directory>

 LogLevel warn
 ErrorLog /var/log/apache2_error.log
 CustomLog /var/log/apache2_access.log combined
 ServerSignature Off
</VirtualHost>
EOF
  ) >> /root/apache_deployment_conf

  salt-cp "$SOMETHING" /root/apache_deployment_conf /root/apache_deployment_conf
  salt "$SOMETHING" cmd.run "cp /root/apache_deployment_conf /etc/apache2/sites-available/deployment.conf"
  salt "$SOMETHING" cmd.run "cd /etc/apache2/sites-enabled/; ln -s ../sites-available/deployment.conf ."
  salt "$SOMETHING" cmd.run "rm /etc/apache2/sites-enabled/000-default"

  main_conf_fixed=`salt $SOMETHING cmd.run 'egrep "^<Directory /srv" /etc/apache2/apache2.conf 2>/dev/null' | grep srv`
  if [ -z "$main_conf_fixed" ]; then
  ( cat <<'EOF'
<Directory /srv/>
        Options Indexes FollowSymLinks
        AllowOverride None
#        Require all granted
        Order deny,allow
        allow from all
</Directory>
EOF
  ) > /root/apache_additions
    salt-cp "$SOMETHING" /root/apache_additions /root/apache_additions
    salt "$SOMETHING" cmd.run "cat /root/apache_additions >> /etc/apache2/apache2.conf"
  fi
fi

# (re) start the services we need
salt "$SOMETHING" --timeout 60 cmd.run "/etc/init.d/apache2 restart"
salt "$SOMETHING" --timeout 60 cmd.run "/etc/init.d/redis-server restart"

# install trigger to the right place
trigger_installed=`salt $SOMETHING cmd.run 'ls -d /usr/share/pyshared/trigger 2>/dev/null | grep "trigger" ' | grep -v ${SOMETHING}`
if [ -z "$trigger_installed" ]; then
  echo "installing trigger"
  salt "$SOMETHING" cmd.run '(cd /root/trigger-tmp/trigger; python setup.py install)'
fi

echo "done!"

# fixmes: might be nice not to set the grains if already set
#         also maybe not re-export the modules etc if they are already showing up on minions
