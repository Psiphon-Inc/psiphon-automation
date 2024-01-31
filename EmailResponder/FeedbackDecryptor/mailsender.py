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
Periodically checks email-ID-DB. If diagnostic info ID is found in
diagnostic-info-DB, then response email is formatted and sent; entry is
deleted from email-ID-DB. Also cleans up expired email-ID-DB entries.
'''

import time
import pprint
import multiprocessing

from config import config
import logger
import datastore
import sender
import mailformatter


# This should be set by the service manager when it receives SIGTERM
terminate = False

_SLEEP_TIME_SECS = 60


def _email_diagnostic_info_records_iterator():
    '''
    Generator for obtaining email_diagnostic_info records.
    '''
    while True:
        # Every hour or so, pymongo throws a CursorNotFound error. This is due to the
        # the cursor being idle more than 10 minutes. It generally doesn't take us that
        # long to send an email, but each time a request to mongodb is made, there's a
        # batch of records returned. Processing all of the records in that batch _does_
        # take more than 10 minutes. So when we try to get another batch the cursor is dead.
        # To address this, we could decrease the batch size or increase the cursor lifetime.
        # More details: https://stackoverflow.com/a/24200795/729729
        logger.debug_log('fresh cursor')

        for rec in datastore.get_email_diagnostic_info_iterator():
            yield rec

        time.sleep(_SLEEP_TIME_SECS)


def go():
    '''
    Spawns the worker subprocesses and sends data to them.
    '''
    logger.debug_log('go: start')

    # Set up the multiprocessing
    worker_manager = multiprocessing.Manager()
    # We only want to pull items out of S3 as we process them, so the queue needs to be
    # limited to the number of worker processes.
    work_queue = worker_manager.Queue(maxsize=config['numProcesses'])
    # Spin up the workers
    worker_pool = multiprocessing.Pool(processes=config['numProcesses'])
    [worker_pool.apply_async(_process_work_items, (work_queue,)) for i in range(config['numProcesses'])]

    # Retrieve and process email-to-diagnostic-info records.
    # Note that `_email_diagnostic_info_records` throttles itself if/when
    # there are no records immediately available.
    for email_diagnostic_info in _email_diagnostic_info_records_iterator():
        if terminate:
            logger.debug_log('go: got terminate; closing work_queue')
            work_queue.close()
            break

        logger.debug_log('go: enqueueing work item')
        # This blocks if the queue is full
        work_queue.put(email_diagnostic_info)
        logger.debug_log('go: enqueued work item')

    logger.debug_log('go: done')


def _process_work_items(work_queue):
    '''
    This runs in the multiprocessing forks to do the actual work. It is a long-lived loop.
    '''
    while True:
        if terminate:
            logger.debug_log('got terminate; stopping work')
            break

        logger.debug_log('_process_work_items: dequeueing work item')
        # This blocks if the queue is empty
        email_diagnostic_info = work_queue.get()
        logger.debug_log('_process_work_items: dequeued work item')

        logger.debug_log('feedback object id: %s' % email_diagnostic_info['diagnostic_info_record_id'])

        # Check if there is (yet) a corresponding diagnostic info record
        diagnostic_info = datastore.find_diagnostic_info(email_diagnostic_info['diagnostic_info_record_id'])
        if not diagnostic_info:
            logger.debug_log('diagnostic_info not found; skipping')
            continue

        logger.log('feedback id: %s' % diagnostic_info.get('Metadata', {}).get('id'))

        diagnostic_info_text = pprint.pformat(diagnostic_info, indent=1, width=75)

        try:
            diagnostic_info_html = mailformatter.format(diagnostic_info)
        except Exception as e:
            logger.error('format failed: %s' % str(e))

            diagnostic_info_html = None

        # If we get to here, then we have a valid diagnostic email.
        # Reply with the decrypted content.

        # If this is not a reply, set a subject
        # If no subject is pre-determined, create one.
        if email_diagnostic_info.get('email_id') is None:
            subject = 'DiagnosticInfo: %s (%s)' % (diagnostic_info['Metadata'].get('platform',
                                                    '[NO_PLATFORM]').capitalize(),
                                                    diagnostic_info['Metadata'].get('id', '[NO_ID]'))
        else:
            subject = 'Re: %s' % (email_diagnostic_info['email_subject'] or '')

        try:
            sender.send_response(config['decryptedEmailRecipient'],
                        config['emailUsername'],
                        subject,
                        diagnostic_info_text,
                        diagnostic_info_html,
                        email_diagnostic_info.get('email_id'),  # may be None
                        None)  # no attachment
            logger.log('decrypted formatted email sent')
        except Exception as e:
            logger.exception()
            logger.error(str(e))

        # Delete the processed record. (Note that sending the email might have
        # failed, but we're deleting it anyway. This is a debatable decision.)
        datastore.remove_email_diagnostic_info(email_diagnostic_info)
