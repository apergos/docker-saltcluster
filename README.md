docker-saltcluster
==================

The saltcluster.py script facilitates the setup and running of a 
salt cluster in docker containers on a single host, intended for
use in a testing environment.

How to use:

all of the following should be done as root, except for
use/testing of the cluster.

* create the salt base image:
    cd salt
    docker build -rm -t ariel/salt:base .
    cd ..

* decide what branch or tag of salt you want to use in your test cluster:
  examples: v0.15.0 or e0961baedeeb8cf0e8683deac38c2f6404b4265a

* decide how many minions you want in your cluster.
  you could start with 1 for a small test or give 100 for a larger scale test

* create the cluster:
    python salt-cluster.py  --create --number number-of-minions --tag salt-tag-or-commit
    example: python salt-cluster.py  --create --number 1 --tag v0.15.0 --verbose

* start the cluster:
    python salt-cluster.py  --start --number number-of-minions --tag salt-tag-or-commit
    example: python salt-cluster.py  --start --tag v0.15.0 --verbose

* configure the cluster:
    python salt-cluster.py  --configure --number number-of-minions --tag salt-tag-or-commit
    example: python salt-cluster.py  --configure --tag v0.15.0 --verbose

* issue salt commands from the salt master by ssh-ing into the container:
    ./ssh-to-master.sh <tag-or-commit>
    (password: testing)
    salt '*' test.ping
    
* when you are done testing, stop the cluster:
    python salt-cluster.py  --stop --count number-of-minions --tag salt-tag-or-commit
    example: python salt-cluster.py  --stop --tag v0.15.0 --verbose

* when you no longer need the containers with this salt branch or commit, delete the cluster:
    python salt-cluster.py  --delete --count number-of-minions --tag salt-tag-or-commit
    example: python salt-cluster.py  --delete --tag v0.15.0 --verbose

Note that the first three steps can be done as one:
    example: python salt-cluster.py  -c -s -C  --number 1 --tag v0.15.0
    This will create, start and then configure the cluster.

For complete usage information give the command
python salt-cluster.py --help

License information: copyright Ariel T. Glenn 2013-2014, GPL v2 or later.
For details see the file COPYING in this directory.
