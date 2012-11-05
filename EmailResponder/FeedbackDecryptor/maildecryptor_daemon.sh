#!/bin/bash

# Copyright (c) 2012, Psiphon Inc.
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

MAILDECRYPTOR_DIR="/maildecryptor"
MAILDECRYPTOR_USER="maildecryptor"

START=start
STOP=stop

if [ -z $1 ] ; then
  echo "Missing argument: $START|$STOP"
  exit 1
fi

if [ "$1" != "$START" -a "$1" != "$STOP" ] ; then
  echo "Bad argument; must be: $START|$STOP"
  exit 1
fi

sudo chmod 0444 $MAILDECRYPTOR_DIR/*
sudo chmod 0555 $MAILDECRYPTOR_DIR/maildecryptor_runner.py $MAILDECRYPTOR_DIR/maildecryptor_daemon.sh
sudo chmod 0400 $MAILDECRYPTOR_DIR/*.pem
sudo chmod 0400 $MAILDECRYPTOR_DIR/*.json
sudo chown $MAILDECRYPTOR_USER:$MAILDECRYPTOR_USER $MAILDECRYPTOR_DIR/*

if [ `stat --printf "%a" $MAILDECRYPTOR_DIR/*.pem` != "400" -o `stat --printf "%a" $MAILDECRYPTOR_DIR/*.json` != "400" ] ; then
  echo "Permissions on sensitive files are not sufficiently restricted"
  exit 1
fi

if [ "$1" = "$START" ] ; then
  ARGS="--start --background"
else
  ARGS="--stop"
fi

sudo start-stop-daemon $ARGS --user $MAILDECRYPTOR_USER --chuid $MAILDECRYPTOR_USER:$MAILDECRYPTOR_USER --chdir $MAILDECRYPTOR_DIR --startas $MAILDECRYPTOR_DIR/maildecryptor_runner.py

sleep 2
tail --lines=3 /var/log/syslog
