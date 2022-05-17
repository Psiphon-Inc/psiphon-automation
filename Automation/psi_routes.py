#!/usr/bin/python
#
# Copyright (c) 2019, Psiphon Inc.
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

import zipfile
import os, os.path
import StringIO 
import csv
import zlib
import tarfile
import base64
import psi_ops_crypto_tools

try:
    import sys
    if sys.version_info < (3, 0):
        import urllib2
    else:
        import urllib.request as urllib2
except ImportError as error:
    print(error)

GEO_DATA_ROOT = os.path.join(os.path.abspath('..'), 'Data', 'GeoData')
GEO_ZIP_FILENAME = 'maxmind_data.zip'
GEO_ZIP_PATH = os.path.join(GEO_DATA_ROOT, GEO_ZIP_FILENAME)
GEO_ROUTES_ROOT = os.path.join(GEO_DATA_ROOT, 'Routes')
GEO_ROUTES_EXTENSION = '.zlib'
GEO_ROUTES_SIGNED_EXTENSION = '.json'
GEO_ROUTES_ARCHIVE_PATH = os.path.join(GEO_ROUTES_ROOT, 'routes.tar.gz')


def recache_geodata(url):
    # getting the file age
    last_modified_file =  '%s.%s' % (GEO_ZIP_PATH, 'last_modified')
    if os.path.exists(last_modified_file) and os.path.exists(GEO_ZIP_PATH):
        with open(last_modified_file) as f:
            current_last_modified = f.read().strip()
        headers = {'If-Modified-Since': current_last_modified}
    else:
        headers = {}
        current_last_modified = None

    request = urllib2.Request(url, headers=headers)

    # checking for new version of the data
    try:
        url = urllib2.urlopen(request, timeout=5)
        last_modified = url.headers.get('Last-Modified')
    except urllib2.HTTPError as e:
        if e.getcode() != 304:
            raise Exception('HTTP error %i requesting geodata file' % e.getcode())
        # Not-Modified 304 returned
        last_modified = current_last_modified
    except urllib2.URLError:
        raise Exception('URLError')
        # timeout error
        last_modified = None

    if last_modified is not None and current_last_modified != last_modified:
        # we need to download new version
        print("Geodata file has been modified since last fetch. Fetching new")
        content = url.read()
        with open(GEO_ZIP_PATH, 'wb') as f:
            f.write(content)

        with open(last_modified_file, 'w') as f:
            f.write(last_modified)
    else:
        print("The geodata file is not modified, using cached version")


def consume_line(files, ip_block, country_code):
    base_ip, prefix = ip_block.split('/')
    prefix = int(prefix)

    #check if all values are valid
    if not base_ip or not prefix or len(country_code) != 2:
        return False

    path = os.path.join(GEO_ROUTES_ROOT, '%s.route' % country_code)
    if path in files:
        file = files[path]
    else:
        file = open(path, 'a')
        files[path] = file

    # from https://stackoverflow.com/a/27832518
    netmask = '.'.join([str((0xffffffff << (32 - prefix) >> i) & 0xff) for i in [24, 16, 8, 0]])
    file.write( "%s\t%s\n" % (base_ip, netmask))
    

def make_routes():
    # create the directories
    if not os.path.exists(GEO_DATA_ROOT):
        os.makedirs(GEO_DATA_ROOT)
    if not os.path.exists(GEO_ROUTES_ROOT):
        os.makedirs(GEO_ROUTES_ROOT)

    if not os.path.isfile('./maxmind_license.txt'):
        raise Exception('maxmind_license.txt file missing from Automation directory.')
    with open('./maxmind_license.txt', 'r') as licenseFile:
        licenseKey = licenseFile.read().replace('\n', '')
    if not 'license_key=' in licenseKey:
        raise Exception('maxmind_license.txt file must include a single line of the format \"license_key=<KEY>\".')

    # TODO: get url from psi_db
    url='https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-Country-CSV&' + licenseKey + '&suffix=zip'
    recache_geodata(url)

    if not os.path.exists(GEO_ZIP_PATH):
        raise Exception('Geodata file does not exist')

    country_blocks_filename = ''
    country_names_filename = ''
    
    fh=open(GEO_ZIP_PATH, 'rb')
    zf = zipfile.ZipFile(fh)
    names=zf.namelist()
    for name in names:
        fileName, fileExtension = os.path.splitext(name)
        if fileExtension == '.csv' and 'Country-Blocks-IPv4' in fileName:
            print("CSV found: %s" % name)
            country_blocks_filename = name
        if fileExtension == '.csv' and 'Country-Locations-en' in fileName:
            print("CSV found: %s" % name)
            country_names_filename = name
    
    if not country_blocks_filename:
        raise Exception('blocks CSV not found in the %s' % GEO_ZIP_PATH)

    if not country_names_filename:
        raise Exception('locations CSV not found in the %s' % GEO_ZIP_PATH)

    ip_blocks_data = StringIO.StringIO(zf.read(country_blocks_filename))
    if not ip_blocks_data:
        raise Exception('Can not read from the %s' % GEO_ZIP_PATH)
    
    country_names_data = StringIO.StringIO(zf.read(country_names_filename))
    if not country_names_data:
        raise Exception('Can not read from the %s' % GEO_ZIP_PATH)

    # read country names file and build a dict of id to country code
    country_codes = {}
    myreader = csv.reader(country_names_data, delimiter=',', quotechar='"')
    for row in myreader:
        if len(row) == 7:
            country_codes[row[0]] = row[4]
    
    # delete current routing files
    for root, dirs, files in os.walk(GEO_ROUTES_ROOT):
        for name in files:
            os.remove(os.path.join(root, name))

    # Keep route files open for appending while processing CSV
    files = {}

    myreader = csv.reader(ip_blocks_data, delimiter=',', quotechar='"')
    # skip the header row
    next(myreader, None)
    for row in myreader:
        if len(row) == 6:
            ip_block = row[0]
            country_id = row[2]
            if country_id == '':
                continue
            country_code = country_codes[country_id]
            if country_code == '':
                continue
            consume_line(files, ip_block, country_code)

    # Close route files and make zlib compressed copies
    # Create single file archive containing all zlib route files
    # Using zlib format to compress data, which client expects and
    # handles; note, this isn't .zip or .gz format.
    tar = tarfile.open(name=GEO_ROUTES_ARCHIVE_PATH, mode='w:gz')
    for path, file in files.iteritems():
        file.close()
        with open(path, 'r') as file:
            data = file.read()
        zlib_path = path + GEO_ROUTES_EXTENSION
        with open(zlib_path, 'wb') as zlib_file:
            zlib_file.write(zlib.compress(data))
        tar.add(zlib_path, arcname=os.path.split(zlib_path)[1], recursive=False)
    tar.close()

def make_signed_routes(pem_key_pair, private_key_password):
    make_routes()
    for root, dirs, files in os.walk(GEO_ROUTES_ROOT):
        for name in files:
            if(name.endswith(GEO_ROUTES_EXTENSION)):
                path = os.path.join(root, name)
                with open(path, 'rb') as file:
                    data = file.read()
                signed_routes_data  =  psi_ops_crypto_tools.make_signed_data(
                        pem_key_pair,
                        private_key_password,
                        base64.b64encode(data))

                signed_routes_filename = path + GEO_ROUTES_SIGNED_EXTENSION
                with open(signed_routes_filename, 'w') as f:
                    f.write(signed_routes_data)

if __name__ == "__main__":
    make_routes()


