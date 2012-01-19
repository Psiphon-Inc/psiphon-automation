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

import psi_build

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Data')))
import psi_db

sys.path.insert(0, os.path.abspath(os.path.join('..', 'Server')))
import psi_config


#==== Config  =================================================================

BUILDS_ROOT = os.path.join('.', 'Builds')

DOWNLOAD_SITE_BUILD_FILENAME = 'psiphon3.exe'

DOWNLOAD_SITE_CONTENT_ROOT = os.path.join('.', 'DownloadSite')

# if psi_build_config.py exists, load it and use psi_build_config.DATA_ROOT as the data root dir
# This file should also contain the EC2 credentials

if os.path.isfile('psi_data_config.py'):
    import psi_data_config
    psi_db.set_db_root(psi_data_config.DATA_ROOT)
    sys.path.insert(0, os.path.abspath(os.path.join(psi_data_config.DATA_ROOT, 'Cloud')))
    import psi_cloud_credentials

#==============================================================================


def publish_s3_download(build_filename):

    # Connect to AWS

    s3 = boto.s3.connection.S3Connection(
                psi_cloud_credentials.EC2_ACCESS_ID,
                psi_cloud_credentials.EC2_SECRET_KEY)

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

    try:
        def progress(complete, total):
            sys.stdout.write('.')
            sys.stdout.flush()
        
        # Upload the download site static content. This include the download page in
        # each available language and the associated images.
        # The download URLs will be the main page referenced by language, for example:
        # https://s3.amazonaws.com/[bucket_id]/en.html
        for name in os.listdir(DOWNLOAD_SITE_CONTENT_ROOT):
            path = os.path.join(DOWNLOAD_SITE_CONTENT_ROOT, name)
            if os.path.isfile(path):
                key = bucket.new_key(name)
                key.set_contents_from_filename(path, cb=progress)
                key.close()
        
        # Upload the specific Propagation Channel/Spondor build as "psiphon3.exe"
    
        key = bucket.new_key(DOWNLOAD_SITE_BUILD_FILENAME)
        path = os.path.join(BUILDS_ROOT, build_filename)
        key.set_contents_from_filename(path, cb=progress)
        key.close()
    except:
        # TODO: delete all keys
        #print 'upload failed, deleting bucket %s' % (bucket_id,)
        #bucket.delete()
        raise

    print ' done'
    
    # Make the whole bucket public now that it's uploaded
    bucket.disable_logging()
    bucket.make_public(recursive=True)

    print 'download URL: https://s3.amazonaws.com/%s/en.html' % (bucket_id)


def publish_s3_downloads(propagation_channel):

    # Create an S3 download site for each Propagation Channel ID/Sponsor ID build that is found
    
    # Match 'psiphon-<Propagation Channel ID>-<Sponsor ID>.exe' with specific propagation channel ID and any sponsor ID
    filename_pattern = re.compile(psi_build.BUILD_FILENAME_TEMPLATE % ('('+propagation_channel.Propagation_Channel_ID+')', '([0-9,A-F]+)'))
 
    for filename in os.listdir(BUILDS_ROOT):
        match = filename_pattern.match(filename)
        if match:
            sponsor_id = match.groups()[1]
            print 'publish S3 download site for propagation channel %s, sponsor %s...' % (
                        propagation_channel.Propagation_Channel_ID,
                        sponsor_id)
            publish_s3_download(filename)


if __name__ == "__main__":

    # TODO: logging for location debugging
    #import logging
    #logging.basicConfig(filename="boto.log", level=logging.DEBUG)

    # Setup S3 download for each propagation channel
    # Assumes builds for each channel have been created

    propagation_channels = psi_db.get_propagation_channels()
    for propagation_channel in propagation_channels:
        publish_s3_downloads(propagation_channel)
