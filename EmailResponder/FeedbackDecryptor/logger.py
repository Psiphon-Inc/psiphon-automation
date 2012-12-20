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

'''
Our logging helpers. Note that some work will be required to make this work
properly on Windows.
'''

import os
import logging
import logging.handlers

_DEBUG = ('DEBUG' in os.environ) and os.environ['DEBUG']

_my_logger = logging.getLogger('MyLogger')
_my_logger.setLevel(logging.DEBUG if _DEBUG else logging.WARNING)
_my_logger.addHandler(logging.handlers.SysLogHandler(address='/dev/log'))


def debug_log(s):
    _my_logger.debug(s)


def log(s):
    _my_logger.critical(s)


def exception(s=''):
    _my_logger.exception(s)
