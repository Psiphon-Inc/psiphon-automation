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

DOCPAD_ENV = 'production,static'


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
        # using check_output to suppress output

        subprocess.check_output('docpad upgrade --env %s' % (DOCPAD_ENV,),
                                shell=True, stderr=subprocess.STDOUT)
        subprocess.check_output('docpad update --env %s' % (DOCPAD_ENV,),
                                shell=True, stderr=subprocess.STDOUT)
        subprocess.check_output('docpad clean --env %s --out "%s"' % (DOCPAD_ENV, dest_dir),
                                shell=True, stderr=subprocess.STDOUT)
        subprocess.check_output('docpad generate --env %s --out "%s"' % (DOCPAD_ENV, dest_dir),
                                shell=True, stderr=subprocess.STDOUT)
    finally:
        os.chdir(prev_dir)
