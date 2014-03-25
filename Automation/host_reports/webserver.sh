#!/bin/bash

if [ "$1" == "start" ]; then
  ulimit -n 4000
  twistd --nodaemon web --port=8000 --path=.
elif [ "$1" == "stop" ]; then
  kill `cat twistd.pid`
else
  echo "Usage: supply either 'start' or 'stop' argument"
fi
