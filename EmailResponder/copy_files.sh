#!/bin/bash

# Copyright (c) 2011, Psiphon Inc.
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

# This script should be used to copy the source files to the correct location, 
# with the correct permissions and content, on the mail responder server.
# Using this script will help avoid mistakes (such as not replacing mail.example.com
# with a real stats address).

EXPECTED_NUM_ARGS=1

if [ $# -ne $EXPECTED_NUM_ARGS ]; then
    echo "Usage: `basename $0` stats_mail_addr"
    exit 1
fi

STATS_MAIL_ADDR=$1

MAIL_HOME=/home/mail_responder

# The simple files: mail_process.py, sendmail.py, blacklist.py, mail_stats.py
sudo cp mail_process.py sendmail.py blacklist.py mail_stats.py $MAIL_HOME

# forward needs to be copied to .forward
sudo cp forward $MAIL_HOME/.forward

# settings.py needs to have a line replaced with the real stats address
sudo sed "s/RECIPIENT_ADDRESS = 'mail@example.com'/RECIPIENT_ADDRESS = '$STATS_MAIL_ADDR'/g" settings.py > settings.tmp 
sudo mv settings.tmp $MAIL_HOME/settings.py

# Fix ownership of the files
sudo chown mail_responder:mail_responder $MAIL_HOME/*

# Nuke the compiled Python files, just in case.
sudo rm $MAIL_HOME/*.pyc

exit 0
