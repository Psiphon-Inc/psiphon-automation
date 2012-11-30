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


import json
import yaml
import os
import sys
try:
    import syslog
except:
    pass

import decryptor
from emailgetter import EmailGetter
import emailsender
import mailformatter


_CONFIG_FILENAME = 'conf.json'
_DEBUG = ('DEBUG' in os.environ) and os.environ['DEBUG']


def _debug_log(s):
    if not _DEBUG:
        return
    _log(s)


def _log(s):
    if 'syslog' in globals():
        syslog.syslog(syslog.LOG_ERR, s)
        if _DEBUG:
            print(s)
    else:
        if _DEBUG:
            print(s)


def _read_config(conf_file):
    with open(conf_file, 'r') as conf_fp:
        config = json.load(conf_fp)
    return config


def _load_yaml(yaml_string):
    '''
    Load all YAML "documents" in `yaml_string` and return them as a list of
    dicts.
    '''
    yaml_docs = []
    for yaml_doc in yaml.safe_load_all(yaml_string):
        yaml_docs.append(yaml_doc)
    return yaml_docs


def _assign_value_to_obj_at_path(obj, obj_path, value):
    if not obj or not obj_path:
        return

    target = obj
    for k in obj_path[:-1]:
        target = target[k]
    target[obj_path[-1]] = value


def _convert_psinet_values(psinet, yaml_docs):
    '''
    Converts sensitive or non-human-readable values in the YAML to IDs and
    names. Modifies the YAML directly.
    '''
    for path, val in objwalk(yaml_docs):
        if path[-1] == 'ipAddress':
            server = psinet.get_server_by_ip_address(val)
            if not server:
                server = psinet.get_deleted_server_by_ip_address(val)
                if server:
                    server.id += ' [DELETED]'

            # If the psinet DB is stale, we might not find the IP address, but
            # we still want to redact it.
            _assign_value_to_obj_at_path(yaml_docs,
                                         path,
                                         server.id if server else '[UNKNOWN]')
        elif path[-1] == 'PROPAGATION_CHANNEL_ID':
            propagation_channel = psinet.get_propagation_channel_by_id(val)
            if propagation_channel:
                _assign_value_to_obj_at_path(yaml_docs, path, propagation_channel.name)
        elif path[-1] == 'SPONSOR_ID':
            sponsor = psinet.get_sponsor_by_id(val)
            if sponsor:
                _assign_value_to_obj_at_path(yaml_docs, path, sponsor.name)


def _convert_ip_addresses(psinet, yaml_docs):
    '''
    Converts IP addresses the YAML to code words. We don't want to email them
    around in the clear.
    Modifies the YAML directly.
    '''
    for path, val in objwalk(yaml_docs):
        if path[-1] == 'ipAddress':
            server = psinet.get_server_by_ip_address(val)
            if server:
                _assign_value_to_obj_at_path(yaml_docs, path, server.id)


def go():
    config = _read_config(_CONFIG_FILENAME)

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
        _debug_log('maildecryptor: msg has %d attachments' % len(msg['attachments']))

        for attachment in msg['attachments']:
            # Not all attachments will be in our format, so expect exceptions.
            try:
                encrypted_info = attachment.getvalue()

                encrypted_info = json.loads(encrypted_info)

                diagnostic_info = decryptor.decrypt(private_key_pem,
                                                    config['privateKeyPassword'],
                                                    encrypted_info)

                diagnostic_info = diagnostic_info.strip()

                yaml_docs = _load_yaml(diagnostic_info)

                # Modifies yaml_docs
                _convert_psinet_values(psinet, yaml_docs)

                # Convert the modified YAML back into a string for emailing.
                diagnostic_info_text = yaml.safe_dump_all(yaml_docs,
                                                          default_flow_style=False)

                try:
                    diagnostic_info_html = mailformatter.format(yaml_docs)
                except Exception as e:
                    diagnostic_info_html = None

                # If we get to here, then we have a valid diagnostic email.
                # Reply with the decrypted content.

                emailsender.send(config['smtpServer'],
                                 config['smtpPort'],
                                 config['emailUsername'],
                                 config['emailPassword'],
                                 config['emailUsername'],
                                 config['emailUsername'],
                                 u'Re: %s' % (msg['subject'] or ''),
                                 diagnostic_info_text,
                                 diagnostic_info_html,
                                 msg['msgobj']['Message-ID'])

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
                _debug_log('maildecryptor: expected exception: %s' % e)


###
# From http://code.activestate.com/recipes/577982-recursively-walk-python-objects/
###

from collections import Mapping, Set, Sequence

# dual python 2/3 compatability, inspired by the "six" library
string_types = (str, unicode) if str is bytes else (str, bytes)
iteritems = lambda mapping: getattr(mapping, 'iteritems', mapping.items)()


def objwalk(obj, path=(), memo=None):
    if memo is None:
        memo = set()
    iterator = None
    if isinstance(obj, Mapping):
        iterator = iteritems
    elif isinstance(obj, (Sequence, Set)) and not isinstance(obj, string_types):
        iterator = enumerate
    if iterator:
        if id(obj) not in memo:
            memo.add(id(obj))
            for path_component, value in iterator(obj):
                for result in objwalk(value, path + (path_component,), memo):
                    yield result
            memo.remove(id(obj))
    else:
        yield path, obj
