#!/usr/bin/python
#
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
#

import time
import struct
import socket
import math
import collections
import string
import random


def _calculate_bucket_count(length):
    # Number of buckets such that first strategy picks among about the same number
    # of choices as the second strategy. Gives an edge to the "outer" strategy.
    bucket_count = int(math.ceil(math.sqrt(length)))
    return bucket_count


# http://stackoverflow.com/questions/2659900/python-slicing-a-list-into-n-nearly-equal-length-partitions
def _partition(lst, n):
    division = len(lst) / float(n)
    return [ lst[int(round(division * i)): int(round(division * (i + 1)))] for i in xrange(n) ]


def select_servers(servers, ip_address, time_in_seconds=None):

    # Combine client IP address and time-of-day strategies to give out different
    # discovery servers to different clients. The aim is to achieve defense against
    # enumerability. We also want to achieve a degree of load balancing clients
    # and these strategies are expected to have reasonably random distribution,
    # even for a cluster of users coming from the same network.

    # We only select one server: multiple results makes enumeration easier; the
    # strategies have a built-in load balancing effect; and date range discoverability
    # means a client will actually learn more servers later even if they happen to
    # always pick the same result at this point.

    # This is a blended strategy: as long as there are enough servers to pick from,
    # both aspects determine which server is selected. IP address is given the
    # priority: if there are only a couple of servers, for example, IP address alone
    # determines the outcome.

    if len(servers) < 1:
        return []

    # Use the lowest octet of the client's IP address, as
    # discussed in the design document.
    ip_value = struct.unpack('!L',socket.inet_aton(ip_address))[0]

    # Time-of-day is actually current time (epoch) truncated to an hour
    if not time_in_seconds:
        time_in_seconds = int(time.time())
    time_value = (time_in_seconds/3600)

    # Divide servers into buckets. The bucket count is chosen such that the number
    # of buckets and the number of items in each bucket are close (using sqrt).
    # IP address selects the bucket, time selects the item in the bucket.
    
    bucket_count = _calculate_bucket_count(len(servers))

    buckets = _partition(servers, bucket_count)
    bucket = buckets[ip_value % len(buckets)]
    server = bucket[time_value % len(bucket)]

    return [server]


def _test_select_servers():

    tests = [
        ('All IPs in a /8, every minute for 24 hours',
         lambda : ('192.168.0.%d' % (octet,) for octet in xrange(0, 255)),
         lambda : (int(time.time()) + seconds for seconds in xrange(0, 60*60*24, 60))),
        ('192.168.1.0, every minute for 24 hours',
         lambda : (address for address in ('192.168.1.0',)),
         lambda : (int(time.time()) + seconds for seconds in xrange(0, 60*60*24, 60))),
        ('192.168.1.1, every minute for 24 hours',
         lambda : (address for address in ('192.168.1.1',)),
         lambda : (int(time.time()) + seconds for seconds in xrange(0, 60*60*24, 60))),
        ('192.168.1.2, every minute for 24 hours',
         lambda : (address for address in ('192.168.1.2',)),
         lambda : (int(time.time()) + seconds for seconds in xrange(0, 60*60*24, 60))),
        ('192.168.1.3, every minute for 24 hours',
         lambda : (address for address in ('192.168.1.3',)),
         lambda : (int(time.time()) + seconds for seconds in xrange(0, 60*60*24, 60))),
        ('192.168.1.0, every hour for 24 hours',
         lambda : (address for address in ('192.168.1.0',)),
         lambda : (int(time.time()) + seconds for seconds in xrange(0, 60*60*24, 60*60))),
        ('All IPs in a /8, at time 0',
         lambda : ('192.168.0.%d' % (octet,) for octet in xrange(0, 255)),
         lambda : (second for second in (0,))),
        ('All IPs in a /8, at time 1',
         lambda : ('192.168.0.%d' % (octet,) for octet in xrange(0, 255)),
         lambda : (second for second in (60*60*1,))),
        ('All IPs in a /8, at time 2',
         lambda : ('192.168.0.%d' % (octet,) for octet in xrange(0, 255)),
         lambda : (second for second in (60*60*2,))),
        ('All IPs in a /8, at time 3',
         lambda : ('192.168.0.%d' % (octet,) for octet in xrange(0, 255)),
         lambda : (second for second in (60*60*3,))),
        ('A full "/8" with random upper octets, every minute for 24 hours',
         lambda : ('%d.%d.%d.%d' % (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255), octet) for octet in xrange(0, 255)),
         lambda : (int(time.time()) + seconds for seconds in xrange(0, 60*60*24, 60)))
    ]

    for (test_name, ip_addresses, times) in tests:
        print '\n' + test_name + '\n'
        for server_count in range (0, 30):
            servers = list(string.letters[:server_count])
    
            frequency = collections.defaultdict(int)

            for ip_address in ip_addresses():
                for time_in_seconds in times():
                    selection = select_servers(
                                    servers,
                                    ip_address,
                                    time_in_seconds)
                    if selection:
                        frequency[selection[0]] += 1

            if len(servers) > 0:
                print 'servers: %d' % (len(servers),)
                print 'bucket count: %d' % (_calculate_bucket_count(len(servers)),)
                print 'frequencies: ' + ','.join(['%d' % frequency[item] for item in servers])

if __name__ == "__main__":
    _test_select_servers()