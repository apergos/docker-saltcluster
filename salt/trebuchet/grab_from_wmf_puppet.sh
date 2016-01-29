#!/bin/bash

# grab the deployment files from the wmf puppet repo and stash them
# locally so the user can put them over onto the salt master

mkdir -p gitdeploy-tmp
mkdir -p gitdeploy-final
# clone the whole puppet repo
(cd gitdeploy-tmp; git clone --depth 1 https://gerrit.wikimedia.org/r/p/operations/puppet)
# grab the files we want: runners, modules, returners, git-deploy
rm -rf gitdeploy-tmp/puppet/modules/deployment/files/states
cp -a gitdeploy-tmp/puppet/modules/deployment/files/* gitdeploy-final/
rm -rf gitdeploy-tmp/

echo "Now run scp-trebuchet-to-master.sh <mastertag>"
echo "This will copy the newly created trebuchet files into the"
echo "proper staging area on the salt master."
echo
echo "After this you can run install_trebuchet.sh to complete installation."
