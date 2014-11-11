# -*- coding: utf-8 -*-

# Copyright (c) 2014, Psiphon Inc.
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


import os
import errno
import hashlib
import urllib

import psi_ops_s3


#
# S3
#

from boto.s3.connection import S3Connection


def get_s3_cached_filepath(cache_dir, bucketname, bucket_filename):
    '''
    Returns the path and name of the file where a cached file would be stored.
    '''

    # Make the cache dir, if it doesn't exist
    try:
        os.makedirs(cache_dir)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            pass
        else:
            raise

    # We store the cached file with the bucket name as the filename.
    # URL encoding the filename is a bit of a hack, but is good enough for our
    # purposes.
    cache_filename = urllib.quote_plus(bucketname+bucket_filename)
    cache_path = os.path.join(cache_dir, cache_filename)
    return cache_path


def get_s3_attachment(attachment_cache_dir, bucketname, bucket_filename):
    '''
    Returns a file-type object for the data.
    '''
    return get_s3_cached_file(attachment_cache_dir, bucketname, bucket_filename)[0]


def get_s3_cached_file(cache_dir, bucketname, bucket_filename):
    '''
    Returns a tuple of the file-type object for the data and a boolean indicating
    if this data is new (not from the cache).
    This function checks if the file has already been downloaded. If it has,
    it checks that the checksum still matches the file in S3. If the file doesn't
    exist, or if it the checksum doesn't match, the file is downloaded and
    cached to disk.
    '''

    cache_path = get_s3_cached_filepath(cache_dir, bucketname, bucket_filename)

    # Make the connection using the credentials in the boto config file.
    conn = S3Connection()

    # `bucketname` may be just a bucket name, or it may be a
    # bucket_name+key_prefix combo. We'll split it up.
    bucketname, key_prefix = psi_ops_s3.split_bucket_id(bucketname)
    bucket_filename = '%s/%s' % (key_prefix, bucket_filename)

    # If we don't specify `validate=False`, then this call will attempt to
    # list all keys, which might not be permitted by the bucket (and isn't).
    bucket = conn.get_bucket(bucketname, validate=False)
    key = bucket.get_key(bucket_filename)
    etag = key.etag.strip('"').lower()

    # Check if the file exists. If so, check if it's stale.
    if os.path.isfile(cache_path):
        cache_file = open(cache_path, 'rb')
        cache_hex = hashlib.md5(cache_file.read()).hexdigest().lower()

        # Do the hashes match?
        if etag == cache_hex:
            cache_file.seek(0)
            return (cache_file, False)

        cache_file.close()

    # The cached file either doesn't exist or is stale.
    cache_file = open(cache_path, 'w')
    key.get_file(cache_file)

    # Close the file and re-open for read-only
    cache_file.close()
    cache_file = open(cache_path, 'rb')

    return (cache_file, True)


def get_s3_string(bucketname, bucket_filename):
    conn = S3Connection()

    # `bucketname` may be just a bucket name, or it may be a
    # bucket_name+key_prefix combo. We'll split it up.
    bucketname, key_prefix = psi_ops_s3.split_bucket_id(bucketname)
    bucket_filename = '%s/%s' % (key_prefix, bucket_filename)

    bucket = conn.get_bucket(bucketname, validate=False)
    key = bucket.get_key(bucket_filename)
    return key.get_contents_as_string()


#
# CloudWatch
#

from boto.ec2 import EC2Connection
from boto.ec2.cloudwatch import CloudWatchConnection
import httplib


_instance_id = None
_autoscaling_group = None


def _get_instance_id():
    global _instance_id
    if not _instance_id:
        # Get the current instace ID. This IP address is magical.
        httpconn = httplib.HTTPConnection('169.254.169.254')
        httpconn.request('GET', '/latest/meta-data/instance-id')
        _instance_id = httpconn.getresponse().read()

    return _instance_id;


def _get_autoscaling_group():
    '''
    Returns None if the current instance is not in an autoscaling group.
    '''

    global _autoscaling_group
    if not _autoscaling_group:
        # Get the autoscaling group name
        ec2conn = EC2Connection()
        tags = ec2conn.get_all_tags({ 'key': 'aws:autoscaling:groupName',
                                      'resource-id': _get_instance_id() })
        _autoscaling_group = tags[0].value if tags else None

    return _autoscaling_group


def put_cloudwatch_metric_data(name, value, unit, namespace,
                               use_autoscaling_group=True):
    # TODO: Make this more efficient? There are some uses of this function that
    # call it multiple times in succession -- should there be a batch mode?

    dimensions = None
    if use_autoscaling_group:
        autoscaling_group = _get_autoscaling_group()
        dimensions = { 'AutoScalingGroupName': autoscaling_group } if autoscaling_group else None

    cloudwatch = CloudWatchConnection()
    cloudwatch.put_metric_data(namespace,
                               name,
                               value,
                               unit=unit,
                               dimensions=dimensions)
