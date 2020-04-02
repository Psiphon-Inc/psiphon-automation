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

import os
import threading
import GeoIP


# Use the commercial "city" and "isp" databases if available
_city_db_filename = '/usr/local/share/GeoIP/GeoIPCity.dat'
_isp_db_filename = '/usr/local/share/GeoIP/GeoIPISP.dat'

# Shared GeoIP databases cached in memory. all calls to
# get_geoip from any thread share these cached databases.

_db_lock = threading.RLock()
_standard_db = None
_has_city_db_file = None
_city_db = None
_has_isp_db_file = None
_isp_db = None

# Helpers to load global databases; these assume the caller
# is providing a mutex

def _get_standard_db():
    global _standard_db
    if _standard_db is None:
        _standard_db = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE)
    return _standard_db

def _has_city_db():
    global _has_city_db_file
    if _has_city_db_file is None:
        _has_city_db_file = os.path.isfile(_city_db_filename)
    return _has_city_db_file

def _get_city_db():
    global _city_db
    if _city_db is None:
        _city_db = GeoIP.open(_city_db_filename, GeoIP.GEOIP_MEMORY_CACHE)
    return _city_db

def _has_isp_db():
    global _has_isp_db_file
    if _has_isp_db_file is None:
        _has_isp_db_file = os.path.isfile(_isp_db_filename)
    return _has_isp_db_file

def _get_isp_db():
    global _isp_db
    if _isp_db is None:
        _isp_db = GeoIP.open(_isp_db_filename, GeoIP.GEOIP_MEMORY_CACHE)
    return _isp_db


def get_unknown():
    # TODO: value is duplicated in psi_auth
    return {'region': 'None', 'city': 'None', 'isp': 'None'}


def get_region_only(region):
    return {'region': region, 'city': 'None', 'isp': 'None'}


def get_geoip(network_address):
    global _db_lock
    with _db_lock:
        try:
            geoip = get_unknown()

            if _has_city_db():
                record = _get_city_db().record_by_name(network_address)
                if record:
                    if record['country_code']:
                        geoip['region'] = record['country_code']
                    if record['city']:
                        # Convert City name from ISO-8859-1 to UTF-8 encoding
                        try:
                            geoip['city'] = record['city'].decode('iso-8859-1').encode('utf-8')
                        except UnicodeDecodeError, ValueError:
                            pass
            else:
                region = _get_standard_db().country_code_by_name(network_address)
                if region:
                    geoip['region'] = region

            if _has_isp_db():
                isp = _get_isp_db().org_by_name(network_address)
                if isp:
                    geoip['isp'] = isp.decode('iso-8859-1').encode('utf-8')

            return geoip

        except NameError:
            # Handle the case where the GeoIP module isn't installed
            return get_unknown()
