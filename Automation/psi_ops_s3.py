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


#==== Config  =================================================================

DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME = 'psiphon3.exe'
EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME = 'psiphon3.ex_'

DOWNLOAD_SITE_ANDROID_BUILD_FILENAME = 'PsiphonAndroid.apk'
EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME = 'PsiphonAndroid.apk'

DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME = 'server_list'

DOWNLOAD_SITE_QR_CODE_FILENAME = 'qr.png'

DOWNLOAD_SITE_CONTENT_ROOT = os.path.join('.', 'DownloadSite')

#==============================================================================


def get_s3_bucket_remote_server_list_url(bucket_id):
    # Assumes USEast
    return ('https', 's3.amazonaws.com', "%s/%s" % (
                bucket_id,
                DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME))


def get_s3_bucket_home_page_url(bucket_id):
    # TODO: add a campaign language and direct to that page; or have the client
    # supply its system language and direct to that page.

    # Assumes USEast
    return "https://s3.amazonaws.com/%s/en.html" % (bucket_id,)


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
    
    print 'new download URL: https://s3.amazonaws.com/%s/en.html' % (bucket_id)

    return bucket_id


def update_s3_download(aws_account, builds, remote_server_list, bucket_id):
    
    # Connect to AWS

    s3 = boto.s3.connection.S3Connection(
                aws_account.access_id,
                aws_account.secret_key)
                
    bucket = s3.get_bucket(bucket_id)
    
    set_s3_bucket_contents(bucket, bucket_id, builds, remote_server_list)

    print 'updated download URL: https://s3.amazonaws.com/%s/en.html' % (bucket_id)
    
    
def set_s3_bucket_contents(bucket, bucket_id, builds, remote_server_list):

    try:
        def progress(complete, total):
            sys.stdout.write('.')
            sys.stdout.flush()
        
        if builds:
            for (source_filename, target_filename) in builds:        
                key = bucket.new_key(target_filename)
                key.set_contents_from_filename(source_filename, cb=progress)
                key.close()

        if remote_server_list:
            key = bucket.new_key(DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME)
            key.set_contents_from_string(remote_server_list, cb=progress)
            key.close()

        # QR code image points to Android APK
        
        qr_code_url = 'https://s3.amazonaws.com/%s/%s' % (
                            bucket_id, DOWNLOAD_SITE_ANDROID_BUILD_FILENAME)

        key = bucket.new_key(DOWNLOAD_SITE_QR_CODE_FILENAME)
        key.set_contents_from_string(make_qr_code(qr_code_url), cb=progress)
        key.close()

        # Update the HTML after the builds, to ensure items it references exist

        # Upload the download site static content. This include the download page in
        # each available language and the associated images.
        # The download URLs will be the main page referenced by language, for example:
        # https://s3.amazonaws.com/[bucket_id]/en.html
        for name in os.listdir(DOWNLOAD_SITE_CONTENT_ROOT):
            path = os.path.join(DOWNLOAD_SITE_CONTENT_ROOT, name)
            if (os.path.isfile(path) and
                os.path.split(path)[1] != DOWNLOAD_SITE_QR_CODE_FILENAME):
                key = bucket.new_key(name)
                key.set_contents_from_filename(path, cb=progress)
                key.close()

    except:
        # TODO: delete all keys
        #print 'upload failed, deleting bucket'
        #bucket.delete()
        raise

    print ' done'
    
    # Make the whole bucket public now that it's uploaded
    bucket.disable_logging()
    bucket.make_public(recursive=True)


def make_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=3, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image()
    stream = cStringIO.StringIO()
    image.save(stream, 'PNG')
    return stream.getvalue()
