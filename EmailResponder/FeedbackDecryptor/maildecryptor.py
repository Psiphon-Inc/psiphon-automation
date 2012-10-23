import json
from base64 import b64decode

import decryptor
from emailgetter import EmailGetter


_CONFIG_FILENAME = 'conf.json'


def _read_config(conf_file):
    with open(conf_file) as conf_fp:
        config = json.load(conf_fp)
    return config


def go():
    config = _read_config(_CONFIG_FILENAME)

    emailgetter = EmailGetter(config['popServer'],
                              config['popPort'],
                              config['popUsername'],
                              config['popPassword'])

    # Retrieve and process email
    for msg in emailgetter.get():
        print(repr(msg))
        print('===================================')
        print('got message: ' + msg['subject'])

        for attachment in msg['attachments']:
            # Not all attachments will be in our format, so expect exceptions.
            try:
                encrypted_info = b64decode(attachment.getvalue())

                # b64decode will often return an empty string on error
                if not encrypted_info:
                    raise TypeError('attachment is not base64 encoded')

                encrypted_info = json.loads(encrypted_info)

                diagnostic_info = decryptor.decrypt(encrypted_info)

                open('diag.txt', 'w').write(diagnostic_info)

                print('===================================')
                print(diagnostic_info)

            except (ValueError, TypeError) as e:
                # Try the next attachment/message
                print(e)
                pass
