Once you have a docker salt cluster set up, you can put this script
over on the salt master, run it giving the docker container id of
the host you want to be the deployment server for trebuchet, and
it will set up the deployment server, configuration on the master,
and grains on all other hosts for use with a test repo which it
will also set up and initialize.

For more information on trebuchet and trigger, see:

https://github.com/trebuchet-deploy/trebuchet
https://github.com/trebuchet-deploy/trigger
