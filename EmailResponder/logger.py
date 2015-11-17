#!/usr/bin/env python
# -*- coding: utf-8 -*-

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


"""
Loggers to be used by the EmailResponder processes. (Basically a wrapper
around syslog.)
Can be used like:
    from logger import logger, logger_json

NOTE: For logger_json, caller must do their own JSON stringifying.
"""

import os
import sys
import logging
import logging.handlers


_DEBUG = os.environ.get('DEBUG', False)


# Get the name of the main module
_main = sys.modules['__main__'].__file__ if hasattr(sys.modules['__main__'], '__file__') else 'EmailResponder'
# ...just the filename, without any path
_main = _main.split(os.path.sep)[-1]

# Before Python 3.3, there is no way to specify a "tag" or "ident" to syslog
# entries. So we'll hack it in manually.
# Ref:
# http://docs.python.org/dev/library/logging.handlers.html#logging.handlers.SysLogHandler.emit
# http://stackoverflow.com/a/19611291/729729
class MySysLogHandler(logging.handlers.SysLogHandler):
    def __init__(self, facility):
        super(MySysLogHandler, self).__init__(address='/dev/log', facility=facility)
        self.ident = _main

    def emit(self, record):
        priority = self.encodePriority(self.facility, self.mapPriority(record.levelname))
        record.ident = self.ident
        record.facility = self.facility
        super(MySysLogHandler, self).emit(record)

_handler = MySysLogHandler(logging.handlers.SysLogHandler.LOG_LOCAL0)
_handler.formatter = logging.Formatter(fmt='%(ident)s[%(process)d][%(facility)s]: %(levelname)s: %(message)s')
logger = logging.getLogger(_main)
logger.setLevel(logging.DEBUG if _DEBUG else logging.INFO)
logger.addHandler(_handler)

# We are using the LOCAL1 facility to output JSON
_handler_json = MySysLogHandler(logging.handlers.SysLogHandler.LOG_LOCAL1)
# Hack the message into a JSON string.
_handler_json.formatter = logging.Formatter(fmt='%(ident)s[%(process)d][%(facility)s]: %(message)s')
# The JSON handler is not a child of the main handler, so it won't also be
# logged there.
logger_json = logging.getLogger(_main+'-json')
logger_json.setLevel(logging.DEBUG if _DEBUG else logging.INFO)
logger_json.addHandler(_handler_json)
