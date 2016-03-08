#!/usr/bin/python
#
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
#

import os
import sys
import string
import random
import cStringIO
import hashlib
import mimetypes
import base64
import json
import urlparse

import boto.s3.connection
import boto.s3.key

try:
    import qrcode
except ImportError as error:
    print error


#==== Config  =================================================================

# It is expected that the `DOWNLOAD_SITE_BUCKET` will exist and will have a
# bucket policy something like this:
'''
{
    "Id": "Policy1234",
    "Statement": [
        {
            "Sid": "Stmt1234",
            "Action": [
                "s3:GetObject"
            ],
            "Effect": "Allow",
            "Resource": "arn:aws:s3:::psiphon/web/*",
            "Principal": {
                "AWS": [
                    "*"
                ]
            }
        }
    ]
}
'''
DOWNLOAD_SITE_BUCKET = 'psiphon'
DOWNLOAD_SITE_PREFIX = 'web'
DOWNLOAD_SITE_SCHEME = 'https'
DOWNLOAD_SITE_HOSTNAME = 's3.amazonaws.com'

DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME = 'psiphon3.exe'
EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME = 'psiphon3.ex_'

DOWNLOAD_SITE_ANDROID_BUILD_FILENAME = 'PsiphonAndroid.apk'
EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME = 'PsiphonAndroid.apk'

DOWNLOAD_SITE_UPGRADE_SUFFIX = '.upgrade'

DOWNLOAD_SITE_CLIENT_VERSION_METADATA_NAME = 'psiphon-client-version'

DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME = 'server_list'

DOWNLOAD_SITE_QR_CODE_KEY_NAME = 'images/android/android-download-qr.png'

DOWNLOAD_SITE_SPONSOR_BANNER_KEY_NAME = 'images/sponsor-banner.png'
DOWNLOAD_SITE_SPONSOR_BANNER_LINK_KEY_NAME = 'images/sponsor-banner-link.json'
DOWNLOAD_SITE_EMAIL_ADDRESS_KEY_NAME = 'images/sponsor-email.json'

ROUTES_BUCKET_ID = 'psiphon'
ROUTES_KEY_PREFIX = 'routes'

_IGNORE_FILENAMES = ('Thumbs.db',)

#==============================================================================

# Note about bucket names: Once upon a time, each `SponsorCampaign` website (or
# "download site") had its own bucket, but we hit the bucket limit and had to
# change to hosting multiple websites in a single bucket. So sometimes
# `bucket_id` will be a bucket and sometime it will be a bucket+key_prefix.
# Note: The key_prefix does *not* end with a forward slash -- it will need to be
# added when used. This doesn't make a lot of sense from the point of view of
# S3 bucket key names, but it makes handling the values saner -- more like URL
# manipulation.
# But also note: These helper functions are *not* specific to `SponsorCampaign`.
# They can be, and are, used to write to other buckets for other purposes (like
# putting the email responder configuration in the automation bucket.)


def _progress(complete, total):
    sys.stdout.write('.')
    sys.stdout.flush()


def _get_s3_bucket_and_prefix(aws_account, bucket_id):
    """Based on the bucket_id, gets the actual bucket object and the key prefix
    to use.
    Returns:
        tuple of (boto S3 bucket object, key_prefix). key_prefix may be an emtpy
            string.
    """

    s3 = boto.connect_s3(
                aws_account.access_id,
                aws_account.secret_key)

    bucket_name, key_prefix = split_bucket_id(bucket_id)

    bucket = s3.get_bucket(bucket_name)

    return (bucket, key_prefix)


def _delete_key(bucket, key_name):
    """A "safe" S3 key delete helper.
    Fails silently if there is no such key.
    Args:
        bucket (S3 bucket object)
        key_name (str)
    """
    key = bucket.get_key(key_name)
    if key:
        key.delete()


def _make_full_key_name(key_prefix, key_name):
    """Helper to create full key name with optional prefix.
    Args:
        key_prefix (str): May be empty string.
        key_name (str)
    Returns:
        str
    """
    if key_prefix:
        return '%s/%s' % (key_prefix, key_name)
    else:
        return key_name


def split_bucket_id(bucket_id):
    """Convert old- or new-style bucket_id into (bucket_name, key_prefix).
    Returns:
        tuple of (bucket_name, key_prefix). bucket_name will always be a
            non-empty string, but key_prefix may be an empty string.
    """
    bucket_id = bucket_id.strip('/')
    pieces = bucket_id.split('/')
    bucket_name = pieces.pop(0)
    key_prefix = '/'.join(pieces)

    return (bucket_name, key_prefix)


def get_s3_bucket_site_root(bucket_id):
    """Get the base of the URL for resources in this bucket's website.
    Args:
        bucket_id (str): Old- or new-style bucket name.
    Returns:
        str: The root of the URL. Will *not* end with a trailing slash.
    """

    root = '%s://%s/%s' % (DOWNLOAD_SITE_SCHEME, DOWNLOAD_SITE_HOSTNAME, bucket_id)
    root.strip('/')
    return root


