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
import sender
import datatransformer


_SLEEP_TIME_SECS = 60
_BUCKET_ITEM_MIN_SIZE = 100


def _is_bucket_item_sane(key):
    logger.debug_log('s3decryptor._is_bucket_item_sane start')

    if key.size < _BUCKET_ITEM_MIN_SIZE or key.size > int(config['s3ObjectMaxSize']):
        err = 'item not sane size: %d' % key.size
        logger.error(err)
        return False

    logger.debug_log('s3decryptor._is_bucket_item_sane end')

    return True


def _bucket_iterator(bucket):
    logger.debug_log('s3decryptor._bucket_iterator start')

    while True:
        for key in bucket.list():
            logger.debug_log('s3decryptor._bucket_iterator: %s' % key)

            contents = None

            # Do basic sanity checks before trying to download the object
            if _is_bucket_item_sane(key):
                logger.debug_log('s3decryptor._bucket_iterator: good item found, yielding')
                contents = key.get_contents_as_string()

            # Make sure to delete the key *before* proceeding, so we don't
            # try to re-process if there's an error.
            bucket.delete_key(key)

            if contents:
                yield contents

        logger.debug_log('s3decryptor._bucket_iterator: no item found, sleeping')
        time.sleep(_SLEEP_TIME_SECS)

    logger.debug_log('s3decryptor._bucket_iterator end')


def _should_email_data(diagnostic_info):
    '''
    Determine if this diagnostic info should be emailed. Not all diagnostic
    info bundles have useful information that needs to be immediately seen by
    a human.
    '''
    # Only email info that has a user-entered feedback message.
    return diagnostic_info.get('Feedback', {}).get('Message', {}).get('text')


def go():
    logger.debug_log('s3decryptor.go: start')

    s3_conn = S3Connection(config['aws_access_key_id'], config['aws_secret_access_key'])
    bucket = s3_conn.get_bucket(config['s3_bucket_name'])

    # Note that `_bucket_iterator` throttles itself if/when there are no
    # available objects in the bucket.
    for encrypted_info_json in _bucket_iterator(bucket):
        logger.debug_log('s3decryptor.go: processing item')

        # In theory, all bucket items should be usable by us, but there's
        # always the possibility that a user (or attacker) is messing with us.
        try:
            encrypted_info = json.loads(encrypted_info_json)

            diagnostic_info = decryptor.decrypt(encrypted_info)

            diagnostic_info = diagnostic_info.strip()

            # HACK: PyYaml only supports YAML 1.1, which is not a true superset
            # of JSON. Therefore it can (and does) throw errors on some Android
            # feedback. We will try to load using JSON first.
            # TODO: Get rid of all YAML feedback and remove it from here.
            try:
                diagnostic_info = json.loads(diagnostic_info)
                logger.debug_log('s3decryptor.go: loaded JSON')
            except:
                diagnostic_info = yaml.safe_load(diagnostic_info)
                logger.debug_log('s3decryptor.go: loaded YAML')

            # Modifies diagnostic_info
            utils.convert_psinet_values(config, diagnostic_info)

            if not utils.is_diagnostic_info_sane(diagnostic_info):
                # Something is wrong. Skip and continue.
                continue

            # Modifies diagnostic_info
            datatransformer.transform(diagnostic_info)

            # Store the diagnostic info
            record_id = datastore.insert_diagnostic_info(diagnostic_info)

            if _should_email_data(diagnostic_info):
                logger.debug_log('s3decryptor.go: should email')
                # Record in the DB that the diagnostic info should be emailed
                datastore.insert_email_diagnostic_info(record_id, None, None)

            # Store an autoresponder entry for this diagnostic info
            datastore.insert_autoresponder_entry(None, record_id)

            logger.log('decrypted diagnostic data')

        except decryptor.DecryptorException as e:
            logger.exception()
            logger.error(str(e))
            try:
                # Something bad happened while decrypting. Report it via email.
                sender.send(config['decryptedEmailRecipient'],
                            config['emailUsername'],
                            u'S3Decryptor: bad object',
                            encrypted_info_json,
                            None)  # no html body
            except smtplib.SMTPException as e:
                logger.exception()
                logger.error(str(e))

        # yaml.constructor.ConstructorError was being thown when a YAML value
        # consisted of just string "=". Probably due to this PyYAML bug:
        # http://pyyaml.org/ticket/140
        except (ValueError, TypeError, yaml.constructor.ConstructorError) as e:
            # Try the next attachment/message
            logger.exception()
            logger.error(str(e))

    logger.debug_log('s3decryptor.go: end')
