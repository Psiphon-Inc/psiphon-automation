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

# TODO: Create indexes

import datetime
from pymongo import MongoClient


_EXPIRY_MINUTES = 360


_connection = MongoClient()
_db = _connection.maildecryptor
_diagnostic_info_store = _db.diagnostic_info
_email_diagnostic_info_store = _db.email_diagnostic_info


def insert_diagnostic_info(obj):
    obj['datetime'] = datetime.datetime.now()
    return _diagnostic_info_store.insert(obj)


def insert_email_diagnostic_info(diagnostic_info_id,
                                 email_id,
                                 email_subject):
    obj = {
           'diagnostic_info_id': diagnostic_info_id,
           'email_id': email_id,
           'email_subject': email_subject,
           'datetime': datetime.datetime.now()
          }
    return _email_diagnostic_info_store.insert(obj)


def get_email_diagnostic_info_iterator():
    return _email_diagnostic_info_store.find()


def find_diagnostic_info(diagnostic_info_id):
    return _diagnostic_info_store.find({'Metadata.id': diagnostic_info_id})


def remove_email_diagnostic_info(email_diagnostic_info):
    return _email_diagnostic_info_store.remove({'_id': email_diagnostic_info['_id']})


def expire_old_email_diagnostic_info_records():
    expiry_datetime = datetime.datetime.now() - datetime.timedelta(minutes=_EXPIRY_MINUTES)
    return _email_diagnostic_info_store.remove({'datetime': {'$lt': expiry_datetime}})
