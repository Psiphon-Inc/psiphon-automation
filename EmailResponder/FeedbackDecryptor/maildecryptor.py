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

    # Retrieve and process email
    for msg in emailgetter.get():
        print(repr(msg))
        print('===================================')
        print('got message: ' + repr(msg['subject']))

        for attachment in msg['attachments']:
            # Not all attachments will be in our format, so expect exceptions.
            try:
                encrypted_info = attachment.getvalue()

                encrypted_info = json.loads(encrypted_info)

                diagnostic_info = decryptor.decrypt(encrypted_info)

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

                open('diag.txt', 'w').write(diagnostic_info)

                print('===================================')
                print(diagnostic_info)

            except (ValueError, TypeError) as e:
                # Try the next attachment/message
                print(e)
                pass
