#!/usr/bin/python

# Copyright (c) 2015, Psiphon Inc.
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

from logger import logger
import os
import sys
import re
import time
import settings

from sqlalchemy import create_engine
from sqlalchemy import Column, String, Integer
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()

QUEUE_ID_LENGTH = 10


def now_milliseconds():
    return int(time.time()*1000)

class IncomingMail(Base):
    __tablename__ = 'incoming_mail'
    queue_id = Column(String(QUEUE_ID_LENGTH), primary_key=True)
    created = Column(BIGINT, default=now_milliseconds)
    mailserver2 = Column(String(256))
    mailserver3 = Column(String(256))
    processing_start = Column(BIGINT)
    processing_end = Column(BIGINT)
    size = Column(Integer)

class OutgoingMail(Base):
    __tablename__ = 'outgoing_mail'
    queue_id = Column(String(QUEUE_ID_LENGTH), primary_key=True)
    created = Column(BIGINT, default=now_milliseconds)
    defer_count = Column(Integer, default=0)
    defer_last_reason = Column(String(256))
    size = Column(Integer)
    sent = Column(BIGINT)
    expired = Column(BIGINT)
    mailserver2 = Column(String(256))
    mailserver3 = Column(String(256))

class MailError(Base):
    __tablename__ = 'mail_error'
    id = Column(Integer, primary_key=True)
    created = Column(BIGINT, default=now_milliseconds)
    error_msg = Column(String(256))
    hostname = Column(String(256))
    ip = Column(String(256))


dbengine = create_engine('mysql://%s:%s@localhost/%s' % (settings.DB_USERNAME, settings.DB_PASSWORD, settings.DB_DBNAME))
Base.metadata.create_all(dbengine)
Session = sessionmaker(bind=dbengine)


