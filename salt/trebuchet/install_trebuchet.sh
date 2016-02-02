#!/bin/bash

# Note: for wmf testing purposes use a jessie host for the deployment server

check_exists(){
    name=$1
    type=$2
    IP=$3
    case $type in
	'dir')
	    command="ls -d $name"
	    ;;
	'file')
	    command="ls $name"
	    ;;
	'pkg')
	    command="dpkg -l | grep $name"
	    ;;
	*)
	    echo "Unknown existence check $name $type"
	    exit 1
	    ;;
    esac
    command="$command 2>/dev/null"
    result=`salt $IP cmd.run "$command" | grep -v $IP`
    if [ ! -z "$result" ]; then
	return 1
    else
	return 0
    fi
}    

check_running_on_master(){
    # check that we are on the salt master
    is_master_running=`pgrep salt-master`
    if [ -z "$is_master_running" ]; then
      echo "This script needs to be run on the salt master; please"
      echo "be sure you are on the right host and that the"
      echo "salt master is running."
      exit 1
    fi
}

check_args(){
    # check that we've been given the hostname of the redis/deploy server
    if [ -z "$1" ]; then
      echo "Usage: $0 hostname"
      echo "where hostname is the name of the minion to be used as the"
      echo "development server and also the redis server."
      exit 1
    fi
    DEPSERVER="$1"
}

check_depserver_responsive(){
    host="$1"
    salt "$host" test.ping | grep "$host" || (echo "$host not responsive to test.ping, exiting" ; return 1)
}

clone_trebuchet(){
  mkdir -p /root/treb-tmp
  cd /root/treb-tmp

  # if the directory is already there, we assume user prepopulated it
  # with the script provided
  if [ ! -e /root/treb-tmp/trebuchet ]; then
      echo "cloning the github trebuchet repo"
      git clone https://github.com/trebuchet-deploy/trebuchet.git
  fi
}

patch_trebuchet() {
  echo "patching trebuchet on master"
  mkdir -p /srv/salt/_returners /srv/salt/_modules /srv/runners

  cd /root/treb-tmp/trebuchet
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
  needspatch=`grep 'deploy.checkout-submodules true' modules/deploy.py`
  if [ -z "$needspatch" ]; then
    echo "patching trebuchet"
    (cd modules; patch < /root/deploy.py.patch)
  fi
}

setup_trebuchet(){
  echo "setting up trebuchet on master"
  cd /root/treb-tmp
  cd trebuchet
  cp runners/deploy.py /srv/runners/
  cp returners/deploy_redis.py /srv/salt/_returners/
  cp modules/deploy.py /srv/salt/_modules/
}

add_deployserver_ip_on_cluster(){
  echo "adding deploy server ip to /etc/hosts on all hosts"

  output=`salt $DEPSERVER cmd.run 'ip -4 addr show dev eth0 | grep inet'`
  IP=`echo $output | cut -f 3,3 -d ' ' | cut -f 1,1 -d /`

  echo "$IP   $DEPSERVER"  >> /etc/hosts
  salt '*' cmd.run "echo $IP   $DEPSERVER  >> /etc/hosts"
}

add_trebuchet_opts_saltmaster(){
  echo "adding trebuchet options to saltmaster conf"
  # note that we add 'test' module commands to peer_run in case you need
  # to do basic debugging
  ( cat <<EOF
pillar_roots:
  base:
    - /srv/pillars

peer_run:
  $DEPSERVER:
    - deploy.*
    - test.*
EOF
  ) >> /etc/salt/master
}

install_pyredis_bindings(){
  echo "installing python redis bindings everywhere"
  apt-get -y install python-redis

  # run on all minions
  salt -l debug '*' --timeout 60 cmd.run 'apt-get -y install python-redis'
}

install_redis_server(){
  echo "installing/configuring redis server"
  salt "$DEPSERVER" --timeout 60 cmd.run "apt-get install -y redis-server"
  salt "$DEPSERVER" --timeout 60 cmd.run "cat /etc/redis/redis.conf | sed -e 's/^bind/#bind/g;' > /etc/redis/redis.conf.new"
  salt "$DEPSERVER" --timeout 60 cmd.run "mv /etc/redis/redis.conf.new /etc/redis/redis.conf"
  salt "$DEPSERVER" --timeout 60 cmd.run "/etc/init.d/redis-server start"
  salt "$DEPSERVER" --timeout 60 cmd.run "apt-get -y install sudo"
}

