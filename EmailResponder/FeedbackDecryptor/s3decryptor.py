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
Periodically checks S3 upload bucket for new items. Gets them, deletes them.
Decrypts them and stores them in the diagnostic-info-DB.
'''

import time
import smtplib
import json
import yaml
from boto.s3.connection import S3Connection

from config import config
import logger
import utils
import decryptor
import datastore
import sendmail


_SLEEP_TIME_SECS = 60
_BUCKET_ITEM_MIN_SIZE = 100
_BUCKET_ITEM_MAX_SIZE = (1024 * 1024 * 1024)  # 1 MB


def _is_bucket_item_sane(key):
    if key.size < _BUCKET_ITEM_MIN_SIZE or key.size > _BUCKET_ITEM_MAX_SIZE:
        return False
    return True


def _bucket_iterator(bucket):
    while True:
        for key in bucket.list():
            # Do basic sanity checks before trying to download the object
            if _is_bucket_item_sane(key):
                yield key.get_contents_as_string()

            bucket.delete_key(key)

        time.sleep(_SLEEP_TIME_SECS)


def go():
    s3_conn = S3Connection(config['aws_access_key_id'], config['aws_secret_access_key'])
    bucket = s3_conn.get_bucket(config['s3_bucket_name'])

    # Note that `_bucket_iterator` throttles itself if/when there are no
    # available objects in the bucket.
    for encrypted_info_json in _bucket_iterator(bucket):
        # In theory, all bucket items should be usable by us, but there's
        # always the possibility that a user (or attacker) is messing with us.
        try:
            encrypted_info = json.loads(encrypted_info_json)

            diagnostic_info = decryptor.decrypt(encrypted_info)

            diagnostic_info = diagnostic_info.strip()

            diagnostic_info = yaml.safe_load(diagnostic_info)

            # Modifies diagnostic_info
            utils.convert_psinet_values(config, diagnostic_info)

            if not utils.is_diagnostic_info_sane(diagnostic_info):
                # Something is wrong. Delete and continue.
                logger.log('non-sane object found')
                continue

            # Store the diagnostic info
            datastore.insert_diagnostic_info(diagnostic_info)

        except decryptor.DecryptorException:
            logger.exception()
            try:
                # Something bad happened while decrypting. Report it via email.
                sendmail.send(config['smtpServer'],
                              config['smtpPort'],
                              config['emailUsername'],
                              config['emailPassword'],
                              config['emailUsername'],
                              config['decryptedEmailRecipient'],
                              u'S3Decryptor: bad object',
                              encrypted_info_json,
                              None)
            except smtplib.SMTPException:
                logger.exception()

        except (ValueError, TypeError):
            # Try the next attachment/message
            logger.exception()
