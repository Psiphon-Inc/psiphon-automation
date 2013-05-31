# Copyright (c) 2013, Psiphon Inc.
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


import time

import datastore


_SLEEP_TIME_SECS = 60


def _diagnostic_record_iter():
    while True:
        for rec in datastore.get_autoresponder_diagnostic_info_iterator():
            yield rec

    time.sleep(_SLEEP_TIME_SECS)


def go():
    emailgetter = EmailGetter(config['popServer'],
                              config['popPort'],
                              config['emailUsername'],
                              config['emailPassword'])

    # Note that `_diagnostic_record_iter` throttles itself if/when there are
    # no records to process.
    for rec in _diagnostic_record_iter():

        # For now we don't do any interesting processing/analysis and we just
        # respond to every feedback with an exhortation to upgrade.
