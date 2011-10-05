#!/usr/bin/python
#
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
#

import tempfile


def unlock(cms_filename):
    pass


def import_(source_filename, cms_filename, keep_locked=False):
    pass


def export(cms_filename, dest_filename):
    pass


# Adapted from:
# http://code.activestate.com/recipes/521901-upgradable-pickles/

class PersistentObject(object):

    class_version = '0.0'

    def __init__(self, cms_filename):
        self.version = self.__class__.class_version
        self.cms_filename = cms_filename

    def __del__(self):
        psi_cms.unlock(self.cms_filename)

    def save(self):
        with tempfile.NamedTemporaryFile() as file:
            file.write(cPickle.dumps(self))
            psi_cms.import_(file.name, self.cms_filename, keep_locked=True)

    @staticmethod
    def load(cms_filename):
        with tempfile.NamedTemporaryFile() as file:
            psi_cms.lock(cms_filename)
            psi_cms.export(cms_filename, file.name)
            file.seek(0)
            obj = cPickle.loads(file.read())
            if not hasattr(obj, 'version'):
                obj.version = '0.0'
            if obj.version != obj.class_version:
                obj.upgrade()
            returnobj

    def upgrade(self):
        pass 
