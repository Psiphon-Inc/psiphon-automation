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
import re
import os
try:
    import syslog
except:
    pass

import decryptor
from emailgetter import EmailGetter
import emailsender


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


def _remove_ip_addresses(yaml_string):
    '''
    Removes IP addresses from the YAML. We don't want to email them around in
    the clear.
    '''
    return re.sub(r'ipAddress: .*\n', 'ipAddress: "[redacted]"\n', yaml_string)


def go(key_password):
    config = _read_config(_CONFIG_FILENAME)

    emailgetter = EmailGetter(config['popServer'],
                              config['popPort'],
                              config['emailUsername'],
                              config['emailPassword'])

    private_key_pem = open(config['privateKeyPemFile'], 'r').read()

    # Retrieve and process email
    for msg in emailgetter.get():
        _debug_log('maildecryptor: msg has %d attachments' % len(msg['attachments']))

        for attachment in msg['attachments']:
            # Not all attachments will be in our format, so expect exceptions.
            try:
                encrypted_info = attachment.getvalue()

                encrypted_info = json.loads(encrypted_info)

                diagnostic_info = decryptor.decrypt(private_key_pem,
                                                    key_password,
                                                    encrypted_info)

                diagnostic_info = diagnostic_info.strip()

                diagnostic_info = _remove_ip_addresses(diagnostic_info)

                # If we get to here, then we have a valid diagnostic email.
                # Reply with the decrypted content.

                emailsender.send(config['smtpServer'],
                                 config['smtpPort'],
                                 config['emailUsername'],
                                 config['emailPassword'],
                                 config['emailUsername'],
                                 config['emailUsername'],
                                 u'Re: %s' % (msg['subject'] or ''),
                                 diagnostic_info,
                                 msg['msgobj']['Message-ID'])

            except (ValueError, TypeError) as e:
                # Try the next attachment/message
                _debug_log('maildecryptor: expected exception: %s' % e)
