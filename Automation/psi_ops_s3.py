#!/usr/bin/python
#
# Copyright (c) 2011, Psiphon Inc.
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

import os
import sys
import re
import string
import random
import boto.s3.connection
import boto.s3.key
import qrcode
import cStringIO
import hashlib
import mimetypes


#==== Config  =================================================================

DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME = 'psiphon3.exe'
EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME = 'psiphon3.ex_'

DOWNLOAD_SITE_ANDROID_BUILD_FILENAME = 'PsiphonAndroid.apk'
EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME = 'PsiphonAndroid.apk'

DOWNLOAD_SITE_UPGRADE_SUFFIX = '.upgrade'

DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME = 'server_list'

DOWNLOAD_SITE_QR_CODE_FILENAME = 'images/android/android-download-qr.png'

_IGNORE_FILENAMES = ('Thumbs.db',)

#==============================================================================


def get_s3_bucket_resource_url(bucket_id, resource_name):
    # Assumes USEast
    return ('https', 's3.amazonaws.com', "%s/%s" % (
                bucket_id,
                resource_name))


def get_s3_bucket_home_page_url(bucket_id, lang_id='en'):
    # TODO: add a campaign language and direct to that page; or have the client
    # supply its system language and direct to that page.

    # Assumes USEast
    return "https://s3.amazonaws.com/%s/%s.html" % (bucket_id, lang_id)


def create_s3_bucket(aws_account):

    # Connect to AWS

    s3 = boto.s3.connection.S3Connection(
                aws_account.access_id,
                aws_account.secret_key)

    # Seed with /dev/urandom (http://docs.python.org/library/random.html#random.seed)
    random.seed()

    # TODO: select location at random
    location = random.choice([
                    boto.s3.connection.Location.APNortheast,
                    boto.s3.connection.Location.APSoutheast,
                    boto.s3.connection.Location.EU,
                    boto.s3.connection.Location.USWest,
                    boto.s3.connection.Location.DEFAULT]) # DEFAULT = USEast
    # Use default location
    location = boto.s3.connection.Location.DEFAULT

    print 'selected location: %s' % (location,)

    # Generate random bucket ID
    # Note: S3 bucket names can't contain uppercase letters or most symbols
    # Format: XXXX-XXXX-XXXX. Each segment has about 20 bits of entropy
    # (http://en.wikipedia.org/wiki/Password_strength#Random_passwords)
    bucket_id = '-'.join(
        [''.join([random.choice(string.lowercase + string.digits)
                 for j in range(4)])
         for i in range(3)])

    # Create new bucket
    # TODO: retry on boto.exception.S3CreateError: S3Error[409]: Conflict
    bucket = s3.create_bucket(bucket_id, location=location)

    print 'new bucket: https://s3.amazonaws.com/%s/' % (bucket_id)

    return bucket_id


def update_s3_download(aws_account, builds, remote_server_list, bucket_id,
                       custom_download_site, website_dir):

    # Connect to AWS

    s3 = boto.s3.connection.S3Connection(
                aws_account.access_id,
                aws_account.secret_key)

    bucket = s3.get_bucket(bucket_id)

    set_s3_bucket_contents(bucket, builds, remote_server_list,
                           custom_download_site, website_dir)

    print 'updated bucket: https://s3.amazonaws.com/%s/' % (bucket_id)


def set_s3_bucket_contents(bucket, builds, remote_server_list,
                           custom_download_site, website_dir):

    try:
        def progress(complete, total):
            sys.stdout.write('.')
            sys.stdout.flush()

        if builds:
            for (source_filename, target_filename) in builds:
                put_file_to_key(bucket, target_filename, source_filename, progress)

        if remote_server_list:
            put_string_to_key(bucket,
                              DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME,
                              remote_server_list,
                              progress)

        if not custom_download_site:
            for root, dirs, files in os.walk(website_dir):
                for name in files:
                    if name in _IGNORE_FILENAMES:
                        continue
                    file_path = os.path.abspath(os.path.join(root, name))
                    key_name = os.path.relpath(os.path.join(root, name), website_dir).replace('\\', '/')
                    put_file_to_key(bucket, key_name, file_path, progress)

            # We wrote a QR code image in the above upload, but it doesn't
            # point to the Android APK in this bucket. So generate a new one
            # and overwrite.

            qr_code_url = 'https://s3.amazonaws.com/%s/%s' % (
                                bucket.name, DOWNLOAD_SITE_ANDROID_BUILD_FILENAME)
            qr_data = make_qr_code(qr_code_url)
            put_string_to_key(bucket,
                              DOWNLOAD_SITE_QR_CODE_FILENAME,
                              qr_data,
                              progress)

    except:
        # TODO: delete all keys
        #print 'upload failed, deleting bucket'
        #bucket.delete()
        raise

    print ' done'

    bucket.disable_logging()


def put_string_to_key(bucket, key_name, content, callback=None):
    key = bucket.get_key(key_name)
    if key:
        etag = key.etag.strip('"').lower()
        local_etag = hashlib.md5(content).hexdigest().lower()

        if etag == local_etag:
            # key contents haven't changed
            return

    key = bucket.new_key(key_name)
    mimetype = mimetypes.guess_type(key_name)[0]
    if mimetype:
        key.set_metadata('Content-Type', mimetype)
    key.set_contents_from_string(content, policy='public-read', cb=callback)
    key.close()


def put_file_to_key(bucket, key_name, content_file, callback=None):
    """
    `content_file` can be a filename or a file object.
    """
    key = bucket.new_key(key_name)
    if isinstance(content_file, str):
        with open(content_file, 'rb') as f:
          content = f.read()
    else:
        content = content_file.read()

    put_string_to_key(bucket, key_name, content, callback)


def make_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=3, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image()
    stream = cStringIO.StringIO()
    image.save(stream, 'PNG')
    return stream.getvalue()