class LogHandlers(object):

    SUCCESS = 0
    FAILURE = 0
    NO_RECORD_MATCH = 0

    queue_id_matcher = '[0-9A-F]{%s}' % (QUEUE_ID_LENGTH,)

    def __init__(self):

        self.handlers = (
            #
            # See big comment at the bottom of this file for a description
            # of the flow of syslog entries.
            #

            # These tuples are of the form:
            # ( process matcher,
            #   message matcher -- may include capture groups,
            #   handler for the whole log dict
            # )
            # Many of the log handlers are curried calls to _process_error,
            # which is a generic-but-flexible error recorder.

            # Jun 27 19:24:04 myhostname postfix/smtpd[30850]: connect from mail-qa0-f44.google.com[209.85.216.44]
            # Jun 27 19:24:04 myhostname postfix/smtpd[30856]: connect from localhost[127.0.0.1]
            (re.compile(r'^postfix/smtpd$'),
             re.compile(r'^connect from '),
             self._no_op),

            # Jun 27 19:24:04 myhostname postfix/smtpd[30856]: disconnect from localhost[127.0.0.1]
            # Jun 27 19:24:34 myhostname postfix/smtpd[30850]: disconnect from mail-qa0-f44.google.com[209.85.216.44]
            (re.compile(r'^postfix/smtpd$'),
             re.compile(r'^disconnect from '),
             self._no_op),

            # Jun 27 19:24:04 myhostname postfix/smtpd[30850]: 9B578221EA: client=mail-qa0-f44.google.com[209.85.216.44]
            (re.compile(r'^postfix/smtpd$'),
             re.compile(r'^'+self.queue_id_matcher+': client='),
             self._no_op),

            # Jun 27 19:24:04 myhostname postfix/cleanup[30852]: 9B578221EA: message-id=<CAKJcm2Bs+AvgBWnsSMNKRGM9XR+pTFuWrs5xOb5NDnwODA56qw@mail.gmail.com>
            # 2014-04-15T17:39:16.222151+00:00 myhostname postfix/cleanup[31522]: ECBCE4001E: message-id=<20140415173915.ECBCE4001E@localhost>
            (re.compile(r'^postfix/cleanup$'),
             re.compile(r'^'+self.queue_id_matcher+': message-id='),
             self._process_message_id),

            # Jun 27 19:24:04 myhostname postfix/qmgr[821]: 9B578221EA: from=<requesting-address@gmail.com>, size=1880, nrcpt=1 (queue active)
            # Jun 27 19:24:05 myhostname postfix/qmgr[821]: 49A88221ED: from=<complaints@psiphon3.com>, size=1147933, nrcpt=1 (queue active)
            (re.compile(r'^postfix/qmgr$'),
             re.compile(r'^'+self.queue_id_matcher+': from=.*\(queue active\)$'),
             self._process_queue_active),

            # Jun 27 19:24:04 myhostname postfix/smtpd[30856]: DF85B221EB: client=localhost[127.0.0.1]
            (re.compile(r'^postfix/smtpd$'),
             re.compile(r'^'+self.queue_id_matcher+': client=localhost\['),
             self._no_op),

            # Jun 27 19:24:05 myhostname postfix/local[30853]: 9B578221EA: to=<mail_responder+get@localhost>, orig_to=<get@psiphon3.com>, relay=local, delay=0.83, delays=0.06/0.01/0/0.76, dsn=2.0.0, status=sent (delivered to command: python /home/mail_responder/mail_process.py)
            (re.compile(r'^postfix/local$'),
             re.compile(r'^'+self.queue_id_matcher+': to=<mail_responder.*status=sent \(delivered to command'),
             self._process_response_done),

            # Jun 27 19:24:05 myhostname postfix/qmgr[821]: 9B578221EA: removed
            (re.compile(r'^postfix/qmgr$'),
             re.compile(r'^'+self.queue_id_matcher+': removed$'),
             self._no_op),

            # Jun 27 19:24:29 myhostname postfix/smtp[30383]: connect to alt2.aspmx.l.google.com[173.194.65.26]:25: Connection timed out
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^connect to .* Connection timed out$'),
             self._no_op),

            # Jun 27 19:26:35 myhostname postfix/smtp[30407]: DF85B221EB: to=<requesting-address@gmail.com>, relay=none, delay=150, delays=0.02/0/150/0, dsn=4.4.1, status=deferred (connect to aspmx3.googlemail.com[74.125.127.27]:25: Connection timed out)
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': .* status=deferred .*$'),
             self._process_queue_deferred),

            # 2012-07-03T21:28:09.632739+00:00 myhostname postfix/error[7801]: 7A26D22F59: to=<requesting-address@gmail.com>, relay=none, delay=0.13, delays=0.11/0/0/0.02, dsn=4.4.1, status=deferred (delivery temporarily suspended: connect to mta5.am0.yahoodns.net[67.195.168.230]:25: Connection timed out)
            (re.compile(r'^postfix/error'),
             re.compile(r'^'+self.queue_id_matcher+': .* status=deferred .*$'),
             self._process_queue_deferred),

            # Jun 27 19:33:30 myhostname postfix/smtp[2090]: DF85B221EB: to=<requesting-address@gmail.com>, relay=alt1.aspmx.l.google.com[173.194.66.27]:25, delay=566, delays=534/0.18/31/0.69, dsn=2.0.0, status=sent (250 2.0.0 OK 1340825647 z7si13020796wix.11)
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': .* status=sent '),
             self._process_response_sent),

            # 2012-08-01T07:57:52.062087+00:00 myhostname postfix/local[20286]: 0415B22086: to=<user@myhostname>, orig_to=<postmaster>, relay=local, delay=0.05, delays=0.02/0.01/0/0.02, dsn=2.0.0, status=sent (delivered to mailbox)
            (re.compile(r'^postfix/local$'),
             re.compile(r'^'+self.queue_id_matcher+': .* status=sent \(delivered to mailbox\)$'),
             self._process_local_msg_sent),

            # Jun 27 20:48:25 myhostname postfix/qmgr[821]: 5106A215C1: from=<complaints@psiphon3.com>, status=expired, returned to sender
            (re.compile(r'^postfix/qmgr$'),
             re.compile(r'^'+self.queue_id_matcher+': .* status=expired, returned to sender$'),
             self._process_queue_expired),

            # Jun 27 20:48:25 myhostname postfix/bounce[30506]: 5106A215C1: sender non-delivery notification: A887022171
            (re.compile(r'^postfix/bounce$'),
             re.compile(r'^'+self.queue_id_matcher+': sender non-delivery notification: '+self.queue_id_matcher+'$'),
             self._no_op),

            # Jun 27 20:48:25 myhostname postfix/bounce[30506]: 5106A215C1: postmaster non-delivery notification: ABC7122175
            (re.compile(r'^postfix/bounce$'),
             re.compile(r'^'+self.queue_id_matcher+': postmaster non-delivery notification: '+self.queue_id_matcher+'$'),
             self._no_op),

            # Jun 27 19:27:00 myhostname postfix/scache[30430]: statistics: start interval Jun 27 19:23:00
            # Jun 27 19:27:00 myhostname postfix/scache[30430]: statistics: domain lookup hits=1 miss=9 success=10%
            # Jun 27 19:27:00 myhostname postfix/scache[30430]: statistics: address lookup hits=0 miss=216 success=0%
            # Jun 27 19:27:00 myhostname postfix/scache[30430]: statistics: max simultaneous domains=1 addresses=6 connection=7
            (re.compile(r'^postfix/scache$'),
             re.compile(r'.*'),
             self._no_op),

            # 2012-07-03T21:25:06.379278+00:00 myhostname postfix/anvil[4018]: statistics: max connection rate 1/60s for (smtp:<remote-mailserver-ip>) at Jul  3 21:15:06
            # 2012-07-03T21:25:06.379285+00:00 myhostname postfix/anvil[4018]: statistics: max connection count 1 for (smtp:<remote-mailserver-ip>) at Jul  3 21:15:06
            # 2012-07-03T21:25:06.379290+00:00 myhostname postfix/anvil[4018]: statistics: max cache size 3 at Jul  3 21:23:58
            (re.compile(r'^postfix/anvil$'),
             re.compile(r'^statistics: .*'),
             self._no_op),

            # Some Googling suggests that that's some buggy hardware/software
            # out there that choke on DKIM headers. If this happens often we may
            # want to take corrective action.
            # Jun 27 20:48:07 myhostname postfix/smtp[32557]: 5106A215C1: enabling PIX workarounds: disable_esmtp delay_dotcrlf for mail.example.com[aaa.bbb.ccc.ddd]:25
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': enabling PIX workarounds: disable_esmtp delay_dotcrlf for '),
             curry(self._process_error, matcher='(?P<queue_id>'+self.queue_id_matcher+'): (?P<error>.*) for (?P<mail_host>[^\[]+)?\[(?P<mail_ip>[^\[]+)\].*')),

            # 2012-07-09T17:08:58.555820+00:00 myhostname postfix/smtp[21859]: warning: valid_hostname: empty hostname
            (re.compile(r'^postfix/smtp'),
             re.compile(r'^warning: valid_hostname: empty hostname$'),
             curry(self._process_error, matcher='(?P<error>warning: valid_hostname: empty hostname)')),

            # 2012-07-09T17:08:58.562131+00:00 myhostname postfix/smtp[21859]: warning: malformed domain name in resource data of MX record for example.com:
            (re.compile(r'^postfix/smtp'),
             re.compile(r'^warning: malformed domain name in resource data of MX record for .*$'),
             curry(self._process_error, matcher='(?P<error>warning: malformed domain name in resource data of MX record for) (?P<mail_host>[^:]+):')),

            # Jun 28 15:17:59 myhostname postfix/smtp[25037]: warning: numeric domain name in resource data of MX record for example.com: xxx.xxx.xxx.xxx
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^warning: numeric domain name in resource data of MX record for .*$'),
             curry(self._process_error, matcher='(?P<error>warning: numeric domain name in resource data of MX record for) (?P<mail_host>[^:]+): (?P<mail_ip>.+)')),

            # IPv6 fail
            # 2012-07-09T17:28:58.495250+00:00 myhostname postfix/smtp[29941]: connect to gmail-smtp-in-v4v6.l.google.com[2001:4860:800a::1b]:25: Network is unreachable
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^connect to .*: Network is unreachable$'),
             curry(self._process_error, matcher='connect to (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\]:[^:]+: (?P<error>Network is unreachable)')),

            # TODO: This is quite weird and is probably worth figuring out...
            # 2012-07-09T17:48:58.895428+00:00 myhostname postfix/smtp[5614]: warning: host 0.0.0.0[0.0.0.0]:25 replied to HELO/EHLO with my own hostname myhostname.com
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^warning: host 0.0.0.0\[0.0.0.0\]:25 replied to HELO/EHLO with my own hostname .*$'),
             curry(self._process_error, matcher='warning: host (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\]:[^:]+ (<?P<error>replied to HELO/EHLO with my own hostname .*)')),

            # 2012-07-09T17:49:19.182296+00:00 myhostname postfix/smtp[3608]: warning: no MX host for example.com has a valid address record
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^warning: no MX host for .* has a valid address record$'),
             curry(self._process_error,
                   matcher='warning: no MX host for (?P<mail_host>[^ ]+) has a valid address record',
                   error_msg='no MX host has a valid address record')),

            # TODO: Which of these hostnames is the one of interest?
            # 2012-07-09T18:05:20.719276+00:00 myhostname postfix/smtp[11701]: 5AA9D221E8: host mta5.am0.yahoodns.net[98.137.54.238] refused to talk to me: 420 Resources unavailable temporarily. Please try later (mta1060.mail.sp2.yahoo.com)
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': host .* refused to talk to me: 420 Resources unavailable temporarily. Please try later .*'),
             curry(self._process_error,
                   matcher=self.queue_id_matcher+': host .* refused to talk to me: 420 Resources unavailable temporarily. Please try later \((?P<mail_host>[^\)]+)\)',
                   error_msg='host refused to talk to me: 420 Resources unavailable temporarily. Please try later')),

            # 2012-07-09T18:48:58.522400+00:00 myhostname postfix/smtp[27782]: A2EEA21D9D: host example.com[xxx.xxx.xxx.xxx] refused to talk to me: 421 mx.fakemx.net Service Unavailable
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': host .* refused to talk to me: 421 .* Service Unavailable$'),
             curry(self._process_error,
                   matcher=self.queue_id_matcher+': host (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\] refused to talk to me: 421 .* Service Unavailable',
                   error_msg='host refused to talk to me: 421 Service Unavailable')),

            # 2012-07-09T18:17:07.410552+00:00 myhostname postfix/smtp[15734]: 7D56B227ED: host host example.com[xxx.xxx.xxx.xxx] said: 421 Read data from client error (in reply to end of DATA command)
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': host .* said: 421 Read data from client error \(in reply to end of DATA command\)$'),
             curry(self._process_error,
                   matcher=self.queue_id_matcher+': host (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\] said: 421 Read data from client error \(in reply to end of DATA command\)',
                   error_msg='host said: 421 Read data from client error (in reply to end of DATA command)')),

            # 2012-07-09T18:21:14.858498+00:00 myhostname postfix/smtpd[18623]: warning: hostname example.com does not resolve to address xxx.xxx.xxx.xxx: Name or service not known
            (re.compile(r'^postfix/smtpd$'),
             re.compile(r'^warning: hostname .* does not resolve to address .*: Name or service not known$'),
             curry(self._process_error,
                   matcher='warning: hostname (?P<mail_host>[^ ]+) does not resolve to address (?P<mail_ip>[^:]+): Name or service not known',
                   error_msg='hostname does not resolve to address: Name or service not known')),

            # Note that this is a subset of the above test, so needs to come after.
            # 2012-07-10T06:22:20.556358+00:00 myhostname postfix/smtpd[9495]: warning: hostname example.com does not resolve to address xxx.xxx.xxx.xxx
            (re.compile(r'^postfix/smtpd$'),
             re.compile(r'^warning: hostname .* does not resolve to address .*$'),
             curry(self._process_error,
                   matcher='warning: hostname (?P<mail_host>[^ ]+) does not resolve to address (?P<mail_ip>[^:]+)',
                   error_msg='hostname does not resolve to address')),

            # 2014-07-15T19:10:47.569085+00:00 myhostname postfix/smtpd[27435]: NOQUEUE: reject: RCPT from unknown[192.168.xxx.xxx]: 450 4.1.8 <garbage@moregarbage.com>: Sender address rejected: Domain not found; from=<garbage@moregarbage.com> to=<get@example.com> proto=ESMTP helo=<moregarbage.com>
            (re.compile(r'^postfix/smtpd$'),
             re.compile(r'^NOQUEUE: reject: .* Sender address rejected: Domain not found.*$'),
             self._no_op),  # Don't bother recording anything -- junk domain name

            # 2014-07-15T19:10:47.569085+00:00 myhostname postfix/smtpd[27435]: NOQUEUE: reject: RCPT from unknown[192.168.xxx.xxx]: 504 5.5.2 <NS3>: Helo command rejected: need fully-qualified hostname; from=<example@hotmail.com> to=<get@responder.com> proto=SMTP helo=<NS3>
            (re.compile(r'^postfix/smtpd$'),
             re.compile(r'^NOQUEUE: reject: .* Helo command rejected: need fully-qualified hostname.*$'),
             self._no_op),  # Don't bother recording anything -- junk domain name

            # 2012-07-09T18:58:59.121424+00:00 myhostname postfix/smtp[1433]: connect to example.com[xxx.xxx.xxx.xxx]:25: Connection refused
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^connect to [^ ]+: Connection refused$'),
             curry(self._process_error,
                   matcher='connect to (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\]:[^:]+: (<?P<error>Connection refused)')),

            # 2014-07-17T16:10:05.170318+00:00 myhostname postfix/smtp[4826]: connect to example.com[xxx.xxx.xxx.xxx]:25: No route to host
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^connect to [^ ]+: No route to host$'),
             curry(self._process_error,
                   matcher='connect to (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\]:[^:]+: (<?P<error>No route to host)')),

            # 2012-07-10T02:34:33.804361+00:00 myhostname postfix/smtp[7252]: A0AB922459: lost connection with example.com[xxx.xxx.xxx.xxx] while sending DATA command
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': lost connection with .* while sending DATA command$'),
             curry(self._process_error,
                   matcher=self.queue_id_matcher+': lost connection with (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\] while sending DATA command',
                   error_msg='lost connection while sending DATA command')),

            # 2014-07-17T16:15:08.096534+00:00 myhostname postfix/smtp[9398]: A0AB922459: lost connection with example.com[xxx.xxx.xxx.xxx] while performing the HELO handshake
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': lost connection with .* while performing the HELO handshake$'),
             curry(self._process_error,
                   matcher=self.queue_id_matcher+': lost connection with (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\] while performing the HELO handshake',
                   error_msg='lost connection while performing the HELO handshake')),

            # 2012-07-10T02:18:39.518175+00:00 myhostname postfix/smtpd[7056]: lost connection after MAIL from example.com[xxx.xxx.xxx.xxx]
            (re.compile(r'^postfix/smtpd'),
             re.compile(r'^lost connection after MAIL from .*$'),
             curry(self._process_error,
                   matcher='lost connection after MAIL from (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\]',
                   error_msg='lost connection after MAIL')),

            # 2014-07-17T16:08:52.406761+00:00 myhostname postfix/smtpd[28416]: lost connection after DATA (0 bytes) from unknown[192.168.xxx.xxx]
            (re.compile(r'^postfix/smtpd'),
             re.compile(r'^lost connection after DATA .* from .*\[192\.168\..*$'),
             self._no_op),

            # 2012-07-09T21:24:01.343326+00:00 myhostname postfix/smtp[27397]: 05F9C22211: host example.com[xxx.xxx.xxx.xxx] said: 451 Message temporarily deferred - [160] (in reply to end of DATA command)
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': host .* said: 451 Message temporarily deferred - \[160\] \(in reply to end of DATA command\)$'),
             curry(self._process_error,
                   matcher=self.queue_id_matcher+': host (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\] said: 451 Message temporarily deferred - \[160\] \(in reply to end of DATA command\)',
                   error_msg='host said: 451 Message temporarily deferred - [160] (in reply to end of DATA command)')),

            # This log occurs when the load balancer does a health check
            # 2013-10-22T18:15:09.330363+00:00 myhostname postfix/smtpd[28303]: lost connection after CONNECT from unknown[192.168.xx.xx]
            (re.compile(r'^postfix/smtpd'),
             re.compile(r'^lost connection after (CONNECT|RCPT) from unknown\[192\.168\..*$'),
             self._no_op),

            # 2014-07-29T19:44:31.570804+00:00 myhostname postfix/smtpd[1235]: lost connection after EHLO from unknown[192.168.xx.xx]
            # 2014-07-29T19:46:48.452238+00:00 myhostname postfix/smtpd[1235]: lost connection after HELO from unknown[192.168.xx.xx]
            (re.compile(r'^postfix/smtpd'),
             re.compile(r'^lost connection after (EHLO|HELO) from unknown\[192\.168\..*$'),
             self._no_op),

            # 2014-07-28T19:40:30.896235+00:00 myhostname postfix/smtpd[10293]: too many errors after EHLO from unknown[192.168.xx.xx]
            (re.compile(r'^postfix/smtpd'),
             re.compile(r'^too many errors after EHLO from unknown\[192\.168\..*$'),
             self._no_op),

            # 2012-07-10T03:13:34.468267+00:00 myhostname postfix/smtp[7550]: 7961621FE0: conversation with example.com[xxx.xxx.xxx.xxx] timed out while sending message body
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': conversation with .* timed out while sending message body$'),
             curry(self._process_error,
                   matcher=self.queue_id_matcher+': conversation with (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\] timed out while sending message body',
                   error_msg='conversation timed out while sending message body')),

            # 2012-07-10T04:08:58.973288+00:00 myhostname postfix/smtp[8119]: A2EEA21D9D: host example.com[xxx.xxx.xxx.xxx] said: 451 Try again later (in reply to RCPT TO command)
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': host .* said: 451 Try again later \(in reply to RCPT TO command\)$'),
             curry(self._process_error,
                   matcher=self.queue_id_matcher+': host (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\] said: 451 Try again later \(in reply to RCPT TO command\)',
                   error_msg='host said: 451 Try again later (in reply to RCPT TO command)')),

            # 2012-07-10T05:07:07.121468+00:00 myhostname postfix/smtp[8627]: 0DD0722727: conversation with example.com[xxx.xxx.xxx.xxx] timed out while sending message body
            (re.compile(r'^postfix/smtp$'),
             re.compile(r'^'+self.queue_id_matcher+': conversation with .* timed out while sending message body$'),
             curry(self._process_error,
                   matcher=self.queue_id_matcher+': conversation with (?P<mail_host>[^\[]+)\[(?P<mail_ip>[^\]]+)\] timed out while sending message body',
                   error_msg='conversation timed out while sending message body')),

            # 2014-07-17T16:11:06.573236+00:00 myhostname postfix/qmgr[28360]: 0DD0722727: skipped, still being delivered
            (re.compile(r'^postfix/qmgr$'),
             re.compile(r'^'+self.queue_id_matcher+': skipped, still being delivered$'),
             self._no_op),

            )

    def _no_op(self, logdict, dbsession):
        return self.NO_RECORD_MATCH

    def _process_message_id(self, logdict, dbsession):
        '''
        This is hit once, when a new incoming or outgoing mail enters the system.
        If the message-id is for an outgoing email, make note of the queue-id.
        If the message-id is for an incoming email, gather stats for the sending server.
        '''
        m = re.match('^(?P<queue_id>'+self.queue_id_matcher+'): message-id=<[^@]+@(?P<mail_domain>[^>]+)>$',
                     logdict['message'])
        if not m:
            return self.FAILURE
        msgdict = m.groupdict()

        if msgdict['mail_domain'] == 'localhost':
            # Outgoing mail
            mail = OutgoingMail(queue_id=msgdict['queue_id'])
            dbsession.add(mail)
        else:
            # Incoming mail
            # Keep the last two and last three parts of the mail server domain separately
            mailserver2 = '.'.join(msgdict['mail_domain'].split('.')[-2:])[:IncomingMail.mailserver2.property.columns[0].type.length]
            mailserver3 = '.'.join(msgdict['mail_domain'].split('.')[-3:])[:IncomingMail.mailserver3.property.columns[0].type.length]
            mail = IncomingMail(queue_id=msgdict['queue_id'], mailserver2=mailserver2, mailserver3=mailserver3)
            dbsession.add(mail)

        return self.SUCCESS

    def _process_queue_active(self, logdict, dbsession):
        '''
        Process additions to the active queue. This includes incoming mail and outgoing mail.
        We'll be collecting stats about message size.
        For incoming mail, this log is an approximation of when mail_process.py began its work.
        '''
        m = re.match('^(?P<queue_id>'+self.queue_id_matcher+'): from=<(?P<addr>[^>]*)>, size=(?P<size>[0-9]+), .*',
                     logdict['message'])
        if not m: return self.FAILURE
        msgdict = m.groupdict()

        if msgdict['addr'] == settings.COMPLAINTS_ADDRESS:
            # Outgoing mail
            mail = dbsession.query(OutgoingMail).filter_by(queue_id=msgdict['queue_id']).first()
            if not mail: return self.NO_RECORD_MATCH
            mail.size = msgdict['size']
        else:
            # Incoming mail
            mail = dbsession.query(IncomingMail).filter_by(queue_id=msgdict['queue_id']).first()
            if not mail: return self.NO_RECORD_MATCH
            mail.size = msgdict['size']
            mail.processing_start = now_milliseconds()

        return self.SUCCESS

    def _process_response_done(self, logdict, dbsession):
        '''
        Process notification that mail_process.py finished its work.
        Record the time.
        '''
        m = re.match('^(?P<queue_id>'+self.queue_id_matcher+'): .*, orig_to=<(?P<request_address>[^>]+)>, .*',
                     logdict['message'])
        if not m: return self.FAILURE
        msgdict = m.groupdict()

        mail = dbsession.query(IncomingMail).filter_by(queue_id=msgdict['queue_id']).first()
        if not mail: return self.NO_RECORD_MATCH
        mail.processing_end = now_milliseconds()

        return self.SUCCESS

    def _process_queue_deferred(self, logdict, dbsession):
        '''
        Process notification that an outgoing deferral occurred.
        Count the instances.
        '''

        m = re.match('^(?P<queue_id>'+self.queue_id_matcher+'): to=<[^@]+@(?P<mail_domain>[^>]+)>.*(?P<reason>(?:bounce or trace service failure)|(?:Connection timed out)|(?:Host or domain name not found)).*$',
                     logdict['message'])
        if not m: return self.FAILURE
        msgdict = m.groupdict()

        mail = dbsession.query(OutgoingMail).filter_by(queue_id=msgdict['queue_id']).first()
        if not mail: return self.NO_RECORD_MATCH
        mail.defer_count += 1
        mail.defer_last_reason = msgdict['reason']

        mailserver2 = '.'.join(msgdict['mail_domain'].split('.')[-2:])[:OutgoingMail.mailserver2.property.columns[0].type.length]
        mailserver3 = '.'.join(msgdict['mail_domain'].split('.')[-3:])[:OutgoingMail.mailserver3.property.columns[0].type.length]
        mail.mailserver2 = mailserver2
        mail.mailserver3 = mailserver3

        return self.SUCCESS

    def _process_response_sent(self, logdict, dbsession):
        '''
        Response successfully sent. Record the end time.
        '''
        m = re.match('^(?P<queue_id>'+self.queue_id_matcher+'): to=<[^@]+@(?P<mail_domain>[^>]+)>.*',
                     logdict['message'])
        if not m: return self.FAILURE
        msgdict = m.groupdict()

        mail = dbsession.query(OutgoingMail).filter_by(queue_id=msgdict['queue_id']).first()
        if not mail: return self.NO_RECORD_MATCH
        mail.sent = now_milliseconds()

        # Keep the last two and last three parts of the mail server domain separately
        mailserver2 = '.'.join(msgdict['mail_domain'].split('.')[-2:])[:OutgoingMail.mailserver2.property.columns[0].type.length]
        mailserver3 = '.'.join(msgdict['mail_domain'].split('.')[-3:])[:OutgoingMail.mailserver3.property.columns[0].type.length]
        mail.mailserver2 = mailserver2
        mail.mailserver3 = mailserver3

        return self.SUCCESS

    def _process_local_msg_sent(self, logdict, dbsession):
        '''
        A message was sent to the postmaster, /dev/null, or some other local
        account.
        If it was an incorrect request address, we want to record it. Otherwise
        trash it.
        '''
        m = re.match('^(?P<queue_id>'+self.queue_id_matcher+'): to=<(?P<local_addr>[^>]+)>, orig_to=<(?P<orig_addr>[^>]+)>.*',
                     logdict['message'])
        if not m: return self.FAILURE
        msgdict = m.groupdict()

        # If we recorded this as outgoing mail, delete it.
        mail = dbsession.query(OutgoingMail).filter_by(queue_id=msgdict['queue_id']).first()
        if mail:
            dbsession.delete(mail)

        # If this is a bad request address, record it in syslog
        devnull_addr = '%s@localhost' % settings.SYSTEM_DEVNULL_USER
        if msgdict.get('local_addr') == devnull_addr and \
           msgdict.get('orig_addr'):
            logger.info('bad_address: %s', msgdict.get('orig_addr'))

        return self.SUCCESS

    def _process_queue_expired(self, logdict, dbsession):
        '''
        Response sending failed utterly. Record the time.
        '''
        m = re.match('^(?P<queue_id>'+self.queue_id_matcher+'): .*',
                     logdict['message'])
        if not m: return self.FAILURE
        msgdict = m.groupdict()

        mail = dbsession.query(OutgoingMail).filter_by(queue_id=msgdict['queue_id']).first()
        if not mail: return self.NO_RECORD_MATCH
        mail.expired = now_milliseconds()

        return self.SUCCESS

    def _process_error(self, logdict, dbsession, matcher, error_msg=None, mail_host=None, mail_ip=None):
        '''
        Record the error and the mailserver hostname and IP.
        '''
        m = re.match('.*'+matcher+'.*',
                     logdict['message'])
        if not m: return self.FAILURE
        msgdict = m.groupdict()

        error = MailError()

        if msgdict.has_key('error'):
            error_msg = msgdict['error']

        if error_msg:
            error.error_msg = error_msg[:MailError.error_msg.property.columns[0].type.length];

        if msgdict.has_key('mail_host'):
            mail_host = msgdict['mail_host']

        if mail_host:
            error.hostname = mail_host[:MailError.hostname.property.columns[0].type.length]

        if msgdict.has_key('mail_ip'):
            mail_ip = msgdict['mail_ip']

        if mail_ip:
            error.ip = mail_ip[:MailError.ip.property.columns[0].type.length]

        dbsession.add(error)

        return self.SUCCESS


