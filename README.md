docker-saltcluster
==================

The saltcluster.py script facilitates the setup and running of a 
salt cluster in docker containers on a single host, intended for
use in a testing environment.

NOTE: This has been tested (only) on Fedora 20 with docker 0.7.0,
0.7.5 and 0.7.6.

How to use:

all of the following should be done as root, except for
use/testing of the cluster.

* grab all the debs we have available and that you might need for
  salt for your platforms:
    cd salt
    bash ./download_debs.sh

  (supported platforms are lucid, precise, trusty
  with 0.17.1, 0.17.5, 2014.1.10; other versions can be added if
  you either send me email with pointers to the packages or
  download them yourself and put them into the staging area 'debs')

* create the salt base images:
    cd salt
    ./build-images.sh
    cd ..

* decide what branches, tags, or package versions of salt you want
  to use in your test cluster; examples:
  v0.15.0 or e0961baedeeb8cf0e8683deac38c2f6404b4265a for git
  0.17.5+ds-1_all for deb

* decide how many minions you want of each version in your cluster.
  you could start with 1 minion total for a small test or 100 for a larger scale test

* create the cluster:
    python salt-cluster.py  --create \
        --miniontags number-of-minions:ubuntuversion:gitordebversion:gitordeb,... \
        --mastertag ubuntuversion:gitordebversion:gitordeb
    example: python salt-cluster.py  --create --miniontags 1:precise:v0.17.1:git --mastertag precise:v0.17.1:git --verbose

* start the cluster:
    python salt-cluster.py  --start --miniontags tagspec --mastertag tagspec
    example: python salt-cluster.py  --start --miniontags 1:precise:v0.17.1:git --mastertag precise:v0.17.1:git --verbose

* configure the cluster:
    python salt-cluster.py  --configure --miniontags tagspec --mastertag tagspec
    example: python salt-cluster.py  --configure --miniontags 1:precise:v0.17.1:git --mastertag precise:v0.17.1:git --verbose

* issue salt commands from the salt master by ssh-ing into the container:
    ./ssh-to-master.sh <tag-or-commit>  <-- FIXME
    (password: testing)
    salt '*' test.ping
    
* when you are done testing, stop the cluster:
    python salt-cluster.py  --stop --miniontags tagspec --mastertag tagspec
    example: python salt-cluster.py  --stop --miniontags 1:precise:v0.17.1:git --mastertag precise:v0.17.1:git --verbose

* when you no longer need the containers with this salt branch or commit, delete the cluster:
    python salt-cluster.py  --delete --miniontags tagspec --mastertag tagspec
    example: python salt-cluster.py  --delete --miniontags 1:precise:v0.17.1:git --mastertag precise:v0.17.1:git --verbose

* when you are done with the base images too, toss them by
    cd salt
    ./rm-images.sh

Note that the first three steps can be done as one:
    example: python salt-cluster.py  -c -s -C  --miniontags 1:precise:v0.17.1:git --mastertag precise:v0.17.1:git
    This will create, start and then configure the cluster.

It is a good idea, if you are going to have multiple clusters around at the same
time, to specify a distinct base name for the master and the minions of that
cluster; this can be done via the --master and --minion arguments. For more
information information on this and other options, give the command

python salt-cluster.py --help

License information: copyright Ariel T. Glenn 2013-2014, GPL v2 or later.
For details see the file COPYING in this directory.
