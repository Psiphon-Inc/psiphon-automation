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

'''
Periodically checks the DB for changes and emails information about the change
and the current state.
This could be a cron job, but: a) making it a service allows for the
possibility of dynamic check intervals, and b) we already have a bunch of
services.
'''

import time
import datetime
import yaml
import smtplib
from mako.template import Template
from mako.lookup import TemplateLookup
import pynliner

import logger
from config import config
import sender
import datastore


_SLEEP_TIME_SECS = 300

# Load the templates at startup
_templates = {
    'stats': Template(filename='templates/stats.mako',
                      default_filters=['unicode', 'h'],
                      lookup=TemplateLookup(directories=['.'])),
    'warning': Template(filename='templates/stats_warning.mako',
                        default_filters=['unicode', 'h'],
                        lookup=TemplateLookup(directories=['.'])),
}


def _render_email(template_name, data):
    rendered = _templates[template_name].render(data=data)

    # CSS in email HTML must be inline
    rendered = pynliner.fromString(rendered)

    return rendered


def _send(template_name, data):
    rendered = _render_email(template_name, data)

    try:
        sender.send(config['statsEmailRecipients'],
                    config['emailUsername'],
                    u'FeedbackDecryptor: ' + template_name.capitalize(),
                    yaml.safe_dump(data, default_flow_style=False),
                    rendered)
    except smtplib.SMTPException:
        logger.exception()


def _send_stats_email(last_send_time):
    stats = datastore.get_stats(last_send_time)
    _send('stats', stats)


def _send_warning_email(recs_per_min):
    _send('warning', recs_per_min)


def go():

    last_send_time = datastore.get_stats_last_send_time()

    # This value will basically invalidate the first check, but that's better
    # than a false positive warning every time we start up.
    last_check_time = datetime.datetime.now()

    while True:
        now = datetime.datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Should we warn of bad activity?
        new_count = datastore.get_new_stats_count(last_check_time)
        interval_mins = (now - last_check_time).total_seconds() / 60.0
        recs_per_min = new_count / interval_mins
        if recs_per_min > config['statsWarningThresholdPerMinute']:
            _send_warning_email({'recs_per_min': recs_per_min,
                                 'interval_mins': interval_mins,
                                 'warning_threshold': config['statsWarningThresholdPerMinute']})

        # If we just passed midnight, send the stats email
        if not last_send_time or (last_send_time - midnight).total_seconds() < 0:
            _send_stats_email(last_send_time)
            last_send_time = datetime.datetime.now()
            datastore.set_stats_last_send_time(last_send_time)

        last_check_time = now
        time.sleep(_SLEEP_TIME_SECS)
