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

MAILDECRYPTOR_USER="maildecryptor"

if [ ! -f ./maildecryptor.conf ]; then
  echo "This script must be run from the source directory."
  exit 1
fi

echo "You must already have created the user $MAILDECRYPTOR_USER, otherwise this script will fail. See the README for details."
echo ""

sed "s|fill-in-with-path-to-source|\"`pwd`\"|" maildecryptor.conf > maildecryptor.conf.configured

sudo cp maildecryptor.conf.configured /etc/init/maildecryptor.conf

sudo chmod 0400 *.pem conf.json
sudo chown $MAILDECRYPTOR_USER:$MAILDECRYPTOR_USER *.pem conf.json

echo "Done. To start the daemon execute:"
echo " > sudo start maildecryptor"
echo ""
