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


import sys
import os

from config import config

# Make the Automation (psi_ops) modules available
sys.path.append(config['psiOpsPath'])
import psi_ops

# We are effectively exporting these
from psi_ops_s3 import \
    get_s3_bucket_resource_url_split,\
    get_s3_bucket_home_page_url,\
    get_s3_bucket_download_page_url,\
    get_s3_bucket_faq_url,\
    DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME,\
    EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME,\
    DOWNLOAD_SITE_ANDROID_BUILD_FILENAME,\
    EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME
from transifex_pull import WEBSITE_LANGS


_psinet = None
def _ensure_psinet_loaded():
    # Load the psinet DB
    global _psinet
    if not _psinet:
        _psinet = psi_ops.PsiphonNetwork.load_from_file(config['psinetFilePath'])


def get_propagation_channel_name_by_id(prop_channel_id):
    '''
    Gets the Propagation Channel name from its ID. Returns None if not found.
    '''
    _ensure_psinet_loaded()
    propagation_channel = _psinet.get_propagation_channel_by_id(prop_channel_id)
    return propagation_channel.name if propagation_channel else None


def get_sponsor_name_by_id(sponsor_id):
    '''
    Gets the Sponsor name from its ID. Returns None if not found.
    '''
    _ensure_psinet_loaded()
    sponsor = _psinet.get_sponsor_by_id(sponsor_id)
    return sponsor.name if sponsor else None


def get_server_display_id_from_ip(ip):
    _ensure_psinet_loaded()
    server_id = None
    server = _psinet.get_server_by_ip_address(ip)
    if server:
        server_id = '[%s]' % server.id
    else:
        server = _psinet.get_deleted_server_by_ip_address(ip)
        if server:
            server_id = '[%s][DELETED]' % server.id

    # If the psinet DB is stale, we might not find the IP address, but
    # we still want to redact it.
    return server_id if server_id else '[UNKNOWN]'


def get_bucket_name_and_email_address(sponsor_name, prop_channel_name):
    '''
    Retuns a tuple of the form `(bucket_name, email_address)` that corresponds
    to the given Sponsor and Propagation Channel. `email_address` will be `None`
    if the Sponsor does not have an email campaign.
    `(None, None)` will be returned if no match at all is found.
    '''
    _ensure_psinet_loaded()

    sponsor = _psinet.get_sponsor_by_name(sponsor_name)
    prop_channel = _psinet.get_propagation_channel_by_name(prop_channel_name)

    if not sponsor or not prop_channel:
        return (None, None)

    prop_channel = _psinet.get_propagation_channel_by_name(prop_channel_name)

    # Get the sponsor campaigns that match the prop channel
    campaigns = [campaign for campaign in sponsor.campaigns
                 if campaign.propagation_channel_id == prop_channel.id]

    # First try to find a campaign that uses email
    email_campaigns = [campaign for campaign in campaigns
                       if type(campaign.account) == psi_ops.EmailPropagationAccount]

    bucket_name = None
    email_address = None
    if email_campaigns:
        # There might be more than one email campaign, but we have no need
        # to distinguish between them.
        campaign = email_campaigns[0]
        bucket_name = campaign.s3_bucket_name
        email_address = campaign.account.email_address
    elif campaigns:
        # No email campaign, so just pick one of the others
        campaign = campaigns[0]
        bucket_name = campaign.s3_bucket_name
        email_address = None

    if not bucket_name:
        return (None, None)

    return (bucket_name, email_address)
