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
import sys
import logging
import logging.handlers

datastore_log = lambda _: _
try:
    import datastore
    datastore_log = datastore.add_error
except Exception as e:
    print 'datastore import failed: %s' % str(e)


_DEBUG = os.environ.get('DEBUG', False)

_my_logger = logging.getLogger('MyLogger')
_my_logger.setLevel(logging.DEBUG if _DEBUG else logging.WARNING)

# syslog won't work on Windows
try:
    _my_logger.addHandler(logging.handlers.SysLogHandler(address='/dev/log'))
except:
    _my_logger.addHandler(logging.StreamHandler())

# Before Python 3.3, there is no way to specify a "tag" or "ident" to syslog
# entries. So we'll hack it in manually.
# Ref: http://docs.python.org/dev/library/logging.handlers.html#logging.handlers.SysLogHandler.emit
_main = sys.modules['__main__'].__file__ if hasattr(sys.modules['__main__'], '__file__') else 'feedbackdecryptor_service'


def debug_log(s):
    _my_logger.debug('%s: %s' % (_main, s))


def log(s):
    _my_logger.critical('%s: %s' % (_main, s))


def exception(s=''):
    _my_logger.exception('%s: %s' % (_main, s))


def error(s):
    '''
    This function also write the message to the datastore, so that it will
    show up in the daily stats email.
    '''
    log(s)
    datastore_log({'module': _main, 'error': s})


def disable():
    '''
    Stops logging. To be used during testing.
    '''
    class Noop(object):
        def __getattr__(self, name):
            return lambda _ : None

    global _my_logger
    _my_logger = Noop()
