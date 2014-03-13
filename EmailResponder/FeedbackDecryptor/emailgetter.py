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


import poplib
import time
import os

import mailparser


_SLEEP_TIME_SECS = 60
_DEBUG = os.environ.get('DEBUG', False)


class EmailGetter():
    def __init__(self, server, port, username, password):
        self._server = server
        self._port = port
        self._username = username
        self._password = password
        self._mailbox = None

    def _connect(self):
        self._disconnect()

        # Connect to the POP3 server
        self._mailbox = poplib.POP3_SSL(self._server, port=self._port)
        self._mailbox.user(self._username)
        self._mailbox.pass_(self._password)

    def _disconnect(self):
        if self._mailbox is not None:
            self._mailbox.quit()
        self._mailbox = None

    def get(self):
        '''
        Generator function that keeps retrieving messages as they are available.
        This will run infinitely -- it sleeps and re-checks when there are no
        more messages.
        '''

        while True:
            if _DEBUG:
                print('emailgetter: checking for messages')

            self._connect()

            # popmail.list() returns a tuple that looks like this:
            # ('+OK 6 messages (21331 bytes)',
            #  ['1 8170', '2 3462', '3 2470', '4 2514', '5 1408', '6 3307'],
            #  56)
            # The message "IDs" are really just 1-based indexes, but we'll
            # treat them as if they're special.
            msg_list = [i.split()[0] for i in self._mailbox.list()[1]]

            # Are the any message available to process?
            if len(msg_list) == 0:
                # No messages. Sleep and try again.
                if _DEBUG:
                    print('emailgetter: no messages; sleeping')

                self._disconnect()
                time.sleep(_SLEEP_TIME_SECS)
                continue

            if _DEBUG:
                print('emailgetter: got %d messages' % len(msg_list))

            try:
                for msg_id in msg_list:
                    # popmail.retr() returns a tuple that looks like this:
                    # ('+OK message follows',
                    #  ['Delivered-To: example@example.com',
                    #   'Received: by a.b.c.d with SMTP id 0123456789abcdef;',
                    #   '        Mon, 22 Oct 2012 14:42:58 -0700 (PDT)',
                    #   ...rest of headers and body...],
                    #  8170)
                    msg = '\n'.join(self._mailbox.retr(msg_id)[1])

                    parsed_msg = mailparser.parse(msg)

                    yield parsed_msg

            finally:
                # We want to call popmail.quit() even if an exception (like a SIGHUP)
                # was thrown from the message processing code. This helps to
                # ensure that the mark-as-read effects of popmail.retr() are committed.
                # Note that this means we might miss a message -- but this is
                # most likely when parsing a message results in an exception,
                # and in that case we *want* to skip it.
                self._disconnect()
