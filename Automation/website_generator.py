#!/usr/bin/python
#
# Copyright (c) 2013, Psiphon Inc.
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
#

import subprocess
import os
import errno


WEBSITE_DIR = '../Website'


def generate(dest_dir):
    '''
    Generates the website into `dest_dir`.
    '''

    dest_dir = os.path.abspath(dest_dir)

    try:
        os.makedirs(dest_dir)
    except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(dest_dir):
            pass
        else:
            raise

    prev_dir = os.getcwd()
    os.chdir(WEBSITE_DIR)

    try:
        subprocess.check_call('docpad upgrade', shell=True)
        subprocess.check_call('docpad update', shell=True)
        subprocess.check_call('docpad clean --out %s' % dest_dir, shell=True)
        subprocess.check_call('docpad generate --env production,static --out %s' % dest_dir,
                              shell=True)
    finally:
        os.chdir(prev_dir)
