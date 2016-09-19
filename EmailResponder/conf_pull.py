#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2015, Psiphon Inc.
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
Pulls email respondering configuration file, writes it to disk, and extracts
other required config files from it.
'''


import os
import json
import argparse

from logger import logger
import settings
import aws_helpers


RESPONDER_DOMAINS_LIST_FILE = os.path.join(os.path.expanduser('~%s' % settings.MAIL_RESPONDER_USERNAME),
                                           'postfix_responder_domains')
ADDRESS_MAPS_LIST_FILE = os.path.join(os.path.expanduser('~%s' % settings.MAIL_RESPONDER_USERNAME),
                                      'postfix_address_maps')


def go():
    '''
    Reads in the given configuration file.
    Return True if successful, False otherwise.
    '''

    try:
        # Note that json.load reads in unicode strings.
        conf_data, new_conf = aws_helpers.get_s3_cached_file(
                                            settings.ATTACHMENT_CACHE_DIR,
                                            settings.CONFIG_S3_BUCKET,
                                            settings.CONFIG_S3_KEY)
        conf_data = json.loads(conf_data.read())

        all_email_addrs = set()
        # Do some validation
        for item in conf_data:
            if 'email_addr' not in item \
                    or 'body' not in item \
                    or 'attachments' not in item:
                raise Exception('invalid config item: %s' % repr(item))

            all_email_addrs.add(item['email_addr'])

        if new_conf:
            # Write the supported domains to files that will be used by
            # Postfix in its config.
            email_domains = set([addr[addr.find('@')+1:] for addr in all_email_addrs])
            with open(RESPONDER_DOMAINS_LIST_FILE, 'w') as responder_domains_file:
                responder_domains_file.write(' '.join(email_domains))

            address_maps_lines = ['%s\t\t%s@localhost' % (addr, settings.MAIL_RESPONDER_USERNAME) for addr in all_email_addrs]
            catchall_lines = ['@%s\t\t%s@localhost' % (domain, settings.SYSTEM_DEVNULL_USER) for domain in email_domains]

            with open(ADDRESS_MAPS_LIST_FILE, 'w') as address_maps_file:
                address_maps_file.write('\n'.join(address_maps_lines))
                address_maps_file.write('\n')
                address_maps_file.write('\n'.join(catchall_lines))
                address_maps_file.write('\n')

    except Exception as ex:
        print('error: config file pull failed: %s; file: %s:%s' % (ex, settings.CONFIG_S3_BUCKET, settings.CONFIG_S3_KEY))
        logger.critical('error: config file pull failed: %s; file: %s:%s', ex, settings.CONFIG_S3_BUCKET, settings.CONFIG_S3_KEY)
        return False

    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pull the responder configuration')
    parser.add_argument('--cron', action='store_true', default=False, help='calling from cron; suppress output')
    args = parser.parse_args()

    go()

    if not args.cron:
        print('Mail responder config pull successful')
