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


import os
import errno
import hashlib


from boto.s3.connection import S3Connection


def get_s3_attachment(attachment_cache_dir, bucketname, bucket_filename):
    return get_s3_cached_file(attachment_cache_dir, bucketname, bucket_filename)


def get_s3_cached_file(cache_dir, bucketname, bucket_filename):
    '''
    Returns a file-type object for the data in the requested bucket with the
    given filename.
    This function checks if the file has already been downloaded. If it has,
    it checks that the checksum still matches the file in S3. If the file doesn't
    exist, or if it the checksum doesn't match, the
    '''

    # Make the cache dir, if it doesn't exist
    try:
        os.makedirs(cache_dir)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            pass
        else:
            raise

    # Make the connection using the credentials in the boto config file.
    conn = S3Connection()

    # If we don't specify `validate=False`, then this call will attempt to
    # list all keys, which might not be permitted by the bucket (and isn't).
    bucket = conn.get_bucket(bucketname, validate=False)
    key = bucket.get_key(bucket_filename)
    etag = key.etag.strip('"').lower()

    # We store the cached file with the bucket name as the filename
    cache_path = os.path.join(cache_dir, bucketname+bucket_filename)

    # Check if the file exists. If so, check if it's stale.
    if os.path.isfile(cache_path):
        cache_file = open(cache_path, 'rb')
        cache_hex = hashlib.md5(cache_file.read()).hexdigest().lower()

        # Do the hashes match?
        if etag == cache_hex:
            cache_file.seek(0)
            return cache_file

        cache_file.close()

    # The cached file either doesn't exist or is stale.
    cache_file = open(cache_path, 'w')
    key.get_file(cache_file)

    # Close the file and re-open for read-only
    cache_file.close()
    cache_file = open(cache_path, 'rb')

    return cache_file


def get_s3_string(bucketname, bucket_filename):
    conn = S3Connection()
    bucket = conn.get_bucket(bucketname, validate=False)
    key = bucket.get_key(bucket_filename)
    return key.get_contents_as_string()
