#!/bin/bash

lockfile="/tmp/psi_load_job.lock"

if [ -f "$lockfile" ] ; then
  echo "Lockfile exists, aborting."
  exit 1
fi

touch $lockfile

#hg pull && hg up

ulimit -n 4000

python ./load.py

rm $lockfile

