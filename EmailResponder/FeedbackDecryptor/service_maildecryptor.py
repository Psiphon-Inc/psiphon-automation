#!/usr/bin/env python

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

import signal
import sys
import time

import maildecryptor
import logger


def _do_exit(signum, frame):
    logger.log('Shutting down')
    sys.exit(0)


def main():
    logger.log('Starting up')

    signal.signal(signal.SIGTERM, _do_exit)

    while True:
        try:
            maildecryptor.go()
        except Exception:
            logger.exception()
            time.sleep(60)
            continue


if __name__ == '__main__':
    main()
