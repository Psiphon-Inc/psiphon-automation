#!/bin/bash

# "python ./load.py" shouldn't run for longer than 60 minutes
max_seconds=3600
process="$(pgrep -f "python ./load.py")"
if [[ -n "$process" ]]; then
  seconds=$(echo "$(date +%s) - $(stat -c %X /proc/$process)" | bc)
  if [[ "$seconds" -ge "$max_seconds" ]]; then
    kill "$process"
  fi
fi

lockfile="/tmp/psi_load_job.lock"

if [ -f "$lockfile" ] ; then
  echo "Lockfile exists, aborting."
  exit 1
fi

touch $lockfile

hg pull && hg up

ulimit -n 5000

python ./load.py

rm $lockfile

