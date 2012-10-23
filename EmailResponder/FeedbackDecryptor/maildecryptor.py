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

import decryptor
from emailgetter import EmailGetter
import emailsender


_CONFIG_FILENAME = 'conf.json'


def _read_config(conf_file):
    with open(conf_file) as conf_fp:
        config = json.load(conf_fp)
    return config


def go():
    config = _read_config(_CONFIG_FILENAME)

    emailgetter = EmailGetter(config['popServer'],
                              config['popPort'],
                              config['emailUsername'],
                              config['emailPassword'])

    private_key_pem = open(config['privateKeyPemFile']).read()

    # Retrieve and process email
    for msg in emailgetter.get():
        for attachment in msg['attachments']:
            # Not all attachments will be in our format, so expect exceptions.
            try:
                encrypted_info = attachment.getvalue()

                encrypted_info = json.loads(encrypted_info)

                diagnostic_info = decryptor.decrypt(private_key_pem, encrypted_info)

                diagnostic_info = diagnostic_info.strip()

                # If we get to here, then we have a valid diagnostic email.
                # Reply with the decrypted content.

                emailsender.send(config['smtpServer'],
                                 config['smtpPort'],
                                 config['emailUsername'],
                                 config['emailPassword'],
                                 config['emailUsername'],
                                 config['emailUsername'],
                                 u'Re: ' + msg['subject'] if msg['subject'] else '',
                                 diagnostic_info,
                                 msg['msgobj']['Message-ID'])

            except (ValueError, TypeError):
                # Try the next attachment/message
                pass
