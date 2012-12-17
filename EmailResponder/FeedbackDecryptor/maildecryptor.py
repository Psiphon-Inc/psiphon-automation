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
Periodically checks feedback email. There are three types of email:
  1. Not related to diagnostic info at all. Disregard.
  2. Has diagnostic attachment. Decrypt attachment and store in the
     diagnostic-info-DB. Store email message ID and diagnostic info ID (and
     subject) in email-ID-DB.
  3. Has diagnostic info ID, but no attachment. Store email message ID and
     diagnostic info ID (and subject) in email-ID-DB.
'''

import json
import yaml
import sys
import os
import binascii
import re

import logger
import utils
from config import config
import decryptor
from emailgetter import EmailGetter
import emailsender
import datastore


def _upgrade_old_object(yaml_docs):
    # Our old YAML had '.' in some key names, which is illegal.
    for path, val in utils.objwalk(yaml_docs):
        if path[-1].find('.') >= 0:
            utils.rename_key_in_obj_at_path(yaml_docs,
                                            path,
                                            path[-1].replace('.', '__'))

    # Our old YAML format was multiple YAML docs in a single string. We'll
    # convert that to the new format.
    obj = {}
    obj['StatusHistory'] = yaml_docs.pop()

    # The presence of DiagnosticHistory was optional once upon a time
    obj['DiagnosticHistory'] = yaml_docs.pop() if len(yaml_docs) > 2 else []

    obj['ServerResponseCheck'] = yaml_docs.pop()
    obj['SystemInformation'] = yaml_docs.pop()

    # Old YAML had no Metadata section
    metadata = {}
    metadata['platform'] = 'android'
    metadata['version'] = 0
    metadata['id'] = binascii.hexlify(os.urandom(8))
    obj['Metadata'] = metadata

    return obj


def _load_yaml(yaml_string):
    # TODO: Rip the backwards-compatibility out of this at some later date.

    yaml_docs = []
    for yaml_doc in yaml.safe_load_all(yaml_string):
        yaml_docs.append(yaml_doc)

    obj = None
    if len(yaml_docs) == 1:
        obj = yaml_docs.pop()
    elif len(yaml_docs) > 1:
        obj = _upgrade_old_object(yaml_docs)

    return obj


def _convert_psinet_values(psinet, obj):
    '''
    Converts sensitive or non-human-readable values in the YAML to IDs and
    names. Modifies the YAML directly.
    '''
    for path, val in utils.objwalk(obj):
        if path[-1] == 'ipAddress':
            server = psinet.get_server_by_ip_address(val)
            if not server:
                server = psinet.get_deleted_server_by_ip_address(val)
                if server:
                    server.id += ' [DELETED]'

            # If the psinet DB is stale, we might not find the IP address, but
            # we still want to redact it.
            utils.assign_value_to_obj_at_path(obj,
                                              path,
                                              server.id if server else '[UNKNOWN]')
        elif path[-1] == 'PROPAGATION_CHANNEL_ID':
            propagation_channel = psinet.get_propagation_channel_by_id(val)
            if propagation_channel:
                utils.assign_value_to_obj_at_path(obj,
                                                  path,
                                                  propagation_channel.name)
        elif path[-1] == 'SPONSOR_ID':
            sponsor = psinet.get_sponsor_by_id(val)
            if sponsor:
                utils.assign_value_to_obj_at_path(obj,
                                                  path,
                                                  sponsor.name)


def _get_id_from_email_address(email_address):
    r = r'\b(?P<addr>[a-z]+)\+(?P<platform>[a-z]+)\+(?P<id>[a-fA-F0-9]+)@'
    m = re.match(r, email_address)
    if not m:
        return None
    return m.groupdict()['id']


def go():
    # Load the psinet DB
    sys.path.append(config['psiOpsPath'])
    import psi_ops
    psinet = psi_ops.PsiphonNetwork.load_from_file(config['psinetFilePath'])

    emailgetter = EmailGetter(config['popServer'],
                              config['popPort'],
                              config['emailUsername'],
                              config['emailPassword'])

    private_key_pem = open(config['privateKeyPemFile'], 'r').read()

    # Retrieve and process email.
    # Note that `emailgetter.get` throttles itself if/when there are no emails
    # immediately available.
    for msg in emailgetter.get():
        logger.debug_log('maildecryptor: msg has %d attachments' % len(msg['attachments']))

        email_processed_successfully = False

        #
        # First try to process attachments.
        #
        for attachment in msg['attachments']:
            # Not all attachments will be in our format, so expect exceptions.
            try:
                encrypted_info = attachment.getvalue()

                encrypted_info = json.loads(encrypted_info)

                diagnostic_info = decryptor.decrypt(private_key_pem,
                                                    config['privateKeyPassword'],
                                                    encrypted_info)

                diagnostic_info = diagnostic_info.strip()

                diagnostic_info = _load_yaml(diagnostic_info)

                # Modifies diagnostic_info
                _convert_psinet_values(psinet, diagnostic_info)

                # Store the diagnostic info
                datastore.insert_diagnostic_info(diagnostic_info)

                # Store the association between the diagnostic info and the email
                datastore.insert_email_diagnostic_info(diagnostic_info['Metadata']['id'],
                                                       msg['msgobj']['Message-ID'],
                                                       msg['subject'])
                email_processed_successfully = True
                break

            except decryptor.DecryptorException as e:
                # Something bad happened while decrypting. Report it via email.
                emailsender.send(config['smtpServer'],
                                 config['smtpPort'],
                                 config['emailUsername'],
                                 config['emailPassword'],
                                 config['emailUsername'],
                                 config['emailUsername'],
                                 u'Re: %s' % (msg['subject'] or ''),
                                 'Decrypt failed: %s' % e,
                                 msg['msgobj']['Message-ID'])

            except (ValueError, TypeError) as e:
                # Try the next attachment/message
                logger.debug_log('maildecryptor: expected exception: %s' % e)

        if email_processed_successfully:
            break

        #
        # The email might refer (by ID) to a diagnostic info package elsewhere
        #

        diagnostic_info_id = _get_id_from_email_address(msg['to'])
        if diagnostic_info_id:
            # Store the association between this email and the forthcoming
            # diagnostic info.
            datastore.insert_email_diagnostic_info(diagnostic_info_id,
                                                   msg['msgobj']['Message-ID'],
                                                   msg['subject'])

            # We'll set this for completeness...
            email_processed_successfully = True

        # At this point either we've extracted useful info from the email or
        # there's nothing to extract.
