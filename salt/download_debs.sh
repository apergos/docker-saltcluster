#!/bin/bash

mkdir -p debs/
wget -P debs/ "http://people.wikimedia.org/~ariel/salt/debs/index.txt"
wget -P debs/ -i debs/index.txt -B "http://people.wikimedia.org/~ariel/salt/debs/"