# From: http://code.activestate.com/recipes/52549-curry-associating-parameters-with-a-function/
class curry:
    def __init__(self, fun, *args, **kwargs):
        self.fun = fun
        self.pending = args[:]
        self.kwargs = kwargs.copy()

    def __call__(self, *args, **kwargs):
        if kwargs and self.kwargs:
            kw = self.kwargs.copy()
            kw.update(kwargs)
        else:
            kw = kwargs or self.kwargs

        return self.fun(*(self.pending + args), **kw)

def process_log(log_line):

    # This regex accomodates both default and high-precision date-times.
    # Jun 28 16:11:25
    # 2012-06-28T16:11:25.696983+00:00
    log_regex = re.compile("^(?P<date>(?:[a-zA-Z]{3}\s+\d\d?\s[0-9\:]+)|(?:[0-9T\:\.+-]+))(?:\s(?P<suppliedhost>[a-zA-Z0-9_-]+))?\s(?P<host>[a-zA-Z0-9_-]+)\s(?P<process>[a-zA-Z0-9\/_-]+)(\[(?P<pid>\d+)\])?:\s(?P<message>.+)$")

    log_handlers = LogHandlers()

    log_search_res = log_regex.search(log_line)
    if log_search_res is None:
        return

    logdict = log_search_res.groupdict()

    # Exclude logs created by this process to avoid circular disaster.
    if logdict['process'] == os.path.basename(sys.argv[0]):
        return

    handler_found = False

    for handler in log_handlers.handlers:
        if handler[0].match(logdict['process']) and handler[1].match(logdict['message']):
            dbsession = Session()

            ret = handler[2](logdict, dbsession)

            if ret == LogHandlers.SUCCESS:
                dbsession.commit()
            elif ret == LogHandlers.NO_RECORD_MATCH:
                logger.warning('no record match for: %s', log_line)
                dbsession.rollback()
            else:
                logger.warning('handler failed for: %s', log_line)
                dbsession.rollback()

            handler_found = True
            break

    if not handler_found:
        logger.warning('no handler match found for: %s', log_line)


