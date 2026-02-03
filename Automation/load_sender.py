# Copyright (c) 2026, Psiphon Inc.
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

"""
Self-contained email sender for load.py.

This module provides SMTP-based email sending functionality that was previously
in the FeedbackDecryptor's sender.py and config.py, but was removed/refactored.

Configuration is loaded from 'load_conf.json' in the same directory.
Expected config keys:
    - smtpServer: SMTP server hostname
    - smtpPort: SMTP server port (typically 465 for SSL)
    - emailUsername: SMTP auth username
    - emailPassword: SMTP auth password
    - emailFromAddr: From address for outgoing emails
    - statsEmailRecipients: List of recipient addresses for stats emails
"""

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_CONFIG_FILENAME = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'load_conf.json')

_config = None

def _load_config():
    global _config
    if _config is None:
        with open(_CONFIG_FILENAME, 'r') as f:
            _config = json.load(f)
        # Validate required keys
        required_keys = [
            'smtpServer', 'smtpPort', 'emailUsername', 'emailPassword',
            'emailFromAddr', 'statsEmailRecipients'
        ]
        for key in required_keys:
            if key not in _config:
                raise ValueError(f"Missing required config key: {key}")
    return _config


def send(subject, body_text, body_html, replyid=None):
    """
    Send email via SMTP. Throws `smtplib.SMTPException` on error.
    """
    config = _load_config()
    recipients = config['statsEmailRecipients']
    from_address = config['emailFromAddr']

    # Build the email message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_address

    if isinstance(recipients, list):
        msg['To'] = ', '.join(recipients)
        rcpt_list = recipients
    else:
        msg['To'] = recipients
        rcpt_list = [recipients]

    if replyid:
        msg['In-Reply-To'] = replyid
        msg['References'] = replyid

    # Attach plain text and HTML parts
    if body_text:
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
    if body_html:
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))

    # Send via SMTP SSL
    smtp_server = smtplib.SMTP_SSL(config['smtpServer'], config['smtpPort'])
    try:
        smtp_server.login(config['emailUsername'], config['emailPassword'])
        smtp_server.sendmail(from_address, rcpt_list, msg.as_string())
    finally:
        smtp_server.quit()