def get_s3_bucket_resource_url_split(bucket_id, resource_name):
    """Gets S3 URL components for the given `bucket_id` and `resource_name`.
    Compatible with `urlparse.urlunsplit`.
    Args:
        bucket_id (str): Old- or new-style bucket name.
        resource_name (str): Path is assumed to be starting from the root of the
                             bucket (or new-style bucket+key_prefix), whether or
                             not it starts with a '/'.
    Returns:
        tuple of `(scheme, hostname, path, query, fragment)`
    """

    resource_name = resource_name.lstrip('/')

    root = get_s3_bucket_site_root(bucket_id)

    # Sometimes `bucket_id` will be a hostname+key_prefix, and sometimes
    # `resource_name` will include a query parameter or fragment, so we need to
    # construct the URL and then split it.
    url = '%s/%s' % (root, resource_name)

    return urlparse.urlsplit(url)


def get_s3_bucket_home_page_url(bucket_id, language=None):
    """Get the URL of the main page for the given `bucket_id`.
    Args:
        bucket_id (str): Old- or new-style bucket name.
        language (str): The language code of the desired home page. `None`, the
                        base redirect page (which attempts some crude language
                        detection) will be used.
    Returns:
        URL (str): Absolute URL.
    """

    # TODO: Add a campaign language and direct to that page; or have the client
    # supply its system language and direct to that page.

    if language:
        page = '%s/index.html' % (language,)
    else:
        page = 'index.html'

    url_split = get_s3_bucket_resource_url_split(bucket_id, page)
    return urlparse.urlunsplit(url_split)


def get_s3_bucket_download_page_url(bucket_id, lang='en'):
    """
    Args:
        bucket_id (str): Old- or new-style bucket name.
        language (str): The language code indicating the desired language of the
                       page.
    Returns:
        URL (str): Absolute URL.
    """

    page = '%s/download.html#direct' % (lang,)
    url_split = get_s3_bucket_resource_url_split(bucket_id, page)
    return urlparse.urlunsplit(url_split)


def get_s3_bucket_faq_url(bucket_id, lang='en'):
    """
    Args:
        bucket_id (str): Old- or new-style bucket name.
        language (str): The language code indicating the desired language of the
                       page.
    Returns:
        URL (str): Absolute URL.
    """

    page = '%s/faq.html' % (lang,)
    url_split = get_s3_bucket_resource_url_split(bucket_id, page)
    return urlparse.urlunsplit(url_split)


def get_s3_bucket_privacy_policy_url(bucket_id, lang='en'):
    """
    Args:
        bucket_id (str): Old- or new-style bucket name.
        language (str): The language code indicating the desired language of the
                       page.
    Returns:
        URL (str): Absolute URL.
    """

    page = '%s/privacy.html#information-collected' % (lang,)
    url_split = get_s3_bucket_resource_url_split(bucket_id, page)
    return urlparse.urlunsplit(url_split)


def create_s3_website_bucket_name():
    """Create the bucket+key_prefix value that should be used for a new
    SponsorCampaign website.

    Returns:
        str with new bucket name to use. (This will be a new-style
            bucket+prefix_key.)
    """

    # Seed with /dev/urandom (http://docs.python.org/library/random.html#random.seed)
    random.seed()

    # Generate random ID
    # Note: We're going to avoid symbols so as to remain a valid URL.
    # Format: XXXX-XXXX-XXXX. Each segment has about 20 bits of entropy
    # (http://en.wikipedia.org/wiki/Password_strength#Random_passwords)
    website_id = '-'.join(
        [''.join([random.choice(string.lowercase + string.digits)
                 for j in range(4)])
         for i in range(3)])

    # Note: We are not checking for a duplicate website_id. We don't expect that
    # to reasonably happen, ever.

    bucket_and_prefix = '%s/%s/%s' % (DOWNLOAD_SITE_BUCKET,
                                      DOWNLOAD_SITE_PREFIX,
                                      website_id)

    return bucket_and_prefix


def update_s3_download(aws_account, builds, remote_server_list, bucket_id):
    """Update the client builds and server list in the given bucket.
    Args:
        aws_account (object): Must have attributes access_id and secret_key.
        builds (iterable): List of tuples of (source_filename, version, target_filename).
            May be None.
        remote_server_list (str): The contents of the server_list file.
        bucket_id (str): The bucket to write the files to. Maybe be old- or
            new-style (bucket+key_prefix).
    Returns:
        None
    """

    bucket, key_prefix = _get_s3_bucket_and_prefix(aws_account, bucket_id)

    if builds:
        for (source_filename, version, target_filename) in builds:
            target_filename = _make_full_key_name(key_prefix, target_filename)
            put_file_to_key(bucket,
                            target_filename,
                            {DOWNLOAD_SITE_CLIENT_VERSION_METADATA_NAME : str(version)},
                            str(source_filename),
                            True,
                            _progress)


    if remote_server_list:
        target_filename = _make_full_key_name(key_prefix,
                                              DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME)
        put_string_to_key(bucket,
                          target_filename,
                          None,
                          remote_server_list,
                          True,
                          _progress)


