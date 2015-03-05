#!/bin/bash

python generate_dockerfile.py -d lucid > Dockerfile
docker build --rm -t ariel/salt:lucidbase .

python generate_dockerfile.py -d precise > Dockerfile
docker build --rm -t ariel/salt:precisebase .

python generate_dockerfile.py -d trusty > Dockerfile
docker build --rm -t ariel/salt:trustybase .

python generate_dockerfile.py -d jessie > Dockerfile
docker build --rm -t ariel/salt:jessiebase .

