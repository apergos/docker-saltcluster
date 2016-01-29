#!/bin/bash

# grab the deployment files from the wmf puppet repo and stash them
# locally so the user can put them over onto the deployment server.

git clone --depth 1 https://gerrit.wikimedia.org/r/p/operations/software/deployment/trebuchet-trigger.git trigger

echo "Now run scp-trigger-to-depserver.sh <hosttag>"
echo "This will copy the newly cloned trigger repo into the"
echo "proper staging area on the deployment server."
echo
echo "After this you can run install_trebuchet.sh to complete installation."