def update_website(aws_account, bucket_id, custom_site, website_dir,
                   website_banner_base64, website_banner_link,
                   website_email_address):
    if custom_site:
        print('not updating website due to custom site in bucket: https://s3.amazonaws.com/%s/' % bucket_id)
        return

    bucket, key_prefix = _get_s3_bucket_and_prefix(aws_account, bucket_id)

    try:
        for root, dirs, files in os.walk(website_dir):
            for name in files:
                if name in _IGNORE_FILENAMES:
                    continue
                file_path = os.path.abspath(os.path.join(root, name))

                # Get key name without prefix
                key_name = os.path.relpath(os.path.join(root, name), website_dir)\
                                  .replace('\\', '/')
                # Add prefix
                key_name = _make_full_key_name(key_prefix, key_name)

                put_file_to_key(bucket, key_name, file_path, True, _progress)

        # Sponsors have optional custom banner images
        banner_key_name = _make_full_key_name(key_prefix,
                                              DOWNLOAD_SITE_SPONSOR_BANNER_KEY_NAME)
        if website_banner_base64:
            put_string_to_key(bucket,
                              banner_key_name,
                              None,
                              base64.b64decode(website_banner_base64),
                              True,
                              _progress)
        else:
            # We need to make sure there's no old sponsor banner in the bucket.
            # Fails silently if there's no such key.
            _delete_key(bucket, banner_key_name)

        # Sponsor banner can optionally link to somewhere.
        banner_link_key_name = _make_full_key_name(key_prefix,
                                                   DOWNLOAD_SITE_SPONSOR_BANNER_LINK_KEY_NAME)
        if website_banner_link:
            put_string_to_key(bucket,
                              banner_link_key_name,
                              None,
                              json.dumps(website_banner_link),
                              True,
                              _progress)
        else:
            # We need to make sure there's no old sponsor banner link in the bucket.
            # Fails silently if there's no such key.
            _delete_key(bucket, banner_link_key_name)

        # If sponsor/campaign has a specific email request address, we'll store
        # that in the bucket for the site to use.
        website_email_address_key_name = _make_full_key_name(key_prefix,
                                                             DOWNLOAD_SITE_EMAIL_ADDRESS_KEY_NAME)
        if website_email_address:
            put_string_to_key(bucket,
                              website_email_address_key_name,
                              None,
                              json.dumps(website_email_address),
                              True,
                              _progress)
        else:
            # We need to make sure there's no old campaign email address in the bucket.
            # Fails silently if there's no such key.
            _delete_key(bucket, website_email_address_key_name)

        # We wrote a QR code image in the above upload, but it doesn't
        # point to the Android APK in this bucket. So generate a new one
        # and overwrite.

        android_build_key_name = _make_full_key_name(key_prefix,
                                                     DOWNLOAD_SITE_ANDROID_BUILD_FILENAME)
        qr_code_url_split = get_s3_bucket_resource_url_split(bucket.name,
                                                             android_build_key_name)
        qr_code_url = urlparse.urlunsplit(qr_code_url_split)
        qr_data = make_qr_code(qr_code_url)
        qr_code_key_name = _make_full_key_name(key_prefix,
                                               DOWNLOAD_SITE_QR_CODE_KEY_NAME)
        put_string_to_key(bucket,
                          qr_code_key_name,
                          None,
                          qr_data,
                          True,
                          _progress)

    except:
        # TODO: delete all keys
        #print 'upload failed, deleting bucket'
        #bucket.delete()
        raise

    print('updated website in bucket: %s' % bucket_id)


def put_string_to_key_in_bucket(aws_account, bucket_id, key_name, content, is_public):
    bucket, key_prefix = _get_s3_bucket_and_prefix(aws_account, bucket_id)

    put_string_to_key(bucket,
                      _make_full_key_name(key_prefix, key_name),
                      None,
                      content,
                      is_public)


def put_string_to_key(bucket, key_name, metadata, content, is_public, callback=None):
    """Write string to key in S3 bucket. If contents of existing key are
    unchanged, there will be no modification.
    Params:
        bucket (boto.s3 object): The bucket to write to.
        key_name (str): The key to write to (must include any applicable prefix).
        metadata (dict[str, str]): Set of metadata to set for key. Only set when key changes.
        content (str): The content to write to the key.
        is_public (bool): Whether the new object should be publicly readable.
        callback (function): An optional progress callback.
    """
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

    if metadata:
        for name, value in metadata.iteritems():
            key.set_metadata(name, value)

    policy = 'public-read' if is_public else None

    key.set_contents_from_string(content, policy=policy, cb=callback)
    key.close()


def put_file_to_key(bucket, key_name, metadata, content_file, is_public, callback=None):
    """Write file contents to key in S3 bucket.
    Note that file will be read into memory before writing.
    Params:
        bucket (boto.s3 object): The bucket to write to.
        key_name (str): The key to write to (must include any applicable prefix).
        metadata (dict[str, str]): Set of metadata to set for key. Only set when key changes.
        content_file (str): The content to write to the key; can be a filename
            or a file object.
        is_public (bool): Whether the new object should be publicly readable.
        callback (function): An optional progress callback.
    """
    if isinstance(content_file, str):
        with open(content_file, 'rb') as f:
          content = f.read()
    else:
        content = content_file.read()

    put_string_to_key(bucket, key_name, metadata, content, is_public, callback)


def make_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=3, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image()
    stream = cStringIO.StringIO()
    image.save(stream, 'PNG')
    return stream.getvalue()

