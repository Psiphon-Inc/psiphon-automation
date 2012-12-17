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


import os
try:
    import syslog
except:
    pass

_DEBUG = ('DEBUG' in os.environ) and os.environ['DEBUG']


def debug_log(s):
    if not _DEBUG:
        return
    log(s)


def log(s):
    if 'syslog' in globals():
        syslog.syslog(syslog.LOG_ERR, s)
        if _DEBUG:
            print(s)
    else:
        if _DEBUG:
            print(s)
