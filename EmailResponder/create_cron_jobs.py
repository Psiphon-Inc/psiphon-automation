#!/usr/bin/python
# -*- coding: utf-8 -*-

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

import argparse
import os
from crontab import CronTab


class CronCreator(object):
    def __init__(self, user, dir):
        self.tab = CronTab(user=user)
        self.dir = dir
        
    def go(self):
        self._maintenance_jobs()
        self._stats_jobs()
        self._blacklist_jobs()
        self.tab.write()
    
    @staticmethod
    def _make_daily(cron):
        cron.minute().on(0)
        cron.hour().on(0)
        
    def _stats_jobs(self):
        command = '/usr/bin/python %s' % os.path.join(self.dir, 'mail_stats.py')
        self.tab.remove_all(command)
        cron = self.tab.new(command=command)
        self._make_daily(cron)
        
    def _blacklist_jobs(self):
        command = '/usr/bin/python %s' % os.path.join(self.dir, 'blacklist.py --clear')
        self.tab.remove_all(command)
        cron = self.tab.new(command=command)
        self._make_daily(cron)
        
    def _maintenance_jobs(self):
        # Clears the postfix message queue
        command = "for i in `mailq|grep '@' |awk {'print $1'}|grep -v '@'`; do sudo postsuper -d $i ; done"
        self.tab.remove_all(command)
        cron = self.tab.new(command=command)
        self._make_daily(cron)

        # Restart postfix
        command = 'sudo /etc/init.d/postfix restart'
        self.tab.remove_all(command)
        cron = self.tab.new(command=command)
        self._make_daily(cron)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Interact with the blacklist table')
    parser.add_argument('--user', action='store', required=True, help="specifies which user's crontab to use") 
    parser.add_argument('--dir', action='store', required=True, help="specifies the location of the command files") 
    args = parser.parse_args()
    
    cron_creator = CronCreator(args.user, args.dir)
    cron_creator.go()
    
    