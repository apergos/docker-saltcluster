Once you have a docker salt cluster set up, you can put this script
over on the salt master, run it giving the docker container id of
the host you want to be the deployment server for trebuchet, and
it will set up the deployment server, configuration on the master,
and grains on all other hosts for use with a test repo which it
will also set up and initialize.

If you want to use the wmf version of trebuchet you can run
grab_from_wmf_puppet.sh which will grab the right files
from the puppet repo for you, and then run
scp-trebuchet-to-master.sh <master-tag> to copy them
over to the right location.

If you want to use the wmf version of trigger you can run
grab_from_wmf_repo.sh which will clone the wmf repo
for you, and then run
scp-trigger-to-depserver.sh <depserver-tag> to copy them
over to the right location.

For more information on trebuchet and trigger, see:

https://github.com/trebuchet-deploy/trebuchet
https://github.com/trebuchet-deploy/trigger
