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

This is still in progress; it seems to work reliably enugh with 0.17.5
on precise, it will of course be broken in part on lucid because
lucid's py-redis client does not support lpush, which the salt redis
returner uses, and 2014.1.10 on trusty has issues with running
salt commands right after the master restart.  I guess this probably
has to do with the minion re-auth, and will mean I need to play
with config settings for the minion and/or the master.
