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
import json
import yaml
import multiprocessing
import boto3

from config import config
import logger
import utils
import decryptor
import datastore
import sender
import datatransformer
import redactor


# This should be set by the service manager when it receives SIGTERM
terminate = False

_SLEEP_TIME_SECS = 10
_BUCKET_ITEM_MIN_SIZE = 100


def _is_bucket_item_sane(obj: 'boto3.S3.Object') -> bool:
    if obj.size < _BUCKET_ITEM_MIN_SIZE or obj.size > int(config.s3ObjectMaxSize):
        err = 'item not sane size: %d' % obj.size
        logger.error(err)
        return False

    return True


def _bucket_iterator(bucket: 'boto3.S3.Bucket') -> str:
    logger.debug_log('_bucket_iterator start')

    while True:
        for obj in bucket.objects.all():
            logger.debug_log('_bucket_iterator: %s' % obj.key)

            if terminate:
                logger.debug_log('got terminate; _bucket_iterator breaking')
                return

            # Do basic sanity checks before trying to download the object
            contents = None
            try:
                if _is_bucket_item_sane(obj):
                    logger.debug_log('_bucket_iterator: good item found, yielding')
                    body = obj.get().get('Body')
                    if body:
                        contents = body.read().decode('utf-8')
            except Exception as e:
                logger.error('_bucket_iterator caught exception: %s' % e)

            # Make sure to delete the object *before* proceeding, so we don't
            # try to re-process if there's an error.
            obj.delete()

            if contents:
                yield contents

        logger.debug_log('_bucket_iterator: no item found, sleeping')
        time.sleep(_SLEEP_TIME_SECS)

    logger.debug_log('_bucket_iterator end') # unreachable


def _should_email_data(diagnostic_info) -> bool:
    '''
    Determine if this diagnostic info should be emailed. Not all diagnostic
    info bundles have useful information that needs to be immediately seen by
    a human. Additionally, trying to email too many feedbacks can produce a backlog.
    '''
    if diagnostic_info.get('Metadata', {}).get('appName') in ('ryve', 'conduit',):
        return True
    elif diagnostic_info.get('Feedback', {}).get('Message', {}).get('text') and diagnostic_info.get('Feedback', {}).get('email'):
        return True
    return False


def go():
    '''
    Spawns the worker subprocesses and sends data to them.
    '''
    logger.debug_log('go: start')

    s3 = boto3.resource('s3')
    bucket = s3.Bucket(config.s3BucketName)

    # Set up the multiprocessing
    worker_manager = multiprocessing.Manager()
    # We only want to pull items out of S3 as we process them, so the queue needs to be
    # limited to the number of worker processes. We're doubling the number of workers
    # because the s3decryptor is the main workhorse of the server.
    work_queue = worker_manager.Queue(maxsize=config.numProcesses*2)
    # Spin up the workers
    worker_pool = multiprocessing.Pool(processes=config.numProcesses)
    exception_results = [worker_pool.apply_async(_process_work_items, (work_queue,)) for i in range(config.numProcesses)]

    # Note that `_bucket_iterator` throttles itself if/when there are no
    # available objects in the bucket.
    for encrypted_info_json in _bucket_iterator(bucket):
        if terminate:
            logger.debug_log('go: got terminate; closing work_queue')
            work_queue.close()
            break

        # Check if any exceptions have been thrown in the worker processes
        for result in exception_results:
            if result.ready():
                logger.debug_log('go: getting exception result')
                # This will raise an exception if one was thrown in the worker
                result.get()

        logger.debug_log('go: enqueuing work item')
        # This blocks if the queue is full
        work_queue.put(encrypted_info_json)
        logger.debug_log('go: enqueued work item')

    worker_pool.close()
    worker_pool.join()

    logger.debug_log('go: done')


