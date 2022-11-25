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


from typing import BinaryIO
import os
import errno
import hashlib
import urllib.parse

import psi_ops_s3


#
# S3
#

import boto3


def get_s3_cached_filepath(cache_dir: str, bucketname: str, bucket_filename: str) -> str:
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
    cache_filename = urllib.parse.quote_plus(bucketname+bucket_filename)
    cache_path = os.path.join(cache_dir, cache_filename)
    return cache_path


def get_s3_attachment(attachment_cache_dir: str, bucketname: str, bucket_filename: str) -> BinaryIO:
    '''
    Returns a file-type object for the data.
    '''
    return get_s3_cached_file(attachment_cache_dir, bucketname, bucket_filename)[0]


def get_s3_cached_file(cache_dir: str, bucketname: str, bucket_filename: str) -> tuple[BinaryIO, bool]:
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
    s3 = boto3.resource('s3')

    # `bucketname` may be just a bucket name, or it may be a
    # bucket_name+key_prefix combo. We'll split it up.
    bucketname, key_prefix = psi_ops_s3.split_bucket_id(bucketname)
    bucket_filename = psi_ops_s3.join_key_name(key_prefix, bucket_filename)

    bucket = s3.Bucket(bucketname)
    obj = bucket.Object(bucket_filename)
    etag = obj.e_tag.strip('"').lower()

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
    with open(cache_path, 'wb') as f:
        obj.download_fileobj(f)

    cache_file = open(cache_path, 'rb')

    return (cache_file, True)


def get_s3_string(bucketname, bucket_filename):
    s3 = boto3.resource('s3')
    # `bucketname` may be just a bucket name, or it may be a
    # bucket_name+key_prefix combo. We'll split it up.
    bucketname, key_prefix = psi_ops_s3.split_bucket_id(bucketname)
    bucket_filename = psi_ops_s3.join_key_name(key_prefix, bucket_filename)
    return psi_ops_s3.get_string_from_key(s3.Bucket(bucketname), bucket_filename)


#
# CloudWatch
#

import http.client


_instance_id = None
_autoscaling_group = None


def _get_instance_id():
    global _instance_id
    if not _instance_id:
        # Get the current instace ID. This IP address is magical.
        # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instancedata-data-retrieval.html
        httpconn = http.client.HTTPConnection('169.254.169.254')
        httpconn.request('GET', '/latest/meta-data/instance-id')
        _instance_id = httpconn.getresponse().read()

    return _instance_id;


def _get_autoscaling_group(aws_region):
    '''
    Returns None if the current instance is not in an autoscaling group.
    '''

    # The cached value is None if it hasn't yet been fetched, empty string if there is no
    # autoscaling group, and otherwise the autoscaling group name.
    global _autoscaling_group
    if _autoscaling_group is None:
        # Get the autoscaling group name
        client = boto3.client('autoscaling', region_name=aws_region)
        asi_resp = client.describe_auto_scaling_instances(InstanceIds=[_get_instance_id().decode('utf-8')])
        if len(asi_resp['AutoScalingInstances']) > 0:
            _autoscaling_group = asi_resp['AutoScalingInstances'][0]['AutoScalingGroupName']
        else:
            # This instance is not in an autoscaling group
            _autoscaling_group = ''

    return _autoscaling_group if _autoscaling_group else None


def put_cloudwatch_metric_data(name, value, unit, namespace,
                               aws_region='us-east-1', use_autoscaling_group=True):
    # TODO: Make this more efficient? There are some uses of this function that
    # call it multiple times in succession -- should there be a batch mode?

    metric_data = [{
        'MetricName': name,
        'Value': value,
        'Unit': unit
    }]

    dimensions = None
    if use_autoscaling_group and _get_autoscaling_group(aws_region) is not None:
        for md in metric_data:
            md['Dimensions'] = [{'Name': 'AutoScalingGroupName', 'Value': _get_autoscaling_group(aws_region)}]

    cloudwatch = boto3.client('cloudwatch', region_name=aws_region)
    cloudwatch.put_metric_data(
        Namespace=namespace,
        MetricData=metric_data)
