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

MAILDECRYPTOR_DIR="/opt/psiphon/maildecryptor"
MAILDECRYPTOR_USER="maildecryptor"

echo "You must already have created the user $MAILDECRYPTOR_USER, otherwise this script will fail. See the README for details."
echo ""

sudo cp maildecryptor.conf /etc/init

sudo mkdir -p $MAILDECRYPTOR_DIR
sudo cp * $MAILDECRYPTOR_DIR

sudo chmod 0444 $MAILDECRYPTOR_DIR/*
sudo chmod 0555 $MAILDECRYPTOR_DIR/maildecryptor_runner.py
sudo chmod 0400 $MAILDECRYPTOR_DIR/*.pem
sudo chmod 0400 $MAILDECRYPTOR_DIR/*.json
sudo chown $MAILDECRYPTOR_USER:$MAILDECRYPTOR_USER $MAILDECRYPTOR_DIR/*

echo "Done. To start the daemon execute:"
echo " > sudo start maildecryptor"