clone_patch_trigger(){
  echo "cloning trigger"
  salt "$DEPSERVER" cmd.run "mkdir -p /root/trigger-tmp"
  salt "$DEPSERVER" cmd.run "cd /root/trigger-tmp; git clone https://github.com/trebuchet-deploy/trigger.git"
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
  patchdone=`salt "$DEPSERVER" cmd.run 'grep saltstack/salt/issues/18317 /root/trigger-tmp/trigger/drivers/trebuchet/local.py'`
  if [ -z "$patchdone" ]; then
      echo "patching trigger"
      salt-cp "$DEPSERVER" /root/local.py.patch /root/local.py.patch
      salt "$DEPSERVER" cmd.run '(cd /root/trigger-tmp/trigger/trigger/drivers/trebuchet/; patch < /root/local.py.patch)'
  fi
}

install_pygit(){
  echo "installing python-git and depenencies"
  salt "$DEPSERVER" cmd.run 'apt-get -y install python-setuptools'

  # ok on trusty and jessie but not precise, steal a backport.
  command='grep 12.04 /etc/issue; if [ $? -eq 1 ]; then apt-get -y install python-git; else apt-get install git-core; apt-get -y install curl; curl -o "/root/python-git_0.3.2.RC1-1_all.deb" "http://apt.wikimedia.org/wikimedia/pool/universe/p/python-git/python-git_0.3.2.RC1-1_all.deb"; curl -o "/root/python-async_0.6.1-1~precise1_amd64.deb" "http://apt.wikimedia.org/wikimedia/pool/universe/p/python-async/python-async_0.6.1-1~precise1_amd64.deb"; curl -o "/root/python-gitdb_0.5.4-1~precise1_amd64.deb" "http://apt.wikimedia.org/wikimedia/pool/universe/p/python-gitdb/python-gitdb_0.5.4-1~precise1_amd64.deb"; curl -o "/root/python-smmap_0.8.2-1~precise1_all.deb" "http://apt.wikimedia.org/wikimedia/pool/universe/p/python-smmap/python-smmap_0.8.2-1~precise1_all.deb"; dpkg -i "/root/python-smmap_0.8.2-1~precise1_all.deb"; dpkg -i "/root/python-async_0.6.1-1~precise1_amd64.deb"; dpkg -i "/root/python-gitdb_0.5.4-1~precise1_amd64.deb"; dpkg -i "/root/python-git_0.3.2.RC1-1_all.deb"; fi'
  echo "command is" $command
  salt "$DEPSERVER" --timeout 60 cmd.run "$command"
}

setup_pillars(){
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
}

setup_more_pillars(){
  echo "setting up more pillars"
  mkdir -p /srv/pillars/deployment
 ( cat <<EOF
{"deployment_config": {"parent_dir": "/srv/deployment", "redis": {"db": 0, "host": "$DEPSERVER", "port": 6379}, "servers": {"default": "$DEPSERVER"}}}
EOF
  ) > /srv/pillars/deployment/deployment_config.sls
  ( cat <<'EOF'
  {"repo_config": {"test/testrepo": {"checkout_submodules": true, "service_name": "puppet"}}}
EOF
  ) > /srv/pillars/deployment/repo_config.sls
}

setup_grains(){
  # set grains on minions
  echo "setting grains on minions"
  salt '*' grains.setval 'deployment_target' 'test/testrepo'
  salt '*' grains.setval 'trebuchet_master' "$DEPSERVER"
  salt '*' grains.setval 'site' "default"
  # don't really want the deployment server to be a deployment target I guess
  salt "$DEPSERVER" grains.delval 'deployment_target' destructive=True
  salt "$DEPSERVER" grains.setval 'deployment_server' 'true'
  salt "$DEPSERVER" grains.setval 'deployment_repo_user' 'root'
}

setup_deploy_runner_conf(){
  # set up deploy_runner.conf on master, some versions of trebuchet need it
  echo "setting up deploy_runner.conf"
  ( cat <<'EOF'
deployment_repo_grains: {'test/testrepo': 'test/testrepo',}
EOF
  ) > /etc/salt/deploy_runner.conf
}

refresh_modules(){
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
}

setup_gitconfig(){
  echo "setting up git config for root"
  # fix the 'stdin: not a tty' error
  salt "$DEPSERVER" cmd.run 'grep -v mesg /root/.profile > /root/.profile.new; mv /root/.profile.new /root/.profile'
  # set up the config
  salt "$DEPSERVER" cmd.run "bash -c 'HOME=/root git config --global user.name \"A. Tester\"'"
  salt "$DEPSERVER" cmd.run "bash -c 'HOME=/root git config --global user.email atester@noreply.com'"
}