def _process_work_items(work_queue):
    '''
    This runs in the multiprocessing forks to do the actual work. It is a long-lived loop.
    '''
    while True:
        if terminate:
            logger.debug_log('got terminate; stopping work')
            break

        # In theory, all bucket items should be usable by us, but there's
        # always the possibility that a user (or attacker) is messing with us.
        try:
            logger.debug_log('_process_work_items: dequeueing work item')
            # This blocks if the queue is empty
            encrypted_info_json = work_queue.get()
            logger.debug_log('_process_work_items: processing item')

            diagnostic_info = None

            encrypted_info = json.loads(encrypted_info_json)

            diagnostic_info = decryptor.decrypt(encrypted_info)
            if not diagnostic_info:
                logger.error('diagnostic_info decrypted empty')
                # Also throw, so we get an email about it
                raise Exception('diagnostic_info decrypted empty')

            diagnostic_info = diagnostic_info.strip()
            if not diagnostic_info:
                logger.error('diagnostic_info stripped empty')
                # Also throw, so we get an email about it
                raise Exception('diagnostic_info stripped empty')

            # HACK: PyYaml only supports YAML 1.1, which is not a true superset
            # of JSON. Therefore it can (and does) throw errors on some Android
            # feedback. We will try to load using JSON first.
            # TODO: Get rid of all YAML feedback and remove it from here.
            try:
                diagnostic_info = json.loads(diagnostic_info)
                logger.debug_log('_process_work_items: loaded JSON')
            except:
                diagnostic_info = yaml.safe_load(diagnostic_info)
                logger.debug_log('_process_work_items: loaded YAML')

            if not diagnostic_info:
                logger.error('diagnostic_info unmarshalled empty')
                # Also throw, so we get an email about it
                raise Exception('diagnostic_info unmarshalled empty')

            logger.log('feedback id: {0}; size: {1:.1f} MB'.format(diagnostic_info.get('Metadata', {}).get('id'), len(encrypted_info_json)/1e6))

            if not utils.is_diagnostic_info_sane(diagnostic_info):
                # Something is wrong. Skip and continue.
                logger.debug_log('_process_work_items: diagnostic_info not sane')
                continue

            # Modifies diagnostic_info
            utils.upgrade_diagnostic_info(diagnostic_info)

            # Modifies diagnostic_info
            utils.convert_psinet_values(config, diagnostic_info)

            # Modifies diagnostic_info
            redactor.redact_sensitive_values(diagnostic_info)

            # Modifies diagnostic_info
            datatransformer.transform(diagnostic_info)

            # Store the diagnostic info
            record_id = datastore.insert_diagnostic_info(diagnostic_info)
            if record_id is None:
                logger.debug_log('_process_work_items: datastore.insert_diagnostic_info returned None')
                # An error occurred or diagnostic info was a duplicate.
                continue

            if _should_email_data(diagnostic_info):
                logger.debug_log('_process_work_items: should email')
                # Record in the DB that the diagnostic info should be emailed
                datastore.insert_email_diagnostic_info(record_id, None, None)

            # Store an autoresponder entry for this diagnostic info
            datastore.insert_autoresponder_entry(None, record_id)

            logger.debug_log('decrypted diagnostic data')

        except decryptor.DecryptorException as e:
            logger.exception()
            logger.error(str(e))
            try:
                # Something bad happened while decrypting. Report it via email.
                sender.send_email(config.decryptedEmailRecipient,
                                  config.responseEmailAddress,
                                  'S3Decryptor: bad object',
                                  encrypted_info_json,
                                  None)  # no html body
            except Exception as e:
                logger.exception()
                logger.error(str(e))

        # yaml.constructor.ConstructorError was being thrown when a YAML value
        # consisted of just string "=". Probably due to this PyYAML bug:
        # http://pyyaml.org/ticket/140
        except (ValueError, TypeError, yaml.constructor.ConstructorError) as e:
            # Try the next attachment/message
            logger.exception()
            logger.error(str(e))

        except Exception as e:
            logger.error(str(e))
            try:
                import traceback
                # Something bad happened while decrypting. Report it via email.
                sender.send_email(config.decryptedEmailRecipient,
                                  config.responseEmailAddress,
                                  'S3Decryptor: unhandled exception',
                                  str(traceback.format_exception(type(e), e, e.__traceback__)) + '\n---\n' + str(diagnostic_info),
                                  None)  # no html body
            except Exception as e:
                logger.exception()
                logger.error(str(e))
            work_queue.put(e)
            raise

    logger.debug_log('_process_work_items: done')
