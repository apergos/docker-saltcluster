Redis returner setup

You should have expect installed for these setup scripts to work.

First build the image:
bash build-image.sh

Run a container from the image:
docker run  ariel/salt:redis

Create, start and configure your salt cluster, then run
./fixup-for-redis.sh

It will prompt you to select the right master if you have more
than one salt cluster running.
It will then configure the salt master and the minions for
the reis returner and test the returner.  If all goes well
you should see a pile of returner output back from the
last command it runs.

This is still in progress; it seems to work reliably enough with 0.17.5
on precise and with 2014.1.10 on trusty.
