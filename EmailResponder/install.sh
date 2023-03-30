#!/bin/bash

# Copyright (c) 2015, Psiphon Inc.
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

NORMAL_USER=ubuntu
MAIL_USER=mail_responder
MAIL_HOME=/home/mail_responder

grep '!!!' settings.py > /dev/null
if [ "$?" -ne "1" ]; then
    echo "You must edit settings.py before attempting to install"
    exit 1
fi

# We're installing poetry as root, globally so that all users have access to it
sudo pip install --upgrade poetry

# Our poetry.toml has the virtualenvs.create directive set to false, which makes it
# install packages globally using pip rather than in a venv. This allows it to be used by
# all users (ubuntu, root, mail_responder, syslog, etc.).
# (An alternative approach could be to use virtualenvs.path and set it to a path that's
# writable by all users. But that seems more dangerous.)
sudo poetry install

# Put the source files where they need to be.
echo "Copying source files..."

# Copy the simple files
sudo cp blacklist.py log_processor.py mail_direct.py mail_process.py mail_stats.py \
        aws_helpers.py sendmail.py settings.py conf_pull.py postfix_queue_check.pl \
        ../Automation/psi_ops_s3.py helo_access sender_access header_checks logger.py \
        client_tls_policy poetry.toml pyproject.toml poetry.lock \
        $MAIL_HOME

# forward needs to be copied to .forward
sed "s|\(.*\)%MAIL_HOME%\(.*\)|\1$MAIL_HOME\2|g" forward > forward.tmp
sudo mv forward.tmp $MAIL_HOME/.forward

# Fix ownership of the files
sudo chown mail_responder:mail_responder $MAIL_HOME/* $MAIL_HOME/.forward

# Make the files readable by anyone (e.g., other users will use them for cron jobs)
sudo chmod a+r  $MAIL_HOME/* $MAIL_HOME/.forward

# Make log_processor.py executable by anyone (e.g., by rsyslog)
sudo chmod a+x  $MAIL_HOME/log_processor.py

# Process the map files
cd $MAIL_HOME; sudo postmap helo_access sender_access postfix_address_maps client_tls_policy; cd -

# Copy the system/service config files.
echo "Copying system config files..."
sed "s|\(.*\)%MAIL_HOME%\(.*\)|\1$MAIL_HOME\2|g" psiphon-log-rotate.conf > psiphon-log-rotate.tmp
sudo mv psiphon-log-rotate.tmp /etc/logrotate.d/psiphon-log-rotate.conf
sudo chown root:root /etc/logrotate.d/psiphon-log-rotate.conf
sudo chmod 644 /etc/logrotate.d/psiphon-log-rotate.conf
sudo service logrotate restart
sed "s|\(.*\)%MAIL_HOME%\(.*\)|\1$MAIL_HOME\2|g" 20-psiphon-logging.conf > 20-psiphon-logging.tmp
sudo mv 20-psiphon-logging.tmp /etc/rsyslog.d/20-psiphon-logging.conf
sudo chown root:root /etc/rsyslog.d/20-psiphon-logging.conf
sudo chmod 644 /etc/rsyslog.d/20-psiphon-logging.conf
sudo service rsyslog restart

sudo cp 50_scores.cf /etc/spamassassin/
sudo sa-update
sudo service spamassassin restart

# Create the cron jobs.
echo "Creating cron jobs..."
sudo poetry run python3 create_cron_jobs.py --mailuser $MAIL_USER --normaluser $NORMAL_USER --dir $MAIL_HOME

if [ "$?" -ne "0" ]; then
    echo "Cron creation failed!"
    exit 1
fi

cd $MAIL_HOME
# Do an initial config pull
sudo -u$MAIL_USER poetry run python3 conf_pull.py
cd -

echo "Done"