if __name__ == '__main__':
    while True:
        log_line = sys.stdin.readline()

        # rsyslog's omprog sends an empty string to indicate that the processor should quit.
        if not log_line:
            sys.exit(0)

        try:
            process_log(log_line)
        except:
            logger.error('exception for log: %s', log_line)
            raise


'''
This is a what the syslogs look like for a successful request+response.

Remote (sending) server connects to load balancer, load balancer connects to this mail server.
`2014-04-15T17:39:12.827507+00:00 myhostname postfix/smtpd[4560]: connect from unknown[192.168.1.2]`

Incoming email gets a Postfix queue ID.
`2014-04-15T17:39:13.140250+00:00 myhostname postfix/smtpd[4560]: 2229C4002B: client=unknown[192.168.1.2]`

Message ID is dumped.
`2014-04-15T17:39:13.366300+00:00 myhostname postfix/cleanup[31523]: 2229C4002B: message-id=<CAKJcm2Bs+AvgBWnsSMNKRGM9XR+pTFuWrs5xOb5NDnwODA56qw@mail.gmail.com>`

More message info dumped, including size. Added to active queue.
`2014-04-15T17:39:13.378666+00:00 myhostname postfix/qmgr[6185]: 2229C4002B: from=<requesting-address@gmail.com>, size=1907, nrcpt=1 (queue active)`

Incoming request is done. Connection (via load balancer) disconnects.
`2014-04-15T17:39:13.482943+00:00 myhostname postfix/smtpd[4560]: disconnect from unknown[192.168.11.2]`

At this point the message is sent to our local `mail_responder` user, and via
that user's `.forward` file is piped to our `mail_process.py` code.
The email is processed and responses are enqueued -- one via local SMTP, one via SES.

Response email: connection from `mail_process.py` to localhost SMTP.
`2014-04-15T17:39:15.967663+00:00 myhostname postfix/smtpd[1332]: connect from localhost.localdomain[127.0.0.1]`

Response email: outgoing email gets a queue ID.
`2014-04-15T17:39:15.969840+00:00 myhostname postfix/smtpd[1332]: ECBCE4001E: client=localhost.localdomain[127.0.0.1]`

Response email: outgoing email's message ID is dumped.
`2014-04-15T17:39:16.222151+00:00 myhostname postfix/cleanup[31522]: ECBCE4001E: message-id=<20140415173915.ECBCE4001E@localhost>`

Response email: more info about the outgoing message. Note the large size --
it's our with-attachment response. "complaints@" is the envelope sender address.
`2014-04-15T17:39:16.457547+00:00 myhostname postfix/qmgr[6185]: ECBCE4001E: from=<complaints@example.com>, size=5785168, nrcpt=1 (queue active)`

Response email: local sending/enqueuing is done, so disconnect.
`2014-04-15T17:39:16.466704+00:00 myhostname postfix/smtpd[1332]: disconnect from localhost.localdomain[127.0.0.1]`

`mail_process.py`'s success log. It's done processing and sending.
`2014-04-15T17:39:16.467590+00:00 myhostname mail_process.py: success: get@example.com: 2.762750s`

Delivery and processing of the original request email is done. Info and stats
about it are logged.
`2014-04-15T17:39:16.657286+00:00 myhostname postfix/local[2682]: 2229C4002B: to=<mail_responder@localhost>, orig_to=<get@example.com>, relay=local, delay=3.6, delays=0.34/0/0/3.3, dsn=2.0.0, status=sent (delivered to command: python /home/mail_responder/mail_process.py)`

It's done, so removed from the queue.
`2014-04-15T17:39:16.657565+00:00 myhostname postfix/qmgr[6185]: 2229C4002B: removed`

When delivery of the response (to Gmail or whatever) is done, the response is
removed from the queue.
`2014-04-15T17:39:19.608561+00:00 myhostname postfix/qmgr[6185]: ECBCE4001E: removed`

Info and stats about that delivery are logged.
`2014-04-15T17:39:19.608593+00:00 myhostname postfix/smtp[10443]: ECBCE4001E: to=<requesting-address@gmail.com>, relay=aspmx.l.google.com[74.125.29.27]:25, delay=3.6, delays=0.49/0/0.18/3, dsn=2.0.0, status=sent (250 2.0.0 OK 1397583559 l41si19732640yhc.128 - gsmtp)

...

A request to an invalid address looks like this:

```
2014-04-15T17:51:54.778660+00:00 myhostname postfix/smtpd[10211]: connect from unknown[192.168.11.2]
2014-04-15T17:51:55.097264+00:00 myhostname postfix/smtpd[10211]: 17A3140022: client=unknown[192.168.11.2]
2014-04-15T17:51:55.308560+00:00 myhostname postfix/cleanup[14280]: 17A3140022: message-id=<CAKJcm2DMhDp85kNYKVz+9bA=Lxv9ma1=9sg=nwZ82OcL8iCcNw@mail.gmail.com>
2014-04-15T17:51:55.316845+00:00 myhostname postfix/qmgr[6185]: 17A3140022: from=<requesting-address@gmail.com>, size=1911, nrcpt=1 (queue active)
2014-04-15T17:51:55.324992+00:00 myhostname postfix/local[2509]: 17A3140022: to=<nobody@localhost>, orig_to=<get@example.com>, relay=local, delay=0.33, delays=0.33/0/0/0.01, dsn=2.0.0, status=sent (delivered to mailbox)
2014-04-15T17:51:55.325136+00:00 myhostname postfix/qmgr[6185]: 17A3140022: removed
2014-04-15T17:51:55.330119+00:00 myhostname log_processor.py: bad_address: get@example.com
2014-04-15T17:51:55.420979+00:00 myhostname postfix/smtpd[10211]: disconnect from unknown[192.168.11.2]
```

...

NOTE: What follows pre-dates the change to virtual domains+aliases.

There are probably a bunch of lines like this related to the sending of our respones,
but since the queue ID isn't mentioned, it's impossible to connect them exactly.
`Jun 27 19:24:29 myhostname postfix/smtp[30383]: connect to alt2.aspmx.l.google.com[173.194.65.26]:25: Connection timed out`

Maybe also some lines like this, although there are fewer of them than the above one.
`Jun 27 19:24:34 myhostname postfix/smtpd[30850]: disconnect from mail-qa0-f44.google.com[209.85.216.44]`

Some time later, an attempt to send the first email times out and is put in the deferred queue.
`Jun 27 19:26:35 myhostname postfix/smtp[30407]: DF85B221EB: to=<requesting-address@gmail.com>, relay=none, delay=150, delays=0.02/0/150/0, dsn=4.4.1, status=deferred (connect to aspmx3.googlemail.com[74.125.127.27]:25: Connection timed out)`

Ditto for the second email.
`Jun 27 19:26:35 myhostname postfix/smtp[30389]: 49A88221ED: to=<requesting-address@gmail.com>, relay=none, delay=150, delays=0.14/0/150/0, dsn=4.4.1, status=deferred (connect to aspmx3.googlemail.com[74.125.127.27]:25: Connection timed out)`

Five minutes go by and the first email is moved back into the active queue.
I believe the five minutes comes from the postfix queue_run_delay setting (default 300s).
`Jun 27 19:32:58 myhostname postfix/qmgr[821]: DF85B221EB: from=<complaints@psiphon3.com>, size=5310, nrcpt=1 (queue active)`

Ditto for the second email.
`Jun 27 19:32:58 myhostname postfix/qmgr[821]: 49A88221ED: from=<complaints@psiphon3.com>, size=1147933, nrcpt=1 (queue active)`

A second attempt is made to send the first email. It succeeds.
`Jun 27 19:33:30 myhostname postfix/smtp[2090]: DF85B221EB: to=<requesting-address@gmail.com>, relay=alt1.aspmx.l.google.com[173.194.66.27]:25, delay=566, delays=534/0.18/31/0.69, dsn=2.0.0, status=sent (250 2.0.0 OK 1340825647 z7si13020796wix.11)`

The first email is removed from the queue.
`Jun 27 19:33:30 myhostname postfix/qmgr[821]: DF85B221EB: removed`

Ditto for the second email: sent successfully and removed from queue.
`Jun 27 19:33:32 myhostname postfix/smtp[2092]: 49A88221ED: to=<requesting-address@gmail.com>, relay=alt1.aspmx.l.google.com[173.194.66.27]:25, delay=567, delays=533/0.2/30/3.4, dsn=2.0.0, status=sent (250 2.0.0 OK 1340825648 cp4si13058473wib.14)`
`Jun 27 19:33:32 myhostname postfix/qmgr[821]: 49A88221ED: removed`
'''