setup_test_repo(){
  echo "setting up initial test repo"
  salt "$DEPSERVER" cmd.run "mkdir -p /srv/deployment/test/testrepo"
  salt "$DEPSERVER" cmd.run "cd /srv/deployment/test/testrepo; git init"
  salt "$DEPSERVER" cmd.run 'echo "bla bla" > /srv/deployment/test/testrepo/myfile.txt'
  salt "$DEPSERVER" cmd.run 'git --git-dir=/srv/deployment/test/testrepo/.git --work-tree=/srv/deployment/test/testrepo add myfile.txt'
  salt "$DEPSERVER" cmd.run "bash -c 'HOME=/root git --git-dir=/srv/deployment/test/testrepo/.git --work-tree=/srv/deployment/test/testrepo commit -m junk_for_testing'"
}

install_apache(){
  echo "installing apache on deployment server"
  salt "$DEPSERVER" cmd.run "apt-get -y install apache2"
}

setup_apache_config(){
  echo "setting up apache config"
  ( cat <<EOF
<VirtualHost *:80>
 ServerName $DEPSERVER
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

  salt-cp "$DEPSERVER" /root/apache_deployment_conf /root/apache_deployment_conf
  salt "$DEPSERVER" cmd.run "cp /root/apache_deployment_conf /etc/apache2/sites-available/deployment.conf"
  salt "$DEPSERVER" cmd.run "cd /etc/apache2/sites-enabled/; ln -s ../sites-available/deployment.conf ."
  salt "$DEPSERVER" cmd.run "rm /etc/apache2/sites-enabled/000-default"

  main_conf_fixed=`salt $DEPSERVER cmd.run 'egrep "^<Directory /srv" /etc/apache2/apache2.conf 2>/dev/null' | grep srv`
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
    salt-cp "$DEPSERVER" /root/apache_additions /root/apache_additions
    salt "$DEPSERVER" cmd.run "cat /root/apache_additions >> /etc/apache2/apache2.conf"
  fi
}

restart_apache_redis(){
  # (re) start the services we need
  salt "$DEPSERVER" --timeout 60 cmd.run "/etc/init.d/apache2 restart"
  salt "$DEPSERVER" --timeout 60 cmd.run "/etc/init.d/redis-server restart"
}

install_trigger(){
  echo "installing trigger on deployment server"
  salt "$DEPSERVER" cmd.run '(cd /root/trigger-tmp/trigger; python setup.py install)'
}

#########

check_running_on_master
check_args "$1"
check_depserver_responsive $DEPSERVER || exit 1
[ ! -e "/root/treb-tmp/trebuchet" ] && clone_trebuchet
patch_trebuchet
setup_trebuchet
grep $DEPSERVER /etc/hosts  > /dev/null || add_deployserver_ip_on_cluster
grep pillar_roots /etc/salt/master > /dev/null || add_trebuchet_opts_saltmaster
check_exists "python-redis" "pkg" "$DEPSERVER" && install_pyredis_bindings
check_exists "redis-server" "pkg" "$DEPSERVER" && install_redis_server
check_exists "/root/trigger-tmp/trigger" "dir" "$DEPSERVER" && clone_patch_trigger
check_exists "python-git" "pkg" "$DEPSERVER" && install_pygit
[ ! -e /srv/pillars/top.sls ] && setup_pillars
[ ! -e /srv/pillars/deployment/deployment_config.sls ] && setup_more_pillars
setup_grains
[ ! -e "/etc/salt/deploy_runner.conf" ] && setup_deploy_runner_conf
refresh_modules
echo "configuring repo for git deploy"; salt "$DEPSERVER" deploy.deployment_server_init
check_exists "/root/.gitconfig" "file" "$DEPSERVER" && setup_gitconfig
check_exists "/srv/deployment/test/testrepo/myfile.txt" "file" "$DEPSERVER" && setup_test_repo
check_exists "apache2" "pkg" "$DEPSERVER" && install_apache
check_exists "/etc/apache2/sites-available/deployment.conf" "file" "$DEPSERVER" && setup_apache_config
restart_apache_redis
check_exists "/usr/share/pyshared/trigger" "dir" "$DEPSERVER" && install_trigger

echo "done!"

# fixmes: might be nice not to set the grains if already set
# also maybe not re-export the modules etc if they are already showing up on minions