def upload_signed_routes(aws_account, routes_dir, file_extension):
    bucket, key_prefix = _get_s3_bucket_and_prefix(aws_account, ROUTES_BUCKET_ID)
    try:
        for root, dirs, files in os.walk(routes_dir):
            for name in files:
                if not name.endswith(file_extension):
                    continue
                file_path = os.path.abspath(os.path.join(root, name))

                # Get key name without prefix
                key_name = os.path.relpath(os.path.join(root, name), routes_dir)\
                        .replace('\\', '/')
                # Add prefix
                key_name = _make_full_key_name(ROUTES_KEY_PREFIX, key_name)

                put_file_to_key(bucket, key_name, file_path, True, _progress)

    except:
        raise

#
# TESTS ========================================================================
#


import unittest


class Test(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(Test, self).__init__(*args, **kwargs)

        import collections

        self.old_style_bucket_id = 'abcd-efgh-ijkl'
        self.new_style_bucket_id = '%s/%s/%s' % (DOWNLOAD_SITE_BUCKET,
                                                 DOWNLOAD_SITE_PREFIX,
                                                 self.old_style_bucket_id)
        self.aws_creds = collections.namedtuple('AwsCreds', ['access_id', 'secret_key'])('abc', 'xyz')
        self.mock_s3 = None
        self.s3 = None

    from contextlib import contextmanager
    @contextmanager
    def setUpTearDown(self):
        self.setUp()
        yield
        self.tearDown()

    @classmethod
    def setUpClass(cls):
        import tempfile, os, errno
        fd, path = tempfile.mkstemp()
        file = os.fdopen(fd, 'w')
        file.write('I am a file')
        file.close()

        cls.temp_file_path = path

        # Write some stuff into a fake website dir
        cls.temp_website_dir = tempfile.mkdtemp()
        cls.website_files = ['index.html', 'en/index.html', 'aaa/bbb/ccc.js']
        for fname in cls.website_files:
            fname = os.path.normpath(os.path.join(cls.temp_website_dir, fname))
            dirname = os.path.dirname(fname)
            try:
                os.makedirs(dirname)
            except OSError as exc: # Python >2.5
                if exc.errno == errno.EEXIST and os.path.isdir(dirname):
                    pass
                else: raise

            with open(fname, 'w') as file:
                file.write('test')

    @classmethod
    def tearDownClass(cls):
        import os, shutil
        os.unlink(cls.temp_file_path)
        shutil.rmtree(cls.temp_website_dir)

    def setUp(self):
        from moto import mock_s3
        self.mock_s3 = mock_s3()
        self.mock_s3.start()

        # Make our fake bucket
        self.s3 = boto.connect_s3(self.aws_creds.access_id,
                                  self.aws_creds.secret_key)
        self.s3.create_bucket(self.old_style_bucket_id)
        self.s3.create_bucket(DOWNLOAD_SITE_BUCKET)

    def tearDown(self):
        if self.mock_s3:
            self.mock_s3.stop()
            self.mock_s3 = None


    def test_split_bucket_id(self):
        bucket_name, key_prefix = split_bucket_id(self.old_style_bucket_id)
        self.assertEqual(bucket_name, self.old_style_bucket_id)
        self.assertEqual(key_prefix, '')

        bucket_name, key_prefix = split_bucket_id(self.new_style_bucket_id)
        self.assertEqual(bucket_name, DOWNLOAD_SITE_BUCKET)
        self.assertEqual(key_prefix, _make_full_key_name(DOWNLOAD_SITE_PREFIX,
                                                         self.old_style_bucket_id))

    def test_get_s3_bucket_and_prefix(self):
        bucket, key_prefix = _get_s3_bucket_and_prefix(self.aws_creds,
                                                       self.old_style_bucket_id)
        self.assertEqual(bucket.name, self.old_style_bucket_id)
        self.assertEqual(key_prefix, '')

        bucket, key_prefix = _get_s3_bucket_and_prefix(self.aws_creds,
                                                       self.new_style_bucket_id)
        self.assertEqual(bucket.name, DOWNLOAD_SITE_BUCKET)
        self.assertEqual(key_prefix, _make_full_key_name(DOWNLOAD_SITE_PREFIX,
                                                         self.old_style_bucket_id))

    def test_delete_key(self):
        bucket = self.s3.get_bucket(self.old_style_bucket_id)
        key = bucket.new_key('testkey')
        key.set_contents_from_string('test')
        key.close()
        self.assertEqual([key.name for key in bucket.get_all_keys()], ['testkey'])
        _delete_key(bucket, 'testkey')
        self.assertEqual([key.name for key in bucket.get_all_keys()], [])

    def test_make_full_key_name(self):
        self.assertEqual(_make_full_key_name('', 'keyname'), 'keyname')
        self.assertEqual(_make_full_key_name('aaa/bbb', 'keyname'), 'aaa/bbb/keyname')

    def test_get_s3_bucket_site_root(self):
        for bucket_id in [self.old_style_bucket_id, self.new_style_bucket_id]:
            root = get_s3_bucket_site_root(bucket_id)
            self.assertEqual(root,
                             '%s://%s/%s' % (DOWNLOAD_SITE_SCHEME,
                                             DOWNLOAD_SITE_HOSTNAME,
                                             bucket_id))
            self.assertFalse(root.endswith('/'))

    def test_get_s3_bucket_resource_url_split(self):
        path_short = 'stem'
        path_long = 'aaa/bbb/ccc/stem.extension'
        query = 'query=yes'
        fragment = 'fragment'

        for bucket_id in [self.old_style_bucket_id, self.new_style_bucket_id]:
            for path in [path_short, path_long]:
                # Just the path
                url_split = get_s3_bucket_resource_url_split(bucket_id,
                                                             path)
                self.assertEqual(tuple(url_split),
                                 (DOWNLOAD_SITE_SCHEME, DOWNLOAD_SITE_HOSTNAME,
                                  '/%s/%s' % (bucket_id, path),
                                  '', ''))

                # Add leading /
                url_split = get_s3_bucket_resource_url_split(bucket_id,
                                                             '/%s' % path)
                self.assertEqual(tuple(url_split),
                                 (DOWNLOAD_SITE_SCHEME, DOWNLOAD_SITE_HOSTNAME,
                                  '/%s/%s' % (bucket_id, path),
                                  '', ''))

                # With query parameter
                url_split = get_s3_bucket_resource_url_split(
                    bucket_id,
                    '%s?%s' % (path, query))
                self.assertEqual(tuple(url_split),
                                 (DOWNLOAD_SITE_SCHEME, DOWNLOAD_SITE_HOSTNAME,
                                  '/%s/%s' % (bucket_id, path),
                                  query, ''))

                # With fragment
                url_split = get_s3_bucket_resource_url_split(
                    bucket_id,
                    '%s#%s' % (path, fragment))
                self.assertEqual(tuple(url_split),
                                 (DOWNLOAD_SITE_SCHEME, DOWNLOAD_SITE_HOSTNAME,
                                  '/%s/%s' % (bucket_id, path),
                                  '', fragment))

                # With query param and fragment
                url_split = get_s3_bucket_resource_url_split(
                    bucket_id,
                    '%s?%s#%s' % (path, query, fragment))
                self.assertEqual(tuple(url_split),
                                 (DOWNLOAD_SITE_SCHEME, DOWNLOAD_SITE_HOSTNAME,
                                  '/%s/%s' % (bucket_id, path),
                                  query, fragment))

    # TODO: Figure out a better way of testing these functions without literally
    # copying the path value.

    def test_get_s3_bucket_home_page_url(self):
        for bucket_id in [self.old_style_bucket_id, self.new_style_bucket_id]:
            for lang in [None, 'en', 'fa']:
                url = get_s3_bucket_home_page_url(bucket_id, lang)
                lang = ('/%s' % lang) if lang else ''
                expected_path = '%s%s/index.html' % (bucket_id, lang)
                self.assertEqual(url,
                                 urlparse.urlunsplit(
                                     (DOWNLOAD_SITE_SCHEME,
                                      DOWNLOAD_SITE_HOSTNAME,
                                      expected_path, '', '')))

    def test_get_s3_bucket_download_page_url(self):
        for bucket_id in [self.old_style_bucket_id, self.new_style_bucket_id]:
            for lang in ['en', 'fa']:
                url = get_s3_bucket_download_page_url(bucket_id, lang)
                expected_path = '%s/%s/download.html' % (bucket_id, lang)
                expected_fragment = 'direct'
                self.assertEqual(url,
                                 urlparse.urlunsplit(
                                     (DOWNLOAD_SITE_SCHEME,
                                      DOWNLOAD_SITE_HOSTNAME,
                                      expected_path, '', expected_fragment)))

    def test_get_s3_bucket_faq_url(self):
        for bucket_id in [self.old_style_bucket_id, self.new_style_bucket_id]:
            for lang in ['en', 'fa']:
                url = get_s3_bucket_faq_url(bucket_id, lang)
                expected_path = '%s/%s/faq.html' % (bucket_id, lang)
                self.assertEqual(url,
                                 urlparse.urlunsplit(
                                     (DOWNLOAD_SITE_SCHEME,
                                      DOWNLOAD_SITE_HOSTNAME,
                                      expected_path, '', '')))

    def test_get_s3_bucket_privacy_policy_url(self):
        for bucket_id in [self.old_style_bucket_id, self.new_style_bucket_id]:
            for lang in ['en', 'fa']:
                url = get_s3_bucket_privacy_policy_url(bucket_id, lang)
                expected_path = '%s/%s/faq.html' % (bucket_id, lang)
                expected_fragment = 'information-collected'
                self.assertEqual(url,
                                 urlparse.urlunsplit(
                                     (DOWNLOAD_SITE_SCHEME,
                                      DOWNLOAD_SITE_HOSTNAME,
                                      expected_path, '', expected_fragment)))

    def test_create_s3_website_bucket_name(self):
        bucket_name = create_s3_website_bucket_name()
        self.assertRegexpMatches(
            bucket_name,
            r'^%s/%s/[a-z0-9-]+$' % (DOWNLOAD_SITE_BUCKET,
                                     DOWNLOAD_SITE_PREFIX))

    def test_update_s3_download(self):
        # It's dirty, but we're going to call setUp and tearDown within this
        # function. We don't want S3 objects to build up as we go.

        #
        # No builds or server_list
        #
        with self.setUpTearDown():
            update_s3_download(self.aws_creds, None, None, self.old_style_bucket_id)
            self.assertEqual(
                self.s3.get_bucket(self.old_style_bucket_id).get_all_keys(),
                [])

        with self.setUpTearDown():
            update_s3_download(self.aws_creds, None, None, self.new_style_bucket_id)
            self.assertEqual(
                self.s3.get_bucket(DOWNLOAD_SITE_BUCKET).get_all_keys(),
                [])

        #
        # Builds, but no server_list
        #
        windows_client_version = 1
        android_client_version = 1
        with self.setUpTearDown():
            update_s3_download(self.aws_creds,
                               [(self.temp_file_path, windows_client_version, DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME),
                                (self.temp_file_path, android_client_version, DOWNLOAD_SITE_ANDROID_BUILD_FILENAME),],
                               None,
                               self.old_style_bucket_id)
            self.assertEqual(
                set([key.name for key in self.s3.get_bucket(self.old_style_bucket_id).get_all_keys()]),
                set((DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME, DOWNLOAD_SITE_ANDROID_BUILD_FILENAME)))
            self.assertEqual(self.s3.get_bucket(self.old_style_bucket_id).get_key(DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME).get_metadata(DOWNLOAD_SITE_CLIENT_VERSION_METADATA_NAME), str(windows_client_version))
            self.assertEqual(self.s3.get_bucket(self.old_style_bucket_id).get_key(DOWNLOAD_SITE_ANDROID_BUILD_FILENAME).get_metadata(DOWNLOAD_SITE_CLIENT_VERSION_METADATA_NAME), str(android_client_version))

        with self.setUpTearDown():
            update_s3_download(self.aws_creds,
                               [(self.temp_file_path, windows_client_version, DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME),
                                (self.temp_file_path, android_client_version, DOWNLOAD_SITE_ANDROID_BUILD_FILENAME),],
                               None,
                               self.new_style_bucket_id)
            windows_build_key = '%s/%s/%s' % (DOWNLOAD_SITE_PREFIX, self.old_style_bucket_id, DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME)
            android_build_key = '%s/%s/%s' % (DOWNLOAD_SITE_PREFIX, self.old_style_bucket_id, DOWNLOAD_SITE_ANDROID_BUILD_FILENAME)
            self.assertEqual(
                set([key.name for key in self.s3.get_bucket(DOWNLOAD_SITE_BUCKET).get_all_keys()]),
                set((windows_build_key, android_build_key)))
            self.assertEqual(self.s3.get_bucket(DOWNLOAD_SITE_BUCKET).get_key(windows_build_key).get_metadata(DOWNLOAD_SITE_CLIENT_VERSION_METADATA_NAME), str(windows_client_version))
            self.assertEqual(self.s3.get_bucket(DOWNLOAD_SITE_BUCKET).get_key(android_build_key).get_metadata(DOWNLOAD_SITE_CLIENT_VERSION_METADATA_NAME), str(android_client_version))

        #
        # server_list, but no builds
        #
        with self.setUpTearDown():
            update_s3_download(self.aws_creds,
                               None,
                               'server list contents',
                               self.old_style_bucket_id)
            self.assertEqual(
                self.s3.get_bucket(self.old_style_bucket_id).get_key(DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME).get_contents_as_string(),
                'server list contents')

        with self.setUpTearDown():
            update_s3_download(self.aws_creds,
                               None,
                               'server list contents',
                               self.new_style_bucket_id)
            self.assertEqual(
                self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)\
                       .get_key('%s/%s/%s' % (DOWNLOAD_SITE_PREFIX, self.old_style_bucket_id, DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME))\
                       .get_contents_as_string(),
                'server list contents')

        #
        # Builds and server_list
        #
        with self.setUpTearDown():
            update_s3_download(self.aws_creds,
                               [(self.temp_file_path, windows_client_version, DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME),
                                (self.temp_file_path, android_client_version, DOWNLOAD_SITE_ANDROID_BUILD_FILENAME),],
                               'server list contents',
                               self.old_style_bucket_id)
            self.assertEqual(
                {key.name for key in self.s3.get_bucket(self.old_style_bucket_id).get_all_keys()},
                set((DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME, DOWNLOAD_SITE_ANDROID_BUILD_FILENAME, DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME)))
            self.assertEqual(self.s3.get_bucket(self.old_style_bucket_id).get_key(DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME).get_metadata(DOWNLOAD_SITE_CLIENT_VERSION_METADATA_NAME), str(windows_client_version))
            self.assertEqual(self.s3.get_bucket(self.old_style_bucket_id).get_key(DOWNLOAD_SITE_ANDROID_BUILD_FILENAME).get_metadata(DOWNLOAD_SITE_CLIENT_VERSION_METADATA_NAME), str(android_client_version))

        with self.setUpTearDown():
            update_s3_download(self.aws_creds,
                               [(self.temp_file_path, windows_client_version, DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME),
                                (self.temp_file_path, android_client_version, DOWNLOAD_SITE_ANDROID_BUILD_FILENAME),],
                               'server list contents',
                               self.new_style_bucket_id)
            windows_build_key = '%s/%s/%s' % (DOWNLOAD_SITE_PREFIX, self.old_style_bucket_id, DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME)
            android_build_key = '%s/%s/%s' % (DOWNLOAD_SITE_PREFIX, self.old_style_bucket_id, DOWNLOAD_SITE_ANDROID_BUILD_FILENAME)
            remote_server_list_key = '%s/%s/%s' % (DOWNLOAD_SITE_PREFIX, self.old_style_bucket_id, DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME)
            self.assertEqual(
                set([key.name for key in self.s3.get_bucket(DOWNLOAD_SITE_BUCKET).get_all_keys()]),
                set((windows_build_key, android_build_key, remote_server_list_key)))
            self.assertEqual(self.s3.get_bucket(DOWNLOAD_SITE_BUCKET).get_key(windows_build_key).get_metadata(DOWNLOAD_SITE_CLIENT_VERSION_METADATA_NAME), str(windows_client_version))
            self.assertEqual(self.s3.get_bucket(DOWNLOAD_SITE_BUCKET).get_key(android_build_key).get_metadata(DOWNLOAD_SITE_CLIENT_VERSION_METADATA_NAME), str(android_client_version))

    def test_put_string_to_key_in_bucket(self):
        with self.setUpTearDown():
            put_string_to_key_in_bucket(self.aws_creds,
                                        self.old_style_bucket_id,
                                        'testkey', 'testcontent', False)
            key = self.s3.get_bucket(self.old_style_bucket_id).get_key('testkey')
            self.assertEqual(key.get_contents_as_string(), 'testcontent')
            # moto doesn't support ACL stuff
            # self.s3.get_bucket(self.old_style_bucket_id).get_acl('testkey')

        with self.setUpTearDown():
            put_string_to_key_in_bucket(self.aws_creds,
                                        self.old_style_bucket_id,
                                        'testkey', 'testcontent', True)
            key = self.s3.get_bucket(self.old_style_bucket_id).get_key('testkey')
            self.assertEqual(key.get_contents_as_string(), 'testcontent')
            # moto doesn't support ACL stuff
            # self.s3.get_bucket(self.old_style_bucket_id).get_acl('testkey')

        with self.setUpTearDown():
            put_string_to_key_in_bucket(self.aws_creds,
                                        self.new_style_bucket_id,
                                        'testkey', 'testcontent', False)
            key = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)\
                         .get_key('%s/%s/testkey' % (DOWNLOAD_SITE_PREFIX, self.old_style_bucket_id))
            self.assertEqual(key.get_contents_as_string(), 'testcontent')
            # moto doesn't support ACL stuff
            # self.s3.get_bucket(self.old_style_bucket_id).get_acl('testkey')

        with self.setUpTearDown():
            put_string_to_key_in_bucket(self.aws_creds,
                                        self.new_style_bucket_id,
                                        'testkey', 'testcontent', True)
            key = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)\
                         .get_key('%s/%s/testkey' % (DOWNLOAD_SITE_PREFIX, self.old_style_bucket_id))
            self.assertEqual(key.get_contents_as_string(), 'testcontent')
            # moto doesn't support ACL stuff
            # self.s3.get_bucket(self.old_style_bucket_id).get_acl('testkey')

    metadata = {'test-metadata-name' : 'test-metadata-value'}
    metadata_new = {'test-metadata-name' : 'test-metadata-value-new'}

    def check_metadata(self, key, metadata):
        self.assertEqual(key.get_metadata(metadata.items()[0][0]), metadata.items()[0][1])

    def test_put_string_to_key(self):
        import time

        # TODO: Test callback
        with self.setUpTearDown():
            bucket = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)
            put_string_to_key(bucket, 'testkey', Test.metadata, 'testcontent', False)
            key = bucket.get_key('testkey')
            self.assertEqual(key.get_contents_as_string(), 'testcontent')
            self.check_metadata(key, Test.metadata)
            # moto doesn't support ACL stuff
            # bucket.get_acl('testkey')

        with self.setUpTearDown():
            bucket = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)
            put_string_to_key(bucket, 'testkey', Test.metadata, 'testcontent', True)
            key = bucket.get_key('testkey')
            self.assertEqual(key.get_contents_as_string(), 'testcontent')
            self.check_metadata(key, Test.metadata)
            # moto doesn't support ACL stuff
            # bucket.get_acl('testkey')

        # No metadata
        with self.setUpTearDown():
            bucket = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)
            put_string_to_key(bucket, 'testkey', None, 'testcontent', True)
            key = bucket.get_key('testkey')
            self.assertEqual(key.get_contents_as_string(), 'testcontent')
            # moto doesn't support ACL stuff
            # bucket.get_acl('testkey')

        #
        # Changed vs. unchanged content
        #

        with self.setUpTearDown():
            bucket = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)

            # Write something
            put_string_to_key(bucket, 'testkey', Test.metadata, 'testcontent', True)
            key = bucket.get_key('testkey')
            self.assertEqual(key.get_contents_as_string(), 'testcontent')
            self.check_metadata(key, Test.metadata)
            # Record the modified time
            last_modified_1 = key.last_modified

            time.sleep(1)

            # Try to write the same thing
            put_string_to_key(bucket, 'testkey', Test.metadata, 'testcontent', True)
            key = bucket.get_key('testkey')
            # Should be no change
            self.assertEqual(key.last_modified, last_modified_1)
            self.check_metadata(key, Test.metadata)

            time.sleep(1)

            # Write a different thing
            put_string_to_key(bucket, 'testkey', Test.metadata_new, 'testcontent new', True)
            key = bucket.get_key('testkey')
            # Should be changed
            self.assertNotEqual(key.last_modified, last_modified_1)
            self.check_metadata(key, Test.metadata_new)

    def test_put_file_to_key(self):
        # TODO: Test callback

        #
        # Using filename
        #

        with self.setUpTearDown():
            bucket = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)
            put_file_to_key(bucket, 'testkey1', Test.metadata, self.temp_file_path, False)
            key = bucket.get_key('testkey1')
            self.assertEqual(key.get_contents_as_string(), 'I am a file')
            self.check_metadata(key, Test.metadata)
            put_file_to_key(bucket, 'testkey2', Test.metadata, self.temp_file_path, True)
            key = bucket.get_key('testkey2')
            self.assertEqual(key.get_contents_as_string(), 'I am a file')
            self.check_metadata(key, Test.metadata)
            # moto doesn't support ACL stuff
            # bucket.get_acl('testkey')

        #
        # Using file object
        #

        with self.setUpTearDown(), open(self.temp_file_path, 'r') as file:
            bucket = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)
            put_file_to_key(bucket, 'testkey1', Test.metadata, file, False)
            key = bucket.get_key('testkey1')
            self.assertEqual(key.get_contents_as_string(), 'I am a file')
            self.check_metadata(key, Test.metadata)
            # moto doesn't support ACL stuff
            # bucket.get_acl('testkey')

        with self.setUpTearDown(), open(self.temp_file_path, 'r') as file:
            bucket = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)
            put_file_to_key(bucket, 'testkey2', Test.metadata, file, True)
            key = bucket.get_key('testkey2')
            self.assertEqual(key.get_contents_as_string(), 'I am a file')
            self.check_metadata(key, Test.metadata)
            # moto doesn't support ACL stuff
            # bucket.get_acl('testkey')

    def test_make_qr_code(self):
        self.assertIn('PNG', make_qr_code('https://example.com'))

    def test_update_website(self):
        #
        # Custom site should mean no changes
        #
        with self.setUpTearDown():
            update_website(self.aws_creds,
                           self.old_style_bucket_id,
                           True,
                           self.temp_website_dir,
                           None, None, None)
            bucket = self.s3.get_bucket(self.old_style_bucket_id)
            self.assertEqual(bucket.get_all_keys(), [])

            update_website(self.aws_creds,
                           self.new_style_bucket_id,
                           True,
                           self.temp_website_dir,
                           None, None, None)
            bucket = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)
            self.assertEqual(bucket.get_all_keys(), [])

        #
        # No special files
        #

        with self.setUpTearDown():
            update_website(self.aws_creds,
                           self.old_style_bucket_id,
                           False,
                           self.temp_website_dir,
                           None, None, None)
            bucket = self.s3.get_bucket(self.old_style_bucket_id)
            key_set = set([key.name for key in bucket.get_all_keys()])
            website_set = set(self.website_files)
            self.assertTrue(key_set.issuperset(website_set))

        with self.setUpTearDown():
            update_website(self.aws_creds,
                           self.new_style_bucket_id,
                           False,
                           self.temp_website_dir,
                           None, None, None)
            bucket = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)
            key_set = set([key.name for key in bucket.get_all_keys()])
            key_prefix = '%s/%s' % (DOWNLOAD_SITE_PREFIX, self.old_style_bucket_id)
            website_set = [_make_full_key_name(key_prefix, fname)
                           for fname in self.website_files]
            website_set = set(website_set)
            self.assertTrue(key_set.issuperset(website_set))

        #
        # All special files
        #

        website_banner_base64 = base64.b64encode('test')
        website_banner_link = 'https://example.com'
        website_email_address = 'test@example.com'

        with self.setUpTearDown():
            update_website(self.aws_creds,
                           self.old_style_bucket_id,
                           False,
                           self.temp_website_dir,
                           website_banner_base64,
                           website_banner_link,
                           website_email_address)
            bucket = self.s3.get_bucket(self.old_style_bucket_id)
            key_set = set([key.name for key in bucket.get_all_keys()])

            website_set = set(self.website_files)
            website_set.update((DOWNLOAD_SITE_SPONSOR_BANNER_KEY_NAME,
                                DOWNLOAD_SITE_SPONSOR_BANNER_LINK_KEY_NAME,
                                DOWNLOAD_SITE_EMAIL_ADDRESS_KEY_NAME))

            self.assertTrue(key_set.issuperset(website_set))

        with self.setUpTearDown():
            update_website(self.aws_creds,
                           self.new_style_bucket_id,
                           False,
                           self.temp_website_dir,
                           website_banner_base64,
                           website_banner_link,
                           website_email_address)
            bucket = self.s3.get_bucket(DOWNLOAD_SITE_BUCKET)
            key_set = set([key.name for key in bucket.get_all_keys()])

            key_prefix = '%s/%s' % (DOWNLOAD_SITE_PREFIX, self.old_style_bucket_id)
            website_set = set([_make_full_key_name(key_prefix, fname)
                               for fname in self.website_files])
            website_set.update((_make_full_key_name(key_prefix, DOWNLOAD_SITE_SPONSOR_BANNER_KEY_NAME),
                                _make_full_key_name(key_prefix, DOWNLOAD_SITE_SPONSOR_BANNER_LINK_KEY_NAME),
                                _make_full_key_name(key_prefix, DOWNLOAD_SITE_EMAIL_ADDRESS_KEY_NAME),))

            self.assertTrue(key_set.issuperset(website_set))


if __name__ == '__main__':
    unittest.main(verbosity=2)
