#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2014, Psiphon Inc.
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

'''
Creates the cron jobs required for operation of the mail responder.
'''

import argparse
import os
from crontab import CronTab


class CronCreator(object):
    def __init__(self, normal_user, mail_user, dir):
        self.normal_tab = CronTab(user=normal_user)
        self.mail_tab = CronTab(user=mail_user)
        self.dir = dir

    def go(self):
        self._maintenance_jobs()
        self._blacklist_jobs()
        self._instance_initialization_jobs()
        self._conf_update()
        self.normal_tab.write()
        self.mail_tab.write()

    @staticmethod
    def _make_daily(cron):
        cron.minute.on(0)
        cron.hour.on(0)

    @staticmethod
    def _delete_commands(cron, command_id):
        '''
        Delete any pre-existing cron jobs with the given `command_id` as comment.
        '''
        cron.remove_all(comment=command_id)

    def _blacklist_jobs(self):
        command_id = 'Psiphon: blacklist clear'
        command = '/usr/bin/python %s' % os.path.join(self.dir, 'blacklist.py --clear-adhoc')

        self._delete_commands(self.mail_tab, command_id)

        cron = self.mail_tab.new(command=command, comment=command_id)
        self._make_daily(cron)

    def _maintenance_jobs(self):
        command_id = 'Psiphon: put CloudWatch system metrics'
        command = "cd /home/mail_responder && /usr/bin/perl ./mon-put-instance-data.pl --disk-path=/ --mem-util --mem-used --mem-avail --swap-util --swap-used --disk-space-util --disk-space-used --disk-space-avail --from-cron --auto-scaling --aws-access-key-id=`/bin/sed -n 's/aws_access_key_id = \\(.*\\)/\\1/p' /etc/boto.cfg` --aws-secret-key=`/bin/sed -n 's/aws_secret_access_key = \\(.*\\)/\\1/p' /etc/boto.cfg`"

        self._delete_commands(self.normal_tab, command_id)

        cron = self.normal_tab.new(command=command, comment=command_id)
        cron.minute.every(5)

        # Update source
        # It's inefficient to do hg incoming followed by hg pull, since there
        # will be two downloads done. But our release branch doesn't change
        # enough for this to be a big deal.
        # More efficient/complex methods here: http://stackoverflow.com/questions/8922787/mercurial-check-whether-last-pull-update-introduced-changes
        branch = 'default'

        command_id = 'Psiphon: pull and update code'
        command = "cd /home/ubuntu/psiphon-circumvention-system/EmailResponder && /usr/bin/hg incoming && /usr/bin/hg pull && /usr/bin/hg up %s && /bin/sh install.sh &>/dev/null" % (branch,)

        self._delete_commands(self.normal_tab, command_id)

        # Do it every hour...
        cron = self.normal_tab.new(command=command, comment=command_id)
        cron.minute.on(0)
        # ...and on reboot
        cron = self.normal_tab.new(command=command, comment=command_id)
        cron.every_reboot()

    def _conf_update(self):
        command_id = 'Pull config'
        command = 'cd /home/mail_responder && /usr/bin/env python conf_pull.py --cron'

        self._delete_commands(self.mail_tab, command_id)

        # Do it every hour...
        cron = self.mail_tab.new(command=command, comment=command_id)
        cron.minute.on(0)
        # And on reboot
        cron = self.mail_tab.new(command=command, comment=command_id)
        cron.every_reboot()

        # Pulling config may have changed Postfix config, so we need to reload it
        command_id = 'Psiphon: reload Postfix config'
        command = 'cd /home/mail_responder && sudo /usr/sbin/postmap postfix_address_maps &>/dev/null; sudo /usr/sbin/postfix reload &>/dev/null'

        self._delete_commands(self.normal_tab, command_id)

        # Do it every hour...
        cron = self.normal_tab.new(command=command, comment=command_id)
        cron.minute.on(0)
        # And on reboot
        cron = self.normal_tab.new(command=command, comment=command_id)
        cron.every_reboot()

    def _instance_initialization_jobs(self):
        # If this directory isn't removed it will mess up metrics reporting
        command_id = 'Psiphon: delete cached instance info'
        command = 'sudo rm -rf /var/tmp/aws-mon/'

        self._delete_commands(self.normal_tab, command_id)

        cron = self.normal_tab.new(command=command, comment=command_id)
        cron.every_reboot()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create mail responder cron jobs')
    parser.add_argument('--mailuser', action='store', required=True, help="the name of the reduced-privilege mail user")
    parser.add_argument('--normaluser', action='store', required=True, help="the name of a normal (sudoer) user")
    parser.add_argument('--dir', action='store', required=True, help="specifies the location of the command files")
    args = parser.parse_args()

    cron_creator = CronCreator(args.normaluser, args.mailuser, args.dir)
    cron_creator.go()
