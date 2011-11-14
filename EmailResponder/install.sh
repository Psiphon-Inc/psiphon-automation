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

MAIL_USER=mail_responder
NORMAL_USER=ubuntu
MAIL_FILE_DIR=/home/mail_responder


# Put the source files where they need to be. Pass arguments on.
echo "Copying source files..."
sh ./copy_files.sh $*

if [ "$?" -ne "0" ]; then
    echo "Copy failed!"
    exit 1
fi

# Copy the system/service config files.
echo "Copying system config files..."
sudo cp psiphon-log-rotate.conf /etc/logrotate.d/
sudo cp 20-psiphon-logging.conf /etc/rsyslog.d/
sudo reload rsyslog

# Create the cron jobs.
echo "Creating cron jobs..."
sudo python create_cron_jobs.py --mailuser $MAIL_USER --normaluser $NORMAL_USER --dir $MAIL_FILE_DIR

if [ "$?" -ne "0" ]; then
    echo "Cron creation failed!"
    exit 1
fi

echo "Done"
