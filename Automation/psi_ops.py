#!/usr/bin/python
#
# Copyright (c) 2015, Psiphon Inc.
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

import re
import sys
import os
import io
import datetime
import pprint
import json
import textwrap
import binascii
import base64
import jsonpickle
import tempfile
import random
import optparse
import operator
import gzip
import zlib
import copy
import subprocess
import traceback
import shutil
import urlparse
import csv
import hmac
import hashlib
from pkg_resources import parse_version
from multiprocessing.pool import ThreadPool
from collections import defaultdict

import psi_utils
import psi_ops_cms
import psi_ops_discovery


# Modules available only on the automation server

try:
    from PIL import Image
except ImportError as error:
    print error

try:
    import website_generator
except ImportError as error:
    print error

try:
    import psi_ops_crypto_tools
except ImportError as error:
    print error

try:
    import psi_ssh
except ImportError as error:
    print error

try:
    import psi_linode_api4 as psi_linode
except ImportError as error:
    print error

try:
    import psi_digitalocean_apiv2 as psi_digitalocean
except ImportError as error:
    print error

try:
    import psi_vpsnet
except ImportError as error:
    print error

try:
    import psi_elastichosts
except ImportError as error:
    print error
try:
    import psi_templates
except ImportError as error:
    print error

try:
    import psi_ops_s3
except ImportError as error:
    print error

try:
    import psi_ops_install
except ImportError as error:
    print error

try:
    import psi_ops_deploy
except ImportError as error:
    print error

try:
    import psi_ops_build_windows
except ImportError as error:
    print error

try:
    import psi_ops_build_android
except ImportError as error:
    print error

try:
    import psi_ops_test_windows
except ImportError as error:
    print error

try:
    import psi_ops_twitter
except ImportError as error:
    print error

try:
    import psi_routes
except ImportError as error:
    print error

plugins = []
try:
    sys.path.insert(0, os.path.abspath('../../Plugins'))
    import psi_ops_plugins
    for (path, plugin) in psi_ops_plugins.PLUGINS:
        sys.path.insert(0, path)
        plugins.append(__import__(plugin))
except ImportError as error:
    print error


WEBSITE_GENERATION_DIR = './website-out'


EMAIL_RESPONDER_CONFIG_BUCKET_KEY = 'EmailResponder/conf.json'


# NOTE: update compartmentalize() functions when adding fields

PropagationChannel = psi_utils.recordtype(
    'PropagationChannel',
    'id, name, propagation_mechanism_types, propagator_managed_upgrades, ' +
    'new_osl_discovery_servers_count, new_discovery_servers_count, new_propagation_servers_count, ' +
    'max_osl_discovery_server_age_in_days, max_discovery_server_age_in_days, max_propagation_server_age_in_days',
    default=None)

PropagationMechanism = psi_utils.recordtype(
    'PropagationMechanism',
    'type')

TwitterPropagationAccount = psi_utils.recordtype(
    'TwitterPropagationAccount',
    'name, consumer_key, consumer_secret, access_token_key, access_token_secret')

EmailPropagationAccount = psi_utils.recordtype(
    'EmailPropagationAccount',
    'email_address')

# website_banner and website_banner_link are separately optional (although it
# makes no sense to have the latter without the former).
Sponsor = psi_utils.recordtype(
    'Sponsor',
    'id, name, banner, website_banner, website_banner_link, home_pages, mobile_home_pages, ' +
    'campaigns, page_view_regexes, https_request_regexes, use_data_from_sponsor_id',
    default=None)

SponsorHomePage = psi_utils.recordtype(
    'SponsorHomePage',
    'region, url')

# Note that `s3_bucket_name` has two different meanings/uses: Originally, each
# `SponsorCampaign` had its own S3 bucket, so `s3_bucket_name` really was the
# bucket name. But we hit the bucket limit, so we started storing the
# `SponsorCampaign` websites in a single bucket, with different key prefixes
# (like folders). So now `s3_bucket_name` is the bucket name and key prefix for
# the `SponsorCampaign`'s website.
SponsorCampaign = psi_utils.recordtype(
    'SponsorCampaign',
    'propagation_channel_id, propagation_mechanism_type, account, ' +
    's3_bucket_name, alternate_s3_bucket_name, languages, platforms, custom_download_site')

SponsorRegex = psi_utils.recordtype(
    'SponsorRegex',
    'regex, replace')

Host = psi_utils.recordtype(
    'Host',
    'id, is_TCS, TCS_type, provider, provider_id, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key, ' +
    'stats_ssh_username, stats_ssh_password, ' +
    'datacenter_name, region, ' +
    'fronting_provider_id, passthrough_address, ' +
    'meek_server_port, meek_server_obfuscated_key, meek_server_fronting_domain, ' +
    'meek_server_fronting_host, alternate_meek_server_fronting_hosts, ' +
    'meek_cookie_encryption_public_key, meek_cookie_encryption_private_key, ' +
    'tactics_request_public_key, tactics_request_private_key, tactics_request_obfuscated_key, ' +
    'run_packet_manipulator',
    default=None)

Server = psi_utils.recordtype(
    'Server',
    'id, host_id, ip_address, egress_ip_address, internal_ip_address, ' +
    'propagation_channel_id, is_embedded, is_permanent, discovery_date_range, capabilities, ' +
    'web_server_port, web_server_secret, web_server_certificate, web_server_private_key, ' +
    'ssh_port, ssh_username, ssh_password, ssh_host_key, TCS_ssh_private_key, ' +
    'ssh_obfuscated_port, ssh_obfuscated_quic_port, ssh_obfuscated_tapdance_port,  ssh_obfuscated_conjure_port,' +
    'ssh_obfuscated_key, alternate_ssh_obfuscated_ports, osl_ids, osl_discovery_date_range, ' +
    'configuration_version',
    default=None)

# Server.configuration_version is emitted as the configuration version field in
# server entries. This version field is used by clients when importing server
# entries, to determine when to replace existing entries. For certain server
# entry sources, any existing entry will be replaced only when its version is
# lower than this version field.
#
# All servers start at INITIAL_SERVER_CONFIGURATION_VERSION. When new capabilities
# or configuration is set for an existing, deployed server, increment its
# Server.configuration_version to ensure clients update their server entries.
INITIAL_SERVER_CONFIGURATION_VERSION = 0


def ServerCapabilities():
    capabilities = {}
    for capability in ('handshake', 'VPN', 'SSH', 'OSSH'):
        capabilities[capability] = True
    # These are disabled by default
    for capability in ('ssh-api-requests', 'FRONTED-MEEK', 'UNFRONTED-MEEK', 'UNFRONTED-MEEK-SESSION-TICKET', 'FRONTED-MEEK-TACTICS', 'QUIC', 'TAPDANCE', 'CONJURE', 'FRONTED-MEEK-QUIC'):
        capabilities[capability] = False
    return capabilities


def copy_server_capabilities(caps):
    capabilities = {}
    for capability in ('handshake', 'ssh-api-requests', 'VPN', 'SSH', 'OSSH', 'FRONTED-MEEK', 'UNFRONTED-MEEK', 'UNFRONTED-MEEK-SESSION-TICKET', 'FRONTED-MEEK-TACTICS', 'QUIC', 'TAPDANCE', 'CONJURE', 'FRONTED-MEEK-QUIC'):
        capabilities[capability] = caps[capability]
    return capabilities


ClientVersion = psi_utils.recordtype(
    'ClientVersion',
    'version, description')

AwsAccount = psi_utils.recordtype(
    'AwsAccount',
    'access_id, secret_key',
    default=None)

ProviderRank = psi_utils.recordtype(
    'ProviderRank',
    'provider, rank',
    default=None)
ProviderRank.provider_values = ('linode', 'elastichosts', 'digitalocean', 'vpsnet')

LinodeAccount = psi_utils.recordtype(
    'LinodeAccount',
    'api_key, base_id, base_ip_address, base_ssh_port, ' +
    'base_root_password, base_stats_username, base_host_public_key, ' +
    'base_known_hosts_entry, base_rsa_private_key, base_rsa_public_key, ' +
    'base_tarball_path, tcs_base_root_password, tcs_base_host_public_key, api_token',
    default=None)

DigitalOceanAccount = psi_utils.recordtype(
    'DigitalOceanAccount',
    'client_id, api_key, base_id, base_size_id, base_region_id, ' +
    'base_ssh_port, base_stats_username, base_host_public_key, ' +
    'base_rsa_private_key, ssh_key_template_id, ' +
    'oauth_token, base_size_slug',
    default=None)

VPSNetAccount = psi_utils.recordtype(
    'VPSNetAccount',
    'account_id, api_key, api_base_url, base_ssh_port, ' +
    'base_root_password, base_stats_username, ' +
    'base_cloud_id, base_system_template, base_ssd_plan',
    default=None)

VPS247Account = psi_utils.recordtype(
    'VPS247Account',
    'account_id, api_key, api_base_url, base_ssh_port, ' +
    'base_root_password, base_stats_username, base_rsa_private_key, ' +
    'base_region_id, base_package_id',
    default=None)

ElasticHostsAccount = psi_utils.recordtype(
    'ElasticHostsAccount',
    'zone, uuid, api_key, base_drive_id, cpu, mem, base_host_public_key, ' +
    'root_username, base_root_password, base_ssh_port, stats_username, rank',
    default=None)
ElasticHostsAccount.zone_values = ('ELASTICHOSTS_US1',  # sat-p
                                   'ELASTICHOSTS_UK1',  # lon-p
                                   'ELASTICHOSTS_UK2')  # lon-b

StatsServerAccount = psi_utils.recordtype(
    'StatsServerAccount',
    'ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key',
    default=None)

SpeedTestURL = psi_utils.recordtype(
    'SpeedTestURL',
    'server_address, server_port, request_path')

RemoteServerSigningKeyPair = psi_utils.recordtype(
    'RemoteServerSigningKeyPair',
    'pem_key_pair')

# The RemoteServerSigningKeyPair record is stored in the secure management
# database, so we don't require a secret key pair wrapping password
REMOTE_SERVER_SIGNING_KEY_PAIR_PASSWORD = 'none'

FeedbackEncryptionKeyPair = psi_utils.recordtype(
    'FeedbackEncryptionKeyPair',
    'pem_key_pair, password')

FeedbackUploadInfo = psi_utils.recordtype(
    'FeedbackUploadInfo',
    'upload_server, upload_path, upload_server_headers')

UpgradePackageSigningKeyPair = psi_utils.recordtype(
    'UpgradePackageSigningKeyPair',
    'pem_key_pair')

# The UpgradePackageSigningKeyPair record is stored in the secure management
# database, so we don't require a secret key pair wrapping password
UPGRADE_PACKAGE_SIGNING_KEY_PAIR_PASSWORD = 'none'

RoutesSigningKeyPair = psi_utils.recordtype(
    'RoutesSigningKeyPair',
    'pem_key_pair, password')


CLIENT_PLATFORM_WINDOWS = 'Windows'
CLIENT_PLATFORM_ANDROID = 'Android'
CLIENT_PLATFORM_IOS = 'iOS'

class PsiphonNetwork(psi_ops_cms.PersistentObject):

    def __init__(self, initialize_plugins=True):
        super(PsiphonNetwork, self).__init__()
        # TODO: what is this __version for?
        self.__version = '1.0'
        self.__sponsors = {}
        self.__propagation_mechanisms = {
            'twitter': PropagationMechanism('twitter'),
            'email-autoresponder': PropagationMechanism('email-autoresponder'),
            'static-download': PropagationMechanism('static-download')
        }
        self.__propagation_channels = {}
        self.__hosts = {}
        self.__deleted_hosts = []
        self.__servers = {}
        self.__deleted_servers = {}
        self.__hosts_to_remove_from_providers = set()
        self.__client_versions = {
            CLIENT_PLATFORM_WINDOWS: [],
            CLIENT_PLATFORM_ANDROID: []
        }
        self.__stats_server_account = StatsServerAccount()
        self.__aws_account = AwsAccount()
        self.__provider_ranks = []
        self.__linode_account = LinodeAccount()
        self.__digitalocean_account = DigitalOceanAccount()
        self.__vpsnet_account = VPSNetAccount()
        self.__vps247_account = VPS247Account()
        self.__elastichosts_accounts = []
        self.__deploy_implementation_required_for_hosts = set()
        self.__deploy_data_required_for_all = False
        self.__deploy_builds_required_for_campaigns = {
            CLIENT_PLATFORM_WINDOWS: set(),
            CLIENT_PLATFORM_ANDROID: set()
        }
        self.__deploy_stats_config_required = False
        self.__deploy_email_config_required = False
        self.__speed_test_urls = []
        self.__remote_server_list_signing_key_pair = None
        self.__feedback_encryption_key_pair = None
        self.__feedback_upload_info = None
        self.__alternate_feedback_upload_urls = set()
        self.__upgrade_package_signing_key_pair = None
        self.__default_email_autoresponder_account = None
        self.__deploy_website_required_for_sponsors = set()
        self.__deploy_pave_osls_required_for_propagation_channels = set()
        self.__automation_bucket = None
        self.__discovery_strategy_value_hmac_key = binascii.b2a_hex(os.urandom(32))
        self.__android_home_tab_url_exclusions = set()
        self.__alternate_meek_fronting_addresses = defaultdict(set)
        self.__alternate_meek_fronting_addresses_regex = defaultdict(str)
        self.__meek_fronting_disable_SNI = defaultdict(bool)
        self.__routes_signing_key_pair = None
        self.__routes_signing_public_key = None
        self.__TCS_traffic_rules_set = None
        self.__TCS_OSL_config = None
        self.__TCS_tactics_config_template = None
        self.__TCS_psiphond_config_values = None
        self.__TCS_blocklist_csv = None
        self.__default_sponsor_id = None
        self.__alternate_s3_bucket_domains = set()
        self.__global_https_request_regexes = []

        # Generate a server entry signing key pair using
        # https://github.com/Psiphon-Labs/psiphon-tunnel-core/tree/master/psiphon/common/protocol/signer
        # and store as a tuple (<public-key>, <private-key>)
        self.__server_entry_signing_key_pair = None

        self.__exchange_obfuscation_key = base64.b64encode(os.urandom(32))

        self.__ssh_ip_address_whitelist = []
        self.__TCS_iptables_output_rules = []

        self.__fronting_provider_id_aliases = {}

        self.__passthrough_addresses = []

        self.__standard_ossh_ports = set()

        if initialize_plugins:
            self.initialize_plugins()

    class_version = '0.64'

    def upgrade(self):
        if cmp(parse_version(self.version), parse_version('0.1')) < 0:
            self.__provider_ranks = []
            self.__elastichosts_accounts = []
            self.version = '0.1'
        if cmp(parse_version(self.version), parse_version('0.2')) < 0:
            for server in self.__servers.itervalues():
                server.ssh_obfuscated_port = None
                server.ssh_obfuscated_key = None
            self.version = '0.2'
        if cmp(parse_version(self.version), parse_version('0.3')) < 0:
            for host in self.__hosts.itervalues():
                host.provider = None
            self.version = '0.3'
        if cmp(parse_version(self.version), parse_version('0.4')) < 0:
            for sponsor in self.__sponsors.itervalues():
                sponsor.page_view_regexes = []
                sponsor.https_request_regexes = []
            self.version = '0.4'
        if cmp(parse_version(self.version), parse_version('0.5')) < 0:
            self.__speed_test_urls = []
            self.version = '0.5'
        if cmp(parse_version(self.version), parse_version('0.6')) < 0:
            for propagation_channel in self.__propagation_channels.itervalues():
                propagation_channel.new_discovery_servers_count = 0
                propagation_channel.new_propagation_servers_count = 0
                propagation_channel.max_discovery_server_age_in_days = 0
                propagation_channel.max_propagation_server_age_in_days = 0
            self.version = '0.6'
        if cmp(parse_version(self.version), parse_version('0.7')) < 0:
            self.__remote_server_list_signing_key_pair = None
            self.version = '0.7'
        if cmp(parse_version(self.version), parse_version('0.8')) < 0:
            self.__client_versions = {
                CLIENT_PLATFORM_WINDOWS: self.__client_versions,
                CLIENT_PLATFORM_ANDROID: []
            }
            self.__deploy_builds_required_for_campaigns = {
                CLIENT_PLATFORM_WINDOWS: self.__deploy_builds_required_for_campaigns,
                CLIENT_PLATFORM_ANDROID: set()
            }
            self.version = '0.8'
        if cmp(parse_version(self.version), parse_version('0.9')) < 0:
            for host in self.__hosts.itervalues():
                host.datacenter_name = ""
            self.__upgrade_host_datacenter_names()
            self.__deleted_hosts = []
            self.__deleted_servers = {}
            self.version = '0.9'
        if cmp(parse_version(self.version), parse_version('0.10')) < 0:
            for server in self.__servers.itervalues():
                server.internal_ip_address = server.ip_address
                server.capabilities = ServerCapabilities()
            for server in self.__deleted_servers.itervalues():
                server.internal_ip_address = server.ip_address
                server.capabilities = ServerCapabilities()
            self.version = '0.10'
        if cmp(parse_version(self.version), parse_version('0.11')) < 0:
            for server in self.__servers.itervalues():
                server.capabilities['OSSH'] = server.capabilities['SSH+']
                server.capabilities.pop('SSH+')
            for server in self.__deleted_servers.itervalues():
                server.capabilities['OSSH'] = server.capabilities['SSH+']
                server.capabilities.pop('SSH+')
            self.version = '0.11'
        if cmp(parse_version(self.version), parse_version('0.12')) < 0:
            self.__feedback_encryption_key_pair = None
            self.version = '0.12'
        if cmp(parse_version(self.version), parse_version('0.13')) < 0:
            for sponsor in self.__sponsors.itervalues():
                for campaign in sponsor.campaigns:
                    campaign.languages = None
            self.version = '0.13'
        if cmp(parse_version(self.version), parse_version('0.14')) < 0:
            self.__feedback_upload_info = None
            self.version = '0.14'
        if cmp(parse_version(self.version), parse_version('0.15')) < 0:
            for server in self.__servers.itervalues():
                server.is_permanent = False
            for server in self.__deleted_servers.itervalues():
                server.is_permanent = False
            self.version = '0.15'
        if cmp(parse_version(self.version), parse_version('0.16')) < 0:
            for sponsor in self.__sponsors.itervalues():
                for campaign in sponsor.campaigns:
                    campaign.custom_download_site = False
            self.version = '0.16'
        if cmp(parse_version(self.version), parse_version('0.17')) < 0:
            self.__upgrade_package_signing_key_pair = None
            self.version = '0.17'
        if cmp(parse_version(self.version), parse_version('0.18')) < 0:
            self.__default_email_autoresponder_account = None
            self.version = '0.18'
        if cmp(parse_version(self.version), parse_version('0.19')) < 0:
            self.__hosts_to_remove_from_providers = set()
            self.version = '0.19'
        if cmp(parse_version(self.version), parse_version('0.20')) < 0:
            for host in self.__hosts.itervalues():
                host.region = ''
            for host in self.__deleted_hosts:
                host.region = ''
            self.version = '0.20'
        if cmp(parse_version(self.version), parse_version('0.21')) < 0:
            for propagation_channel in self.__propagation_channels.itervalues():
                propagation_channel.propagator_managed_upgrades = False
            self.version = '0.21'
        if cmp(parse_version(self.version), parse_version('0.22')) < 0:
            self.__deploy_website_required_for_sponsors = set()
            for sponsor in self.__sponsors.itervalues():
                sponsor.website_banner = None
                sponsor.website_banner_link = None
            self.version = '0.22'
        if cmp(parse_version(self.version), parse_version('0.23')) < 0:
            self.__automation_bucket = None
            self.version = '0.23'
        if cmp(parse_version(self.version), parse_version('0.24')) < 0:
            self.__digitalocean_account = DigitalOceanAccount()
            self.version = '0.24'
        if cmp(parse_version(self.version), parse_version('0.25')) < 0:
            for server in self.__servers.itervalues():
                server.alternate_ssh_obfuscated_ports = []
            for server in self.__deleted_servers.itervalues():
                server.alternate_ssh_obfuscated_ports = []
            self.version = '0.25'
        if cmp(parse_version(self.version), parse_version('0.26')) < 0:
            self.__discovery_strategy_value_hmac_key = binascii.b2a_hex(os.urandom(32))
            for host in self.__hosts.itervalues():
                host.meek_server_port = None
                host.meek_server_obfuscated_key = None
                host.meek_server_fronting_domain = None
                host.meek_server_fronting_host = None
                host.meek_cookie_encryption_public_key = None
                host.meek_cookie_encryption_private_key = None
            for host in self.__deleted_hosts:
                host.meek_server_port = None
                host.meek_server_obfuscated_key = None
                host.meek_server_fronting_domain = None
                host.meek_server_fronting_host = None
                host.meek_cookie_encryption_public_key = None
                host.meek_cookie_encryption_private_key = None
            for host in self.__hosts_to_remove_from_providers:
                host.meek_server_port = None
                host.meek_server_obfuscated_key = None
                host.meek_server_fronting_domain = None
                host.meek_server_fronting_host = None
                host.meek_cookie_encryption_public_key = None
                host.meek_cookie_encryption_private_key = None
            for server in self.__servers.itervalues():
                if server.capabilities:
                    server.capabilities['FRONTED-MEEK'] = False
                    server.capabilities['UNFRONTED-MEEK'] = False
            for server in self.__deleted_servers.itervalues():
                if server.capabilities:
                    server.capabilities['FRONTED-MEEK'] = False
                    server.capabilities['UNFRONTED-MEEK'] = False
            self.version = '0.26'
        if cmp(parse_version(self.version), parse_version('0.27')) < 0:
            for sponsor in self.__sponsors.itervalues():
                sponsor.mobile_home_pages = {}
            self.version = '0.27'
        if cmp(parse_version(self.version), parse_version('0.28')) < 0:
            self.__android_home_tab_url_exclusions = set()
            self.version = '0.28'
        if cmp(parse_version(self.version), parse_version('0.29')) < 0:
            self.__alternate_meek_fronting_addresses = defaultdict(set)
            self.version = '0.29'
        if cmp(parse_version(self.version), parse_version('0.30')) < 0:
            self.__routes_signing_key_pair = None
            self.version = '0.30'
        if cmp(parse_version(self.version), parse_version('0.31')) < 0:
            for sponsor in self.__sponsors.itervalues():
                for campaign in sponsor.campaigns:
                    campaign.platforms = None
            self.version = '0.31'
        if cmp(parse_version(self.version), parse_version('0.32')) < 0:
            for sponsor in self.__sponsors.itervalues():
                sponsor.use_data_from_sponsor_id = None
            self.version = '0.32'
        if cmp(parse_version(self.version), parse_version('0.33')) < 0:
            self.__alternate_meek_fronting_addresses_regex = defaultdict(str)
            self.version = '0.33'
        if cmp(parse_version(self.version), parse_version('0.34')) < 0:
            for sponsor in self.__sponsors.itervalues():
                if sponsor.banner:
                    try:
                        pngdata = io.BytesIO()
                        Image.open(io.BytesIO(base64.b64decode(sponsor.banner))).save(pngdata, 'png')
                        sponsor.banner = base64.b64encode(pngdata.getvalue())
                    except Exception as e:
                        print('Corrupt banner image found for sponsor %s; unable to convert' % sponsor.id)
            self.version = '0.34'
        if cmp(parse_version(self.version), parse_version('0.35')) < 0:
            self.__meek_fronting_disable_SNI = defaultdict(bool)
            for host in self.__hosts.itervalues():
                host.alternate_meek_server_fronting_hosts = None
            for host in self.__deleted_hosts:
                host.alternate_meek_server_fronting_hosts = None
            for host in self.__hosts_to_remove_from_providers:
                host.alternate_meek_server_fronting_hosts = None
            self.version = '0.35'
        if cmp(parse_version(self.version), parse_version('0.36')) < 0:
            self.__vpsnet_account = VPSNetAccount()
            self.version = '0.36'
        if cmp(parse_version(self.version), parse_version('0.37')) < 0:

            # This version adds TCS compatibility

            # No existing hosts use the TCS stack
            for host in self.__hosts.itervalues():
                host.is_TCS = False
            for host in self.__deleted_hosts:
                host.is_TCS = False
            for host in self.__hosts_to_remove_from_providers:
                host.is_TCS = False

            # No existing servers have TCS keys
            for server in self.__servers.itervalues():
                server.TCS_ssh_private_key = None
            for server in self.__deleted_servers.itervalues():
                server.TCS_ssh_private_key = None

            # No existing servers have TCS capabilities
            for server in self.__servers.itervalues():
                if server.capabilities:
                    server.capabilities['ssh-api-requests'] = False
            for server in self.__deleted_servers.itervalues():
                if server.capabilities:
                    server.capabilities['ssh-api-requests'] = False

            # Stub in valid, empty defaults
            self.__linode_account.tcs_base_root_password = ''
            self.__linode_account.tcs_base_host_public_key = ''
            self.__TCS_traffic_rules_set = "{}"
            self.__TCS_psiphond_config_values = {}
            self.version = '0.37'
        if cmp(parse_version(self.version), parse_version('0.38')) < 0:
            self.__TCS_OSL_config = "{}"
            self.version = '0.38'
        if cmp(parse_version(self.version), parse_version('0.39')) < 0:
            self.__default_sponsor_id = None
            self.version = '0.39'
        if cmp(parse_version(self.version), parse_version('0.40')) < 0:
            for server in self.__servers.itervalues():
                if server.capabilities:
                    server.capabilities['UNFRONTED-MEEK-SESSION-TICKET'] = False
            for server in self.__deleted_servers.itervalues():
                if server.capabilities:
                    server.capabilities['UNFRONTED-MEEK-SESSION-TICKET'] = False
            self.version = '0.40'
        if cmp(parse_version(self.version), parse_version('0.41')) < 0:
            for sponsor in self.__sponsors.itervalues():
                for campaign in sponsor.campaigns:
                    campaign.alternate_s3_bucket_name = None
            self.version = '0.41'
        if cmp(parse_version(self.version), parse_version('0.42')) < 0:
            self.__deploy_pave_osls_required_for_propagation_channels = set()
            self.version = '0.42'
        if cmp(parse_version(self.version), parse_version('0.43')) < 0:
            for server in self.__servers.itervalues():
                server.osl_ids = None
                server.osl_discovery_date_range = None
            for server in self.__deleted_servers.itervalues():
                server.osl_ids = None
                server.osl_discovery_date_range = None
            self.version = '0.43'
        if cmp(parse_version(self.version), parse_version('0.44')) < 0:
            # Existing TCS hosts use docker
            for host in self.__hosts.itervalues():
                host.TCS_type = 'DOCKER' if host.is_TCS else None
            for host in self.__deleted_hosts:
                host.TCS_type = 'DOCKER' if host.is_TCS else None
            for host in self.__hosts_to_remove_from_providers:
                host.TCS_type = 'DOCKER' if host.is_TCS else None
            self.version = '0.44'
        if cmp(parse_version(self.version), parse_version('0.45')) < 0:
            self.__alternate_s3_bucket_domains = set()
            self.version = '0.45'
        if cmp(parse_version(self.version), parse_version('0.46')) < 0:
            self.__global_https_request_regexes = []
            self.version = '0.46'
        if cmp(parse_version(self.version), parse_version('0.47')) < 0:
            self.__vps247_account = VPS247Account()
            self.version = '0.47'
        if cmp(parse_version(self.version), parse_version('0.48')) < 0:
            for propagation_channel in self.__propagation_channels.itervalues():
                propagation_channel.new_osl_discovery_servers_count = 0
                propagation_channel.max_osl_discovery_server_age_in_days = 0
            self.version = '0.48'
        if cmp(parse_version(self.version), parse_version('0.49')) < 0:
            # Note: this tactics config template is for illustration only
            self.__TCS_tactics_config_template = '''
            {
              "RequestPublicKey" : "%s",
              "RequestPrivateKey" : "%s",
              "RequestObfuscatedKey" : "%s",
              "DefaultTactics" : {
                "TTL" : "1s",
                "Probability" : 1.0,
                "Parameters" : {
                }
              }
            }
            '''
            for host in self.__hosts.values() + list(self.__deleted_hosts) + list(self.__hosts_to_remove_from_providers):
                host.tactics_request_public_key = None
                host.tactics_request_private_key = None
                host.tactics_request_obfuscated_key = None
            for server in self.__servers.values() + self.__deleted_servers.values():
                server.capabilities['FRONTED-MEEK-TACTICS'] = False
                server.configuration_version = INITIAL_SERVER_CONFIGURATION_VERSION
            for server in self.__servers.itervalues():
                if server.capabilities['FRONTED-MEEK']:
                    server.capabilities['FRONTED-MEEK-TACTICS'] = True
                    server.configuration_version = INITIAL_SERVER_CONFIGURATION_VERSION + 1
                    host = self.__hosts[server.host_id]
                    public_key, private_key = self.generate_nacl_keypair()
                    host.tactics_request_public_key = public_key
                    host.tactics_request_private_key = private_key
                    host.tactics_request_obfuscated_key = self.generate_obfuscated_key(base64_encode=True)
            self.version = '0.49'
        if cmp(parse_version(self.version), parse_version('0.50')) < 0:
            for server in self.__servers.values() + self.__deleted_servers.values():
                server.capabilities['QUIC'] = False
                server.ssh_obfuscated_quic_port = None
            self.version = '0.50'
        if cmp(parse_version(self.version), parse_version('0.51')) < 0:
            for server in self.__servers.values() + self.__deleted_servers.values():
                server.capabilities['TAPDANCE'] = False
                server.ssh_obfuscated_tapdance_port = None
            self.version = '0.51'
        if cmp(parse_version(self.version), parse_version('0.52')) < 0:
            self.__TCS_blocklist_csv = ""
            self.version = '0.52'
        if cmp(parse_version(self.version), parse_version('0.53')) < 0:
            for server in self.__servers.values() + self.__deleted_servers.values():
                server.capabilities['FRONTED-MEEK-QUIC'] = False
            self.version = '0.53'
        if cmp(parse_version(self.version), parse_version('0.54')) < 0:
            self.__server_entry_signing_key_pair = None
            self.__exchange_obfuscation_key = base64.b64encode(os.urandom(32))
            self.version = '0.54'
        if cmp(parse_version(self.version), parse_version('0.55')) < 0:
            self.__routes_signing_public_key = None
            self.version = '0.55'
        if cmp(parse_version(self.version), parse_version('0.56')) < 0:
            self.__linode_account.api_token = ''
            self.version = '0.56'
        if cmp(parse_version(self.version), parse_version('0.57')) < 0:
            self.__ssh_ip_address_whitelist = []
            self.version = '0.57'
        if cmp(parse_version(self.version), parse_version('0.58')) < 0:
            for host in self.__hosts.values() + list(self.__deleted_hosts) + list(self.__hosts_to_remove_from_providers):
                host.fronting_provider_id = None
            self.__fronting_provider_id_aliases = {}
            self.version = '0.58'
        if cmp(parse_version(self.version), parse_version('0.59')) < 0:
            self.__TCS_iptables_output_rules = []
            self.version = '0.59'
        if cmp(parse_version(self.version), parse_version('0.60')) < 0:
            for host in self.__hosts.values() + list(self.__deleted_hosts) + list(self.__hosts_to_remove_from_providers):
                host.passthrough_address = None
            self.__passthrough_addresses = []
            self.version = '0.60'
        if cmp(parse_version(self.version), parse_version('0.61')) < 0:
            self.__standard_ossh_ports = set()
            self.__standard_ossh_ports.add(443)
            self.version = '0.61'
        if cmp(parse_version(self.version), parse_version('0.62')) < 0:
            for host in self.__hosts.values() + list(self.__deleted_hosts) + list(self.__hosts_to_remove_from_providers):
                host.run_packet_manipulator = None
            self.version = '0.62'
        if cmp(parse_version(self.version), parse_version('0.63')) < 0:
            self.__alternate_feedback_upload_urls = set()
            self.version = '0.63'
        if cmp(parse_version(self.version), parse_version('0.64')) < 0:
            for server in self.__servers.values() + self.__deleted_servers.values():
                server.capabilities['CONJURE'] = False
                server.ssh_obfuscated_conjure_port = None
            self.version = '0.64'

    def initialize_plugins(self):
        for plugin in plugins:
            if hasattr(plugin, 'initialize'):
                plugin.initialize(self)

    def show_status(self):
        # NOTE: verbose mode prints credentials to stdout
        print textwrap.dedent('''
            Sponsors:               %d
            Channels:               %d
            Twitter Campaigns:      %d
            Email Campaigns:        %d
            Total Campaigns:        %d
            Hosts:                  %d (VPN: %d, TCS: %d)
            Servers:                %d
            Providers:              %d
            Automation Bucket:      %s
            Stats Server:           %s
            Windows Client Version: %s %s
            Android Client Version: %s %s
            AWS Account:            %s
            Provider Ranks:         %s
            Linode Account:         %s
            DigitalOcean Account:   %s
            VPSNet Account          %s
            VPS247 Account          %s
            ElasticHosts Account:   %s
            Deploys Pending:        Host Implementations    %d
                                    Host Data               %s
                                    Windows Campaign Builds %d
                                    Android Campaign Builds %d
                                    Stats Server Config     %s
                                    Email Server Config     %s
                                    Websites                %d
                                    Pave OSLs               %d
            ''') % (
                len(self.__sponsors),
                len(self.__propagation_channels),
                sum([len(filter(lambda x:x.propagation_mechanism_type == 'twitter', sponsor.campaigns))
                     for sponsor in self.__sponsors.itervalues()]),
                sum([len(filter(lambda x:x.propagation_mechanism_type == 'email-autoresponder', sponsor.campaigns))
                     for sponsor in self.__sponsors.itervalues()]),
                sum([len(sponsor.campaigns)
                     for sponsor in self.__sponsors.itervalues()]),
                len(self.__hosts), len([s for s in self.__servers.itervalues() if s.capabilities['VPN'] == True]), len([h for h in self.__hosts.itervalues() if h.is_TCS == True and h.TCS_type == 'NATIVE']),
                len(self.__servers),
                len(set([h.provider for h in self.__hosts.itervalues()])),
                self.__automation_bucket if self.__automation_bucket else 'None',
                self.__stats_server_account.ip_address if self.__stats_server_account else 'None',
                self.__client_versions[CLIENT_PLATFORM_WINDOWS][-1].version if self.__client_versions[CLIENT_PLATFORM_WINDOWS] else 'None',
                self.__client_versions[CLIENT_PLATFORM_WINDOWS][-1].description if self.__client_versions[CLIENT_PLATFORM_WINDOWS] else '',
                self.__client_versions[CLIENT_PLATFORM_ANDROID][-1].version if self.__client_versions[CLIENT_PLATFORM_ANDROID] else 'None',
                self.__client_versions[CLIENT_PLATFORM_ANDROID][-1].description if self.__client_versions[CLIENT_PLATFORM_ANDROID] else '',
                'Configured' if self.__aws_account.access_id else 'None',
                'Configured' if self.__provider_ranks else 'None',
                'Configured' if self.__linode_account.api_key else 'None',
                'Configured' if self.__digitalocean_account.client_id and self.__digitalocean_account.api_key else 'None',
                'Configured' if self.__vpsnet_account.account_id and self.__vpsnet_account.api_key else 'None',
                'Configured' if self.__vps247_account.account_id and self.__vps247_account.api_key else 'None',
                'Configured' if self.__elastichosts_accounts else 'None',
                len(self.__deploy_implementation_required_for_hosts),
                'Yes' if self.__deploy_data_required_for_all else 'No',
                len(self.__deploy_builds_required_for_campaigns[CLIENT_PLATFORM_WINDOWS]),
                len(self.__deploy_builds_required_for_campaigns[CLIENT_PLATFORM_ANDROID]),
                'Yes' if self.__deploy_stats_config_required else 'No',
                'Yes' if self.__deploy_email_config_required else 'No',
                len(self.__deploy_website_required_for_sponsors),
                len(self.__deploy_pave_osls_required_for_propagation_channels),
                )

    def show_client_versions(self):
        for platform in self.__client_versions.iterkeys():
            print platform
            for client_version in self.__client_versions[platform]:
                print client_version.logs[0][0], client_version.version, client_version.description

    def __show_logs(self, obj):
        for timestamp, message in obj.get_logs():
            print '%s: %s' % (timestamp.isoformat(), message)
        print ''

    def show_sponsors(self):
        for s in self.__sponsors.itervalues():
            self.show_sponsor(s.name)

    def show_sponsor(self, sponsor_name):
        s = self.get_sponsor_by_name(sponsor_name)
        print textwrap.dedent('''
            ID:                      %(id)s
            Name:                    %(name)s
            Home Pages:              %(home_pages)s
            Mobile Home Pages:       %(mobile_home_pages)s
            Page View Regexes:       %(page_view_regexes)s
            HTTPS Request Regexes:   %(https_request_regexes)s
            Campaigns:               %(campaigns)s
            ''') % {
                    'id': s.id,
                    'name': s.name,
                    'home_pages': '\n                         '.join(['%s: %s' % (region.ljust(5) if region else 'All',
                                                         '\n                                '.join([h.url for h in home_pages]))
                                                         for region, home_pages in sorted(s.home_pages.items())]),
                    'mobile_home_pages': '\n                         '.join(['%s: %s' % (region.ljust(5) if region else 'All',
                                                         '\n                                '.join([h.url for h in mobile_home_pages]))
                                                         for region, mobile_home_pages in sorted(s.mobile_home_pages.items())]),
                    'page_view_regexes': '\n                         '.join(['%s -> %s' % (page_view_regex.regex, page_view_regex.replace)
                                                                             for page_view_regex in s.page_view_regexes]),
                    'https_request_regexes': '\n                         '.join(['%s -> %s' % (https_request_regex.regex, https_request_regex.replace)
                                                                                 for https_request_regex in s.https_request_regexes]),
                    'campaigns': '\n                         '.join(['%s %s %s %s' % (
                                                             self.__propagation_channels[c.propagation_channel_id].name,
                                                             c.propagation_mechanism_type,
                                                             c.account[0] if c.account else 'None',
                                                             c.s3_bucket_name)
                                            for c in s.campaigns])
                    }
        self.__show_logs(s)

    def show_campaigns_on_propagation_channel(self, propagation_channel_name):
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        for sponsor in self.__sponsors.itervalues():
            for campaign in sponsor.campaigns:
                if campaign.propagation_channel_id == propagation_channel.id:
                    print textwrap.dedent('''
                            Sponsor:                %s
                            Propagation Mechanism:  %s
                            Account:                %s
                            Bucket Name:            %s''') % (
                                sponsor.name,
                                campaign.propagation_mechanism_type,
                                campaign.account[0] if campaign.account else 'None',
                                campaign.s3_bucket_name)

    def show_propagation_channels(self, verbose=True):
        for p in self.__propagation_channels.itervalues():
            self.show_propagation_channel(p.name, verbose=verbose)

    def show_propagation_channel(self, propagation_channel_name, now=None, verbose=True):
        if now == None:
            now = datetime.datetime.now()
        p = self.get_propagation_channel_by_name(propagation_channel_name)
        embedded_servers = [server.id + (' (permanent)' if server.is_permanent else '') for server in self.__servers.itervalues()
                            if server.propagation_channel_id == p.id and server.is_embedded]
        old_propagation_servers = [server.id for server in self.__servers.itervalues()
                                   if server.propagation_channel_id == p.id and
                                   not server.is_embedded and not server.discovery_date_range]
        current_discovery_servers = ['%s - %s : %s' % (server.discovery_date_range[0].isoformat(),
                                                       server.discovery_date_range[1].isoformat(),
                                                       server.id)
                                     for server in self.__servers.itervalues()
                                     if server.propagation_channel_id == p.id and server.discovery_date_range and
                                     (server.discovery_date_range[0] <= now < server.discovery_date_range[1])]
        current_discovery_servers.sort()
        future_discovery_servers = ['%s - %s : %s' % (server.discovery_date_range[0].isoformat(),
                                                      server.discovery_date_range[1].isoformat(),
                                                      server.id)
                                    for server in self.__servers.itervalues()
                                    if server.propagation_channel_id == p.id and server.discovery_date_range and
                                       server.discovery_date_range[0] > now]
        future_discovery_servers.sort()
        old_discovery_servers = ['%s - %s : %s' % (server.discovery_date_range[0].isoformat(),
                                                   server.discovery_date_range[1].isoformat(),
                                                   server.id)
                                 for server in self.__servers.itervalues()
                                 if server.propagation_channel_id == p.id and server.discovery_date_range and
                                    now >= server.discovery_date_range[1]]
        old_discovery_servers.sort()

        print textwrap.dedent('''
            ID:                                  %s
            Name:                                %s
            Propagation Mechanisms:              %s
            Propagator Managed Upgrades          %s
            New Propagation Servers:             %s
            Max Propagation Server Age (days):   %s
            New Discovery Servers:               %s
            Max Discovery Server Age (days):     %s
            New OSL Discovery Servers:           %s
            Max OSL Discovery Server Age (days): %s
            ''') % (
                p.id,
                p.name,
                '\n                                   '.join(p.propagation_mechanism_types),
                p.propagator_managed_upgrades,
                str(p.new_propagation_servers_count),
                str(p.max_propagation_server_age_in_days),
                str(p.new_discovery_servers_count),
                str(p.max_discovery_server_age_in_days),
                str(p.new_osl_discovery_servers_count),
                str(p.max_osl_discovery_server_age_in_days))

        if verbose:
            print textwrap.dedent('''
                Embedded Servers:                  %s
                Discovery Servers:                 %s
                Future Discovery Servers:          %s
                Old Propagation Servers:           %s
                Old Discovery Servers:             %s
                ''') % (
                    '\n                                   '.join(embedded_servers),
                    '\n                                   '.join(current_discovery_servers),
                    '\n                                   '.join(future_discovery_servers),
                    '\n                                   '.join(old_propagation_servers),
                    '\n                                   '.join(old_discovery_servers))
            self.__show_logs(p)

    def show_servers(self):
        for s in self.__servers.itervalues():
            self.show_server(s.id)

    def show_servers_on_host(self, host_id):
        for s in self.__servers.itervalues():
            if s.host_id == host_id:
                self.show_server(s.id)

    def show_server(self, server_id):
        s = self.__servers[server_id]
        print textwrap.dedent('''
            Server:                   %s
            Host:                     %s%s %s %s / %s
            IP Address:               %s
            Region:                   %s
            Propagation Channel:      %s
            Is Embedded:              %s
            Is Permanent:             %s
            Discovery Date Range:     %s
            OSL Discovery Date Range: %s
            Capabilities:             %s
            Configuration Version:    %d
            ''') % (
                s.id,
                s.host_id,
                " (TCS " + self.__hosts[s.host_id].TCS_type + ")" if self.__hosts[s.host_id].is_TCS else "",
                self.__hosts[s.host_id].ip_address,
                self.__hosts[s.host_id].ssh_username,
                self.__hosts[s.host_id].ssh_password,
                s.ip_address,
                self.__hosts[s.host_id].region,
                self.__propagation_channels[s.propagation_channel_id].name if s.propagation_channel_id else 'None',
                s.is_embedded,
                s.is_permanent,
                ('%s - %s' % (s.discovery_date_range[0].isoformat(),
                            s.discovery_date_range[1].isoformat())) if s.discovery_date_range else 'None',
                ('%s - %s' % (s.osl_discovery_date_range[0].isoformat(),
                            s.osl_discovery_date_range[1].isoformat())) if s.osl_discovery_date_range else 'None',
                ', '.join([capability for capability, enabled in s.capabilities.iteritems() if enabled]),
                s.configuration_version if s.configuration_version else 0)
        self.__show_logs(s)

    def show_server_by_diagnostic_id(self, diagnostic_id):
        for s in self.__servers.itervalues():
            if diagnostic_id == self.__get_server_tag(s)[0:8]:
                self.show_server(s.id)

    def show_host(self, host_id, show_logs=False):
        host = self.__hosts[host_id]
        servers = [self.__servers[s].id + (' (permanent)' if self.__servers[s].is_permanent else '')
                   for s in self.__servers
                   if self.__servers[s].host_id == host_id]

        print textwrap.dedent('''
            Host ID:                 %(id)s%(is_TCS)s
            Provider:                %(provider)s (%(provider_id)s)
            Datacenter:              %(datacenter_name)s
            IP Address:              %(ip_address)s
            Region:                  %(region)s
            SSH:                     %(ssh_port)s %(ssh_username)s / %(ssh_password)s
            Stats User:              %(stats_ssh_username)s / %(stats_ssh_password)s
            Servers:                 %(servers)s
            ''') % {
                    'id': host.id,
                    'is_TCS' : " (TCS " + host.TCS_type + ")" if host.is_TCS else "",
                    'provider': host.provider,
                    'provider_id': host.provider_id,
                    'datacenter_name': host.datacenter_name,
                    'ip_address': host.ip_address,
                    'region': host.region,
                    'ssh_port': host.ssh_port,
                    'ssh_username': host.ssh_username,
                    'ssh_password': host.ssh_password,
                    'stats_ssh_username': host.stats_ssh_username,
                    'stats_ssh_password': host.stats_ssh_password,
                    'servers': '\n                         '.join(servers)
                    }

        if show_logs:
            self.__show_logs(host)

    def show_provider_ranks(self):
        for r in self.__provider_ranks:
            print textwrap.dedent('''
                Provider:   %s
                Rank:       %s
                ''') % (r.provider, r.rank)

    def __generate_id(self):
        count = 16
        chars = '0123456789ABCDEF'
        return ''.join([chars[ord(os.urandom(1)) % len(chars)] for i in range(count)])

    def get_propagation_channel_by_name(self, name):
        matches = filter(lambda x: x.name == name,
                         self.__propagation_channels.itervalues())
        return matches[0] if matches else None

    def get_propagation_channel_by_id(self, id):
        return self.__propagation_channels[id] if id in self.__propagation_channels else None

    def add_propagation_channel(self, name, propagation_mechanism_types, propagator_managed_upgrades=False):
        assert(self.is_locked)
        self.import_propagation_channel(self.__generate_id(), name, propagation_mechanism_types, propagator_managed_upgrades)

    def import_propagation_channel(self, id, name, propagation_mechanism_types, propagator_managed_upgrades):
        assert(self.is_locked)
        for type in propagation_mechanism_types:
            assert(type in self.__propagation_mechanisms)
        propagation_channel = PropagationChannel(id, name, propagation_mechanism_types, propagator_managed_upgrades, 0, 0, 0, 0, 0, 0)
        assert(id not in self.__propagation_channels)
        assert(not filter(lambda x: x.name == name, self.__propagation_channels.itervalues()))
        self.__propagation_channels[id] = propagation_channel

    def set_propagation_channel_new_osl_discovery_servers_count(self, propagation_channel_name, count):
        assert(self.is_locked)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_channel.new_osl_discovery_servers_count = count
        propagation_channel.log('New OSL discovery servers count set to %d' % (count,))

    def set_propagation_channel_new_discovery_servers_count(self, propagation_channel_name, count):
        assert(self.is_locked)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_channel.new_discovery_servers_count = count
        propagation_channel.log('New discovery servers count set to %d' % (count,))

    def set_propagation_channel_new_propagation_servers_count(self, propagation_channel_name, count):
        assert(self.is_locked)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_channel.new_propagation_servers_count = count
        propagation_channel.log('New propagation servers count set to %d' % (count,))

    def set_propagation_channel_max_osl_discovery_server_age_in_days(self, propagation_channel_name, age):
        assert(self.is_locked)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_channel.max_osl_discovery_server_age_in_days = age
        propagation_channel.log('Max OSL discovery server age set to %d days' % (age,))

    def set_propagation_channel_max_discovery_server_age_in_days(self, propagation_channel_name, age):
        assert(self.is_locked)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_channel.max_discovery_server_age_in_days = age
        propagation_channel.log('Max discovery server age set to %d days' % (age,))

    def set_propagation_channel_max_propagation_server_age_in_days(self, propagation_channel_name, age):
        assert(self.is_locked)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_channel.max_propagation_server_age_in_days = age
        propagation_channel.log('Max propagation server age set to %d days' % (age,))

    def get_sponsor_by_name(self, name):
        matches = filter(lambda x: x.name == name,
                         self.__sponsors.itervalues())
        return matches[0] if matches else None

    def get_sponsor_by_id(self, id):
        return self.__sponsors[id] if id in self.__sponsors else None

    def add_sponsor(self, name):
        assert(self.is_locked)
        self.import_sponsor(self.__generate_id(), name)

    def import_sponsor(self, id, name):
        assert(self.is_locked)
        sponsor = Sponsor(id, name, None, None, None, {}, {}, [], [], [])
        assert(id not in self.__sponsors)
        assert(not filter(lambda x: x.name == name, self.__sponsors.itervalues()))
        self.__sponsors[id] = sponsor

    def set_sponsor_banner(self, name, banner_filename):
        assert(self.is_locked)
        with open(banner_filename, 'rb') as file:
            banner = file.read()
        # Ensure that the banner is a PNG
        assert(banner[:8] == '\x89PNG\r\n\x1a\n')
        sponsor = self.get_sponsor_by_name(name)
        sponsor.banner = base64.b64encode(banner)
        sponsor.log('set banner')
        for campaign in sponsor.campaigns:
            for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                self.__deploy_builds_required_for_campaigns[platform].add(
                    (campaign.propagation_channel_id, sponsor.id))
            campaign.log('marked for build and publish (new banner)')

    def set_sponsor_website_banner(self, name, website_banner_filename, website_banner_link):
        assert(self.is_locked)
        with open(website_banner_filename, 'rb') as file:
            website_banner = file.read()
        # Ensure that the banner is a PNG
        assert(website_banner[:8] == '\x89PNG\r\n\x1a\n')
        sponsor = self.get_sponsor_by_name(name)
        sponsor.website_banner = base64.b64encode(website_banner)
        sponsor.website_banner_link = website_banner_link
        self.__deploy_website_required_for_sponsors.add(sponsor.id)
        sponsor.log('set website_banner, marked for publish')

    def flag_website_updated(self):
        assert(self.is_locked)
        for sponsor in self.__sponsors.itervalues():
            self.__deploy_website_required_for_sponsors.add(sponsor.id)
            sponsor.log('website updated, marked for publish')

    def add_sponsor_email_campaign(self, sponsor_name, propagation_channel_name, email_account):
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_mechanism_type = 'email-autoresponder'
        assert(propagation_mechanism_type in propagation_channel.propagation_mechanism_types)
        # TODO: assert(email_account not in ...)
        campaign = SponsorCampaign(propagation_channel.id,
                                   propagation_mechanism_type,
                                   EmailPropagationAccount(email_account),
                                   None,
                                   None,
                                   None,
                                   None,
                                   False)
        if campaign not in sponsor.campaigns:
            sponsor.campaigns.append(campaign)
            sponsor.log('add email campaign %s' % (email_account,))
            for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                self.__deploy_builds_required_for_campaigns[platform].add(
                        (campaign.propagation_channel_id, sponsor.id))
            self.__deploy_pave_osls_required_for_propagation_channels.add(propagation_channel.id)
            campaign.log('marked for build and publish (new campaign)')

    def set_default_email_autoresponder_account(self, email_account):
        assert(self.is_locked)

        # TODO: Make sure the sponsor campaign that provides this address isn't
        # deleted. Right now we don't have a "delete sponsor campaign" function.

        # Make sure the email address exists in a campaign.
        exists = False
        for sponsor in self.__sponsors.itervalues():
            for campaign in sponsor.campaigns:
                if type(campaign.account) == EmailPropagationAccount \
                        and campaign.account.email_address == email_account:
                    exists = True
                    break

            if exists:
                break
        assert(exists)

        self.__default_email_autoresponder_account = EmailPropagationAccount(email_account)

    def add_sponsor_twitter_campaign(self, sponsor_name,
                                     propagation_channel_name,
                                     twitter_account_name,
                                     twitter_account_consumer_key,
                                     twitter_account_consumer_secret,
                                     twitter_account_access_token_key,
                                     twitter_account_access_token_secret):
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_mechanism_type = 'twitter'
        assert(propagation_mechanism_type in propagation_channel.propagation_mechanism_types)
        campaign = SponsorCampaign(propagation_channel.id,
                                   propagation_mechanism_type,
                                   TwitterPropagationAccount(
                                        twitter_account_name,
                                        twitter_account_consumer_key,
                                        twitter_account_consumer_secret,
                                        twitter_account_access_token_key,
                                        twitter_account_access_token_secret),
                                   None,
                                   None,
                                   None,
                                   None,
                                   False)
        if campaign not in sponsor.campaigns:
            sponsor.campaigns.append(campaign)
            sponsor.log('add twitter campaign %s' % (twitter_account_name,))
            for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                self.__deploy_builds_required_for_campaigns[platform].add(
                        (campaign.propagation_channel_id, sponsor.id))
            self.__deploy_pave_osls_required_for_propagation_channels.add(propagation_channel.id)
            campaign.log('marked for build and publish (new campaign)')

    def add_sponsor_static_download_campaign(self, sponsor_name, propagation_channel_name):
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_mechanism_type = 'static-download'
        assert(propagation_mechanism_type in propagation_channel.propagation_mechanism_types)
        campaign = SponsorCampaign(propagation_channel.id,
                                   propagation_mechanism_type,
                                   None,
                                   None,
                                   None,
                                   None,
                                   None,
                                   False)
        if campaign not in sponsor.campaigns:
            sponsor.campaigns.append(campaign)
            sponsor.log('add static download campaign')
            for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                self.__deploy_builds_required_for_campaigns[platform].add(
                        (campaign.propagation_channel_id, sponsor.id))
            self.__deploy_pave_osls_required_for_propagation_channels.add(propagation_channel.id)
            campaign.log('marked for build and publish (new campaign)')

    def set_sponsor_campaign_s3_bucket_name(self, sponsor_name,
                                            propagation_channel_name, account,
                                            s3_bucket_name):
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        for campaign in sponsor.campaigns:
            if (campaign.propagation_channel_id == propagation_channel.id and
                ((campaign.account == None and account == None) or campaign.account[0] == account)):
                    campaign.s3_bucket_name = s3_bucket_name
                    campaign.log('set campaign s3 bucket name to %s' % (s3_bucket_name,))
                    for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                        self.__deploy_builds_required_for_campaigns[platform].add(
                            (campaign.propagation_channel_id, sponsor.id))
                    self.__deploy_pave_osls_required_for_propagation_channels.add(propagation_channel.id)
                    campaign.log('marked for build and publish (modified campaign)')

    def set_sponsor_campaign_custom_download_site(self, sponsor_name, propagation_channel_name, account, is_custom):
        sponsor = self.get_sponsor_by_name(sponsor_name)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        for campaign in sponsor.campaigns:
            if (campaign.propagation_channel_id == propagation_channel.id and
                ((campaign.account == None and account == None) or campaign.account[0] == account)):
                campaign.custom_download_site = is_custom
                campaign.log('set campaign custom_download_site to %s' % is_custom)
                if not is_custom:
                    self.__deploy_website_required_for_sponsors.add(sponsor.id)
                    campaign.log('marked sponsor website as needing new deploy')

    def set_sponsor_home_page(self, sponsor_name, region, url):
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        home_page = SponsorHomePage(region, url)
        if region not in sponsor.home_pages:
            sponsor.home_pages[region] = []
        if home_page not in sponsor.home_pages[region]:
            sponsor.home_pages[region].append(home_page)
            sponsor.log('set home page %s for %s' % (url, region if region else 'All'))
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def set_sponsor_mobile_home_page(self, sponsor_name, region, url):
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        mobile_home_page = SponsorHomePage(region, url)
        if region not in sponsor.mobile_home_pages:
            sponsor.mobile_home_pages[region] = []
        if mobile_home_page not in sponsor.mobile_home_pages[region]:
            sponsor.mobile_home_pages[region].append(mobile_home_page)
            sponsor.log('set mobile home page %s for %s' % (url, region if region else 'All'))
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def remove_sponsor_home_page(self, sponsor_name, region, url):
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        home_page = SponsorHomePage(region, url)
        if (region in sponsor.home_pages
            and home_page in sponsor.home_pages[region]):
            sponsor.home_pages[region].remove(home_page)
            sponsor.log('deleted home page %s for %s' % (url, region))
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def set_sponsor_page_view_regex(self, sponsor_name, regex, replace):
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        if not [rx for rx in sponsor.page_view_regexes if rx.regex == regex]:
            sponsor.page_view_regexes.append(SponsorRegex(regex, replace))
            sponsor.log('set page view regex %s; replace %s' % (regex, replace))
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def remove_sponsor_page_view_regex(self, sponsor_name, regex):
        '''
        Note that the regex part of the regex+replace pair is unique, so only
        it has to be passed in when removing.
        '''
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        match = [sponsor.page_view_regexes.pop(idx)
                 for (idx, rx)
                 in enumerate(sponsor.page_view_regexes)
                 if rx.regex == regex]
        if match:
            sponsor.page_view_regexes.remove(regex)
            sponsor.log('deleted page view regex %s' % regex)
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def set_global_https_request_regex(self, regex, replace):
        assert(self.is_locked)
        if not [rx for rx in self.__global_https_request_regexes if rx.regex == regex]:
            self.__global_https_request_regexes.append(SponsorRegex(regex, replace))
            self.__deploy_data_required_for_all = True

    def set_sponsor_https_request_regex(self, sponsor_name, regex, replace):
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        if not [rx for rx in sponsor.https_request_regexes if rx.regex == regex]:
            sponsor.https_request_regexes.append(SponsorRegex(regex, replace))
            sponsor.log('set https request regex %s; replace %s' % (regex, replace))
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def remove_sponsor_https_request_regex(self, sponsor_name, regex):
        '''
        Note that the regex part of the regex+replace pair is unique, so only
        it has to be passed in when removing.
        '''
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        match = [sponsor.https_request_regexes.pop(idx)
                 for (idx, rx)
                 in enumerate(sponsor.https_request_regexes)
                 if rx.regex == regex]
        if match:
            sponsor.https_request_regexes.remove(regex)
            sponsor.log('deleted https request regex %s' % regex)
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def set_sponsor_name(self, sponsor_name, new_sponsor_name):
        assert(self.is_locked)
        assert(not filter(lambda x: x.name == new_sponsor_name, self.__sponsors.itervalues()))
        sponsor = self.get_sponsor_by_name(sponsor_name)
        sponsor.name = (new_sponsor_name)
        self.__deploy_stats_config_required = True
        sponsor.log('set sponsor name from \'%s\' to \'%s\'' % (sponsor_name, new_sponsor_name))

    def set_sponsor_override_data_sponsor_id(self, sponsor_name, use_data_from_sponsor_name):
        assert(self.is_locked)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        override_sponsor = self.get_sponsor_by_name(use_data_from_sponsor_name)
        sponsor.use_data_from_sponsor_id = override_sponsor.id
        for campaign in sponsor.campaigns:
            for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                self.__deploy_builds_required_for_campaigns[platform].add(
                    (campaign.propagation_channel_id, sponsor.id))
            campaign.log('marked for build and publish (new banner override)')
        self.__deploy_data_required_for_all = True
        self.__deploy_website_required_for_sponsors.add(sponsor.id)
        sponsor.log('set use data from sponsor \'%s\'' % (use_data_from_sponsor_name))

    def get_server_by_ip_address(self, ip_address):
        servers = filter(lambda x: x.ip_address == ip_address, self.__servers.itervalues())
        if len(servers) == 1:
            return servers[0]
        return None

    def get_server_by_internal_ip_address(self, ip_address):
        servers = filter(lambda x: x.internal_ip_address == ip_address, self.__servers.itervalues())
        if len(servers) == 1:
            return servers[0]
        return None

    def get_deleted_server_by_ip_address(self, ip_address):
        servers = filter(lambda x: x.ip_address == ip_address, self.__deleted_servers.itervalues())
        if len(servers) == 1:
            return servers[0]
        return None

    def get_deleted_server_by_host_id(self, host_id):
        servers = filter(lambda x: x.host_id == host_id, self.__deleted_servers.itervalues())
        if len(servers) == 1:
            return servers[0]
        return None

    def get_deleted_host_by_ip_address(self, ip_address):
        hosts = filter(lambda x: x.ip_address == ip_address, self.__deleted_hosts)
        if len(hosts) == 1:
            return hosts[0]
        return None

    def get_deleted_host_by_host_id(self, host_id):
        hosts = filter(lambda x: x.id == host_id, self.__deleted_hosts)
        if len(hosts) == 1:
            return hosts[0]
        return None

    def get_host_object(self, id, is_TCS, TCS_type, provider, provider_id, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key,
                        stats_ssh_username, stats_ssh_password, datacenter_name, region, meek_server_port,
                        meek_server_obfuscated_key, meek_server_fronting_domain, meek_server_fronting_host,
                        alternate_meek_server_fronting_hosts, meek_cookie_encryption_public_key,
                        meek_cookie_encryption_private_key,
                        tactics_request_public_key, tactics_request_private_key, tactics_request_obfuscated_key,
                        run_packet_manipulator):
        return Host(id,
                    is_TCS,
                    TCS_type,
                    provider,
                    provider_id,
                    ip_address,
                    ssh_port,
                    ssh_username,
                    ssh_password,
                    ssh_host_key,
                    stats_ssh_username,
                    stats_ssh_password,
                    datacenter_name,
                    region,
                    None, # fronting_provider_id
                    None, # passthrough_address
                    meek_server_port,
                    meek_server_obfuscated_key,
                    meek_server_fronting_domain,
                    meek_server_fronting_host,
                    alternate_meek_server_fronting_hosts,
                    meek_cookie_encryption_public_key,
                    meek_cookie_encryption_private_key,
                    tactics_request_public_key,
                    tactics_request_private_key,
                    tactics_request_obfuscated_key,
                    run_packet_manipulator
                    )

    def get_server_object(self, id, host_id, ip_address, egress_ip_address, internal_ip_address, propagation_channel_id,
                        is_embedded, is_permanent, discovery_date_range, capabilities, web_server_port, web_server_secret,
                        web_server_certificate, web_server_private_key, ssh_port, ssh_username, ssh_password,
                        ssh_host_key, TCS_ssh_private_key, ssh_obfuscated_port, ssh_obfuscated_quic_port,
                        ssh_obfuscated_tapdance_port, ssh_obfuscated_conjure_port,
                        ssh_obfuscated_key, alternate_ssh_obfuscated_ports, osl_ids, osl_discovery_date_range, configuration_version):
        return Server(id,
                    host_id,
                    ip_address,
                    egress_ip_address,
                    internal_ip_address,
                    propagation_channel_id,
                    is_embedded,
                    is_permanent,
                    discovery_date_range,
                    capabilities,
                    web_server_port,
                    web_server_secret,
                    web_server_certificate,
                    web_server_private_key,
                    ssh_port,
                    ssh_username,
                    ssh_password,
                    ssh_host_key,
                    TCS_ssh_private_key,
                    ssh_obfuscated_port,
                    ssh_obfuscated_quic_port,
                    ssh_obfuscated_tapdance_port,
                    ssh_obfuscated_conjure_port,
                    ssh_obfuscated_key,
                    alternate_ssh_obfuscated_ports,
                    osl_ids,
                    osl_discovery_date_range,
                    configuration_version)

    def export_host_and_server(self, host_id_list):

        import pickle
        exp_entry = list()

        for host_id in host_id_list:
            host = self.__hosts[host_id]
            server = [s for s in self.get_servers() if s.host_id == host.id][0]

            exp_host = (host.id,
                        host.is_TCS,
                        host.TCS_type,
                        host.provider,
                        host.provider_id,
                        host.ip_address,
                        host.ssh_port,
                        host.ssh_username,
                        host.ssh_password,
                        host.ssh_host_key,
                        host.stats_ssh_username,
                        host.stats_ssh_password,
                        host.datacenter_name,
                        host.region,
                        host.fronting_provider_id,
                        host.passthrough_address,
                        host.meek_server_port,
                        host.meek_server_obfuscated_key,
                        host.meek_server_fronting_domain,
                        host.meek_server_fronting_host,
                        host.alternate_meek_server_fronting_hosts,
                        host.meek_cookie_encryption_public_key,
                        host.meek_cookie_encryption_private_key,
                        host.tactics_request_public_key,
                        host.tactics_request_private_key,
                        host.tactics_request_obfuscated_key)

            exp_server = (server.id,
                            server.host_id,
                            server.ip_address,
                            server.egress_ip_address,
                            server.internal_ip_address,
                            server.propagation_channel_id,
                            server.is_embedded,
                            server.is_permanent,
                            server.discovery_date_range,
                            server.capabilities,
                            server.web_server_port,
                            server.web_server_secret,
                            server.web_server_certificate,
                            server.web_server_private_key,
                            server.ssh_port,
                            server.ssh_username,
                            server.ssh_password,
                            server.ssh_host_key,
                            server.TCS_ssh_private_key,
                            server.ssh_obfuscated_port,
                            server.ssh_obfuscated_quic_port,
                            server.ssh_obfuscated_tapdance_port,
                            server.ssh_obfuscated_conjure_port,
                            server.ssh_obfuscated_key,
                            server.alternate_ssh_obfuscated_ports,
                            server.osl_ids,
                            server.osl_discovery_date_range,
                            server.configuration_version)

            exp_entry.append([exp_host, exp_server])

        with open("entries.txt", 'ab') as export_file:
            pickle.dump(exp_entry, export_file)

    def import_host_and_server(self):

        import pickle

        assert(self.is_locked)

        with open("entries.txt", "rb") as import_file:
            entries_list = pickle.load(import_file)

            for imp_entry in entries_list:

                host = Host(*imp_entry[0])
                server = Server(*imp_entry[1])

                assert(host.id not in self.__hosts)
                assert(server.id not in self.__servers)

                self.__hosts[host.id] = host
                self.__servers[server.id] = server

    # obsolete
    def import_host(self, id, is_TCS, TCS_type, provider, provider_id, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key,
                    stats_ssh_username, stats_ssh_password):
        assert(self.is_locked)
        host = Host(
                id,
                is_TCS,
                TCS_type,
                provider,
                provider_id,
                ip_address,
                ssh_port,
                ssh_username,
                ssh_password,
                ssh_host_key,
                stats_ssh_username,
                stats_ssh_password)

        assert(host.id not in self.__hosts)
        self.__hosts[host.id] = host

    # obsolete
    def import_server(self, server_id, host_id, ip_address, egress_ip_address, internal_ip_address,
                      propagation_channel_id, is_embedded, is_permanent, discovery_date_range, capabilities, web_server_port,
                      web_server_secret, web_server_certificate, web_server_private_key, ssh_port, ssh_username,
                      ssh_password, ssh_host_key):
        assert(self.is_locked)
        server = Server(
                    server_id,
                    host_id,
                    ip_address,
                    egress_ip_address,
                    internal_ip_address,
                    propagation_channel_id,
                    is_embedded,
                    is_permanent,
                    discovery_date_range,
                    capabilities,
                    web_server_port,
                    web_server_secret,
                    web_server_certificate,
                    web_server_private_key,
                    ssh_port,
                    ssh_username,
                    ssh_password,
                    ssh_host_key,
                    None)

        assert(server.id not in self.__servers)
        self.__servers[server.id] = server

    def __disable_server(self, server):
        assert(self.is_locked)
        # Prevent users from establishing new connections to this server,
        # while allowing existing connections to be maintained.
        server.capabilities['handshake'] = False
        server.capabilities['SSH'] = False
        server.capabilities['OSSH'] = False
        server.capabilities['FRONTED-MEEK'] = False
        server.capabilities['UNFRONTED-MEEK'] = False
        server.capabilities['UNFRONTED-MEEK-SESSION-TICKET'] = False
        host = self.__hosts[server.host_id]
        servers = [s for s in self.__servers.itervalues() if s.host_id == server.host_id]
        if host.is_TCS:
            psi_ops_install.install_TCS_psi_limit_load(host, disable_permanently=True)
        else:
            psi_ops_install.install_firewall_rules(host, servers, None, self.__ssh_ip_address_whitelist, None, plugins, False) # No need to update the malware blacklist
        # NOTE: caller is responsible for saving now
        #self.save()

    def __count_users_on_host(self, host_id):
        host = self.__hosts[host_id]
        if host.is_TCS:
            return int(self.run_command_on_host(host,
                'tac /var/log/psiphond/psiphond.log | grep -m1 \\"establish_tunnels\\": | python -c \'import sys, json; print json.loads(sys.stdin.read())["ALL"]["established_clients"]\''))
        else:
            vpn_users = int(self.run_command_on_host(host,
                                                 'ifconfig | grep ppp | wc -l'))
            ssh_users = int(self.run_command_on_host(host,
                                                 'ps ax | grep ssh | grep psiphon | wc -l')) / 2
            return vpn_users + ssh_users

    def __check_host_is_accepting_tunnels(self, host_id):
        host = self.__hosts[host_id]
        if host.is_TCS:
            return 'True' == self.run_command_on_host(host,
                'tac /var/log/psiphond/psiphond.log | grep -m1 \\"establish_tunnels\\": | python -c \'import sys, json; print json.loads(sys.stdin.read())["establish_tunnels"]\'').strip()
        else:
            raise Exception("not implemented")

    def __upgrade_host_datacenter_names(self):
        #TODO: need to upgrade this function to use new APIv4
        if self.__linode_account.api_key:
            linode_datacenter_names = psi_linode.get_datacenter_names(self.__linode_account)
            for host in self.__hosts.itervalues():
                if host.provider.lower() == 'linode':
                    host.datacenter_name = str(linode_datacenter_names[host.provider_id])
                else:
                    host.datacenter_name = str(host.provider)

    def __prune_servers(self, servers):
        number_removed = 0
        number_disabled = 0
        for server in servers:
            users_on_host = self.__count_users_on_host(server.host_id)
            if users_on_host <= 15:
                self.remove_host(server.host_id)
                number_removed += 1
            elif users_on_host < 50:
                self.__disable_server(server)
                number_disabled += 1
        return number_removed, number_disabled

    def prune_propagation_channel_servers(self, propagation_channel_name,
                                          max_osl_discovery_server_age_in_days=None,
                                          max_discovery_server_age_in_days=None,
                                          max_propagation_server_age_in_days=None):
        assert(self.is_locked)

        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        now = datetime.datetime.now()
        today = datetime.datetime(now.year, now.month, now.day)

        # Remove old servers with low activity
        number_removed = 0
        number_disabled = 0

        if max_osl_discovery_server_age_in_days == None:
            max_osl_discovery_server_age_in_days = propagation_channel.max_osl_discovery_server_age_in_days
        if max_osl_discovery_server_age_in_days > 0:
            old_osl_discovery_servers = [server for server in self.__servers.itervalues()
                if server.propagation_channel_id == propagation_channel.id
                and server.osl_discovery_date_range
                and server.osl_discovery_date_range[1] < (today - datetime.timedelta(days=max_osl_discovery_server_age_in_days))
                and self.__hosts[server.host_id].provider in ['linode', 'digitalocean', 'vpsnet']]
            removed, disabled = self.__prune_servers(old_osl_discovery_servers)
            number_removed += removed
            number_disabled += disabled

        if max_discovery_server_age_in_days == None:
            max_discovery_server_age_in_days = propagation_channel.max_discovery_server_age_in_days
        if max_discovery_server_age_in_days > 0:
            old_discovery_servers = [server for server in self.__servers.itervalues()
                if server.propagation_channel_id == propagation_channel.id
                and server.discovery_date_range
                and server.discovery_date_range[1] < (today - datetime.timedelta(days=max_discovery_server_age_in_days))
                and self.__hosts[server.host_id].provider in ['linode', 'digitalocean', 'vpsnet']]
            removed, disabled = self.__prune_servers(old_discovery_servers)
            number_removed += removed
            number_disabled += disabled

        if max_propagation_server_age_in_days == None:
            max_propagation_server_age_in_days = propagation_channel.max_propagation_server_age_in_days
        if max_propagation_server_age_in_days > 0:
            old_propagation_servers = [server for server in self.__servers.itervalues()
                if server.propagation_channel_id == propagation_channel.id
                and not server.discovery_date_range
                and not server.is_embedded
                and server.logs[0][0] < (today - datetime.timedelta(days=max_propagation_server_age_in_days))
                and self.__hosts[server.host_id].provider in ['linode', 'digitalocean', 'vpsnet']]
            removed, disabled = self.__prune_servers(old_propagation_servers)
            number_removed += removed
            number_disabled += disabled

        # This deploy will update the stats server, so it doesn't try to pull stats from
        # hosts that no longer exist
        # NOTE: This will also call save() only if a host has been removed and
        # __deploy_stats_config_required is set. If hosts have only been disabled, a save()
        # might not occur.
        # NEW: caller is responsible for deploy(), to reduce the number of save()'s when
        # this is called in a loop.
        #self.deploy()

        if number_removed > 0 or number_disabled > 0:
            self.save()

        return number_removed, number_disabled

    def replace_propagation_channel_servers(self, propagation_channel_name,
                                            new_osl_discovery_servers_count=None,
                                            new_discovery_servers_count=None,
                                            new_propagation_servers_count=None):
        assert(self.is_locked)

        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        now = datetime.datetime.now()
        today = datetime.datetime(now.year, now.month, now.day)
        tomorrow = today + datetime.timedelta(days=1)

        # Use a default 1 day discovery date range.
        new_discovery_date_range = (tomorrow, tomorrow + datetime.timedelta(days=1))
        # Use a default 15 day osl discovery date range.
        new_osl_discovery_date_range = (today, today + datetime.timedelta(days=15))

        if new_osl_discovery_servers_count == None:
            new_osl_discovery_servers_count = propagation_channel.new_osl_discovery_servers_count
        if new_discovery_servers_count == None:
            new_discovery_servers_count = propagation_channel.new_discovery_servers_count
        if new_propagation_servers_count == None:
            new_propagation_servers_count = propagation_channel.new_propagation_servers_count

        def _launch_new_server(_):
            try:
                is_TCS = True
                return self.launch_new_server(is_TCS)
            except:
                return None

        pool = ThreadPool(20)
        new_servers = pool.map(_launch_new_server, [None for _ in range(new_osl_discovery_servers_count + new_discovery_servers_count + new_propagation_servers_count)])

        failure = None

        if new_osl_discovery_servers_count > 0:
            try:
                self.add_servers(new_servers[:new_osl_discovery_servers_count], propagation_channel_name, new_osl_discovery_date_range, None, False)
            except Exception as ex:
                for line in traceback.format_exc().split('\n'):
                    print line
                failure = ex

        if new_discovery_servers_count > 0:
            try:
                self.add_servers(new_servers[new_osl_discovery_servers_count:new_osl_discovery_servers_count + new_discovery_servers_count], propagation_channel_name, None, new_discovery_date_range, False)
            except Exception as ex:
                for line in traceback.format_exc().split('\n'):
                    print line
                failure = ex

        if new_propagation_servers_count > 0:
            try:
                self.add_servers(new_servers[new_osl_discovery_servers_count + new_discovery_servers_count:], propagation_channel_name, None, None)
            except Exception as ex:
                for line in traceback.format_exc().split('\n'):
                    print line
                failure = ex

        if failure:
            raise failure

    def get_existing_server_ids(self):
        return [server.id for server in self.__servers.itervalues()] + \
               [deleted_server.id for deleted_server in self.__deleted_servers.itervalues()]

    def add_server_to_host(self, host, new_servers):

        existing_servers = [server for server in self.get_servers() if server.host_id == host.id]
        servers_on_host = existing_servers + new_servers

        psi_ops_install.install_host(host, servers_on_host, self.get_existing_server_ids(), self.__TCS_psiphond_config_values, self.__ssh_ip_address_whitelist, self.__TCS_iptables_output_rules, plugins)
        host.log('install with new servers')

        assert(host.id in self.__hosts)

        for server in new_servers:
            assert(server.id not in self.__servers)
            self.__servers[server.id] = server
            # If the Host is TCS, the Server should have this capability
            if host.is_TCS:
                server.capabilities['ssh-api-requests'] = True

        psi_ops_deploy.deploy_data(
                            host,
                            self.__compartmentalize_data_for_host(host.id, host.is_TCS),
                            self.__TCS_traffic_rules_set,
                            self.__TCS_OSL_config,
                            self.__TCS_tactics_config_template,
                            self.__TCS_blocklist_csv)

        for server in servers_on_host:
            self.test_server(server.id, ['handshake'])

    def setup_fronting_for_server(self, server_id, fronting_provider_alias, meek_server_fronting_domain, meek_server_fronting_host):
        server = self.__servers[server_id]
        host = self.__hosts[server.host_id]
        assert(host.meek_server_port == None)

        host.fronting_provider_id = self.__fronting_provider_id_aliases[fronting_provider_alias]

        server.capabilities['FRONTED-MEEK'] = True
        host.meek_server_fronting_domain = meek_server_fronting_domain
        host.meek_server_fronting_host = meek_server_fronting_host
        self.setup_meek_parameters_for_host(host, 443)

        server.capabilities['FRONTED-MEEK-TACTICS'] = True
        if not host.tactics_request_public_key or not host.tactics_request_private_key:
            public_key, private_key = self.generate_nacl_keypair()
            host.tactics_request_public_key = public_key
            host.tactics_request_private_key = private_key
        if not host.tactics_request_obfuscated_key:
            host.tactics_request_obfuscated_key = self.generate_obfuscated_key(base64_encode=True)

        self.install_meek_for_host(host)

    def setup_unfronted_meek_for_server(self, server_id):
        server = self.__servers[server_id]
        host = self.__hosts[server.host_id]
        assert(host.meek_server_port == None)

        server.capabilities['handshake'] = False
        server.capabilities['VPN'] = False
        server.capabilities['SSH'] = False
        server.capabilities['OSSH'] = False
        server.capabilities['FRONTED-MEEK'] = False
        server.capabilities['UNFRONTED-MEEK'] = True
        self.setup_meek_parameters_for_host(host, 80)
        self.install_meek_for_host(host)

    def setup_unfronted_meek_session_ticket_for_server(self, server_id):
        server = self.__servers[server_id]
        host = self.__hosts[server.host_id]
        assert(host.meek_server_port == None)
        assert(host.is_TCS)

        server.capabilities['handshake'] = False
        server.capabilities['VPN'] = False
        server.capabilities['SSH'] = False
        server.capabilities['OSSH'] = False
        server.capabilities['FRONTED-MEEK'] = False
        server.capabilities['UNFRONTED-MEEK'] = False
        server.capabilities['UNFRONTED-MEEK-SESSION-TICKET'] = True
        self.setup_meek_parameters_for_host(host, 443)
        self.install_meek_for_host(host)

    def generate_obfuscated_key(self, base64_encode=False):
        obfuscated_key = os.urandom(psi_ops_install.SSH_OBFUSCATED_KEY_BYTE_LENGTH)
        return base64.b64encode(obfuscated_key) if base64_encode else binascii.hexlify(obfuscated_key)

    def generate_nacl_keypair(self):
        keygenerator_binary = 'keygenerator.exe'
        if os.name == 'posix':
            keygenerator_binary = 'keygenerator'
        keypair = json.loads(subprocess.Popen([os.path.join('.', keygenerator_binary)], stdout=subprocess.PIPE).communicate()[0])
        return keypair['publicKey'], keypair['privateKey']

    def setup_meek_parameters_for_host(self, host, meek_server_port):
        assert(host.meek_server_port == None)
        host.meek_server_port = meek_server_port
        if not host.meek_server_obfuscated_key:
            host.meek_server_obfuscated_key = self.generate_obfuscated_key()
        if not host.meek_cookie_encryption_public_key or not host.meek_cookie_encryption_private_key:
            public_key, private_key = self.generate_nacl_keypair()
            host.meek_cookie_encryption_public_key = public_key
            host.meek_cookie_encryption_private_key = private_key

    def install_meek_for_host(self, host):
        servers = [s for s in self.__servers.itervalues() if s.host_id == host.id]
        psi_ops_install.install_firewall_rules(host, servers, self.__TCS_psiphond_config_values, self.__ssh_ip_address_whitelist, self.__TCS_iptables_output_rules, plugins, False) # No need to update the malware blacklist
        psi_ops_install.install_psi_limit_load(host, servers)
        psi_ops_deploy.deploy_implementation(
                            host,
                            servers,
                            self.__get_own_encoded_server_entries_for_host(host.id),
                            self.__discovery_strategy_value_hmac_key,
                            plugins,
                            self.__TCS_psiphond_config_values)
        psi_ops_deploy.deploy_data(
                            host,
                            self.__compartmentalize_data_for_host(host.id, host.is_TCS),
                            self.__TCS_traffic_rules_set,
                            self.__TCS_OSL_config,
                            self.__TCS_tactics_config_template,
                            self.__TCS_blocklist_csv)

    def setup_server(self, host, servers):
        # Install Psiphon 3 and generate configuration values
        # Here, we're assuming one server/IP address per host
        psi_ops_install.install_host(host, servers, self.get_existing_server_ids(), self.__TCS_psiphond_config_values, self.__ssh_ip_address_whitelist, self.__TCS_iptables_output_rules, plugins)
        host.log('install')
        psi_ops_install.change_weekly_crontab_runday(host, None)
        # Update database

        # Add new server (we also add a host; here, the host and server are
        # one-to-one, but legacy networks have many servers per host and we
        # retain support for this in the data model and general functionality)
        # Note: this must be done before deploy_data otherwise the deployed
        # data will not include this host and server
        assert(host.id not in self.__hosts)
        self.__hosts[host.id] = host

        for server in servers:
            assert(server.id not in self.__servers)
            self.__servers[server.id] = server
            # If the Host is TCS, the Server should have this capability
            if host.is_TCS:
                server.capabilities['ssh-api-requests'] = True

        # Deploy will upload web server source database data and client builds
        # (Only deploying for the new host, not broadcasting info yet...)
        psi_ops_deploy.deploy_implementation(
                            host,
                            servers,
                            self.__get_own_encoded_server_entries_for_host(host.id),
                            self.__discovery_strategy_value_hmac_key,
                            plugins,
                            self.__TCS_psiphond_config_values)
        psi_ops_deploy.deploy_geoip_database_autoupdates(host)
        psi_ops_deploy.deploy_data(
                            host,
                            self.__compartmentalize_data_for_host(host.id, host.is_TCS),
                            self.__TCS_traffic_rules_set,
                            self.__TCS_OSL_config,
                            self.__TCS_tactics_config_template,
                            self.__TCS_blocklist_csv)
        psi_ops_deploy.deploy_routes(host)
        host.log('initial deployment')

        for server in servers:
            self.test_server(server.id, ['handshake'])

    def launch_new_server(self, is_TCS, provider=None, multi_ip=True):
        if provider == None:
            provider = self._weighted_random_choice(self.__provider_ranks).provider

        # This is pretty dirty. We should use some proper OO technique.
        provider_launch_new_server = None
        provider_account = None
        if provider.lower() == 'linode':
            provider_launch_new_server = psi_linode.launch_new_server
            provider_account = self.__linode_account
        elif provider.lower() == 'digitalocean':
            provider_launch_new_server = psi_digitalocean.launch_new_server
            provider_account = self.__digitalocean_account
        elif provider.lower() == 'vpsnet':
            provider_launch_new_server = psi_vpsnet.launch_new_server
            provider_account = self.__vpsnet_account
        elif provider.lower() == 'vps247':
            provider_launch_new_server = psi_vps247.launch_new_server
            provider_account = self.__vps247_account
        elif provider.lower() == 'elastichosts':
            provider_launch_new_server = psi_elastichosts.ElasticHosts().launch_new_server
            provider_account = self._weighted_random_choice(self.__elastichosts_accounts)
        else:
            raise ValueError('bad provider value: %s' % provider)

        print 'starting %s process (up to 20 minutes)...' % provider

        # Create a new cloud VPS
        def provider_launch_new_server_with_retries(is_TCS):
            for _ in range(3):
                try:
                    return provider_launch_new_server(provider_account, is_TCS, plugins, multi_ip)
                except Exception as ex:
                    print str(ex)
            raise ex

        server_info = provider_launch_new_server_with_retries(is_TCS)
        return server_info[0:3] + (provider.lower(),) + server_info[4:]

    def add_servers(self, server_infos, propagation_channel_name, osl_discovery_date_range, discovery_date_range, replace_others=True, server_capabilities=None):
        assert(self.is_locked)

        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)

        # Embedded servers (aka "propagation servers") are embedded in client
        # builds, where as discovery servers are only revealed when clients
        # connect to a server.
        is_embedded_server = (osl_discovery_date_range is None and discovery_date_range is None)

        # The following changes will be saved if at least one server is successfully added

        if replace_others:
            # If we are creating new propagation servers, stop embedding the old ones
            # (they are still active, but not embedded in builds or discovered)
            # NEW: don't replace servers marked with is_permanent
            if is_embedded_server:
                for old_server in self.__servers.itervalues():
                    if (old_server.propagation_channel_id == propagation_channel.id and
                        old_server.is_embedded and
                        not old_server.is_permanent):
                        old_server.is_embedded = False
                        old_server.log('unembedded')
            # If we are creating new discovery servers, stop discovering existing ones
            elif discovery_date_range:
                self.__replace_propagation_channel_discovery_servers(propagation_channel.id)
            else:
                raise Exception("not implemented")

        osl_ids = None
        if osl_discovery_date_range:
            osl_propagation_channel_ids, osl_ids = self.get_current_propagation_channel_and_osl_ids_for_scheme(0)
            for channel_id in osl_propagation_channel_ids:
                self.__deploy_pave_osls_required_for_propagation_channels.add(channel_id)

        if discovery_date_range:
            self.__deploy_data_required_for_all = True

        self.__deploy_stats_config_required = True

        # Unless the node is reserved for discovery, release it through
        # the campaigns associated with the propagation channel
        # TODO: recover from partially complete state...
        if is_embedded_server:
            for sponsor in self.__sponsors.itervalues():
                for campaign in sponsor.campaigns:
                    if campaign.propagation_channel_id == propagation_channel.id:
                        for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                            self.__deploy_builds_required_for_campaigns[platform].add(
                                    (campaign.propagation_channel_id, sponsor.id))
                        # Don't log this, too much noise
                        #campaign.log('marked for build and publish (new embedded server)')

        new_server_error = ''
        for new_server_number in range(len(server_infos)):
            server_info = server_infos[new_server_number]
            if type(server_info) != tuple:
                continue
            host = Host(*server_info[:-1])

            if not host.region:
                new_server_error = "Empty host region"
                continue

            # NOTE: jsonpickle will serialize references to discovery_date_range, which can't be
            # resolved when unpickling, if discovery_date_range is used directly.
            # So create a copy instead.
            discovery = self.__copy_date_range(discovery_date_range) if discovery_date_range else None
            osl_discovery = self.__copy_date_range(osl_discovery_date_range) if osl_discovery_date_range else None

            ssh_port = '22'
            assert(self.__standard_ossh_ports)
            ossh_port = random.choice(list(self.__standard_ossh_ports))
            capabilities = ServerCapabilities()

            if server_capabilities:
                capabilities = copy_server_capabilities(server_capabilities)
            elif discovery or osl_discovery:
                # Discovery servers will either be OSSH-only or UNFRONTED-MEEK-only
                capabilities['handshake'] = False
                capabilities['VPN'] = False
                if random.random() < 0.5:
                    capabilities['SSH'] = False
                if random.random() < 0.5:
                    capabilities['OSSH'] = False
                    capabilities['UNFRONTED-MEEK'] = True
            elif new_server_number % 2 == 1:
                # We would like every other new propagation server created to be somewhat obfuscated
                capabilities['handshake'] = False
                capabilities['VPN'] = False
                capabilities['SSH'] = False
                ossh_ports = range(1,1023)
                ossh_ports.remove(15)
                ossh_ports.remove(25)
                ossh_ports.remove(80)
                ossh_ports.remove(135)
                ossh_ports.remove(136)
                ossh_ports.remove(137)
                ossh_ports.remove(138)
                ossh_ports.remove(139)
                ossh_ports.remove(515)
                ossh_ports.remove(593)
                ossh_port = random.choice(ossh_ports)
            else:
                # Regular propagation servers also have UNFRONTED-MEEK
                capabilities['UNFRONTED-MEEK'] = True

            if capabilities['UNFRONTED-MEEK']:
                random_number = random.random()
                if random_number < 0.33:
                    self.setup_meek_parameters_for_host(host, 80)
                elif random_number < 0.66:
                    ossh_port = random.choice([53, 554])
                    self.setup_meek_parameters_for_host(host, 443)
                else:
                    ossh_port = random.choice([53, 554])
                    assert(host.is_TCS)
                    capabilities['UNFRONTED-MEEK'] = False
                    capabilities['UNFRONTED-MEEK-SESSION-TICKET'] = True
                    self.setup_meek_parameters_for_host(host, 443)

            # All and only TCS servers support SSH API requests
            capabilities['ssh-api-requests'] = host.is_TCS

            # TCS servers do not support VPN
            if host.is_TCS:
                capabilities['handshake'] = False
                capabilities['VPN'] = False

            quic_port = ossh_port
            if quic_port in [68, 123] or random.random() < 0.1:
                quic_port = ssh_port

            if host.is_TCS:
                capabilities['QUIC'] = capabilities['OSSH']

            server = Server(
                        None,
                        host.id,
                        host.ip_address,
                        server_info[-1] if server_info[-1] else host.ip_address,
                        host.ip_address,
                        propagation_channel.id,
                        is_embedded_server,
                        False,
                        discovery,
                        capabilities,
                        str(random.randrange(8000, 9000)),
                        None,
                        None,
                        None,
                        ssh_port,
                        None,
                        None,
                        None,
                        None,
                        ossh_port,
                        quic_port,
                        None,
                        None,
                        None,
                        None,
                        None,
                        INITIAL_SERVER_CONFIGURATION_VERSION)

            server.osl_ids = list(osl_ids) if osl_ids else None
            server.osl_discovery_date_range = osl_discovery

            supports_passthrough = psi_ops_deploy.server_supports_passthrough(server, host)
            if supports_passthrough and len(self.__passthrough_addresses) > 0:
                host.passthrough_address = random.choice(self.__passthrough_addresses)

            self.setup_server(host, [server])

            self.run_command_on_host(host, 'shutdown -r')

            self.save()

        if new_server_error:
            raise Exception(new_server_error)

        # The save() above ensures new server configuration is saved to CMS before deploying new
        # server info to the network

        # This deploy will broadcast server info, propagate builds, and update
        # the stats and email server
        # NEW: deploy() is called by another process
        #self.deploy()

    def remove_hosts_from_providers(self):
        assert(self.is_locked)

        params_list = []
        need_to_save = False
        for host in self.__hosts_to_remove_from_providers.copy():
            # Only hosts that can be removed via an API are removed here.
            # Others must be manually removed.
            provider_remove_host = None
            if host.provider == 'linode':
                provider_remove_host = psi_linode.remove_server
                provider_account = self.__linode_account
            if host.provider == 'digitalocean':
                provider_remove_host = psi_digitalocean.remove_server
                provider_account = self.__digitalocean_account
            if host.provider == 'vpsnet':
                provider_remove_host = psi_vpsnet.remove_server
                provider_account = self.__vpsnet_account
            if provider_remove_host:
                params_list.append((provider_remove_host, provider_account, host))
                self.__hosts_to_remove_from_providers.remove(host)
                need_to_save = True
                # It is safe to call provider_remove_host() for a host that has
                # already been removed, so there is no need to save() yet.

        def remove_host_from_provider(params):
            provider_remove_host = params[0]
            provider_account = params[1]
            host = params[2]
            try:
                # Remove the actual host through the provider's API
                provider_remove_host(provider_account, host.provider_id)
            except Exception as ex:
                print str(ex)
                return ex

        pool = ThreadPool(30)
        results = pool.map(remove_host_from_provider, params_list)
        for result in results:
            if result:
                raise result

        if need_to_save:
            self.save()

    def remove_host(self, host_id):
        assert(self.is_locked)
        host = self.__hosts[host_id]
        host_copy = Host(
                        host.id,
                        host.is_TCS,
                        host.TCS_type,
                        host.provider,
                        host.provider_id,
                        host.ip_address,
                        host.ssh_port,
                        host.ssh_username,
                        host.ssh_password,
                        host.ssh_host_key,
                        host.stats_ssh_username,
                        host.stats_ssh_password,
                        host.datacenter_name,
                        host.region,
                        host.fronting_provider_id,
                        host.passthrough_address,
                        host.meek_server_port,
                        host.meek_server_obfuscated_key,
                        host.meek_server_fronting_domain,
                        host.meek_server_fronting_host,
                        host.alternate_meek_server_fronting_hosts,
                        host.meek_cookie_encryption_public_key,
                        host.meek_cookie_encryption_private_key)
        self.__hosts_to_remove_from_providers.add(host_copy)

        # Mark host and its servers as deleted in the database. We keep the
        # records around for historical info and to ensure we never recycle
        # server IDs
        server_ids_on_host = []
        for server in self.__servers.itervalues():
            if server.host_id == host.id:
                server_ids_on_host.append(server.id)
        for server_id in server_ids_on_host:
            assert(server_id not in self.__deleted_servers)
            deleted_server = self.__servers.pop(server_id)
            # Clear some unneeded data that might be contributing to a MemoryError
            deleted_server.web_server_certificate = None
            deleted_server.web_server_secret = None
            deleted_server.web_server_private_key = None
            deleted_server.ssh_password = None
            deleted_server.ssh_host_key = None
            deleted_server.ssh_obfuscated_key = None
            deleted_server.TCS_ssh_private_key = None
            # Add deleted log to deleted server
            deleted_server.log("deleted")
            self.__deleted_servers[server_id] = deleted_server
        # We don't assign host IDs and can't guarentee uniqueness, so not
        # archiving deleted host keyed by ID.
        deleted_host = self.__hosts.pop(host.id)
        # Don't archive "deploy" logs.  They are noisy, and may contribute to
        # a MemoryError we have observed when serializing the PsiphonNetwork object
        for log in copy.copy(deleted_host.logs):
            if 'deploy' in log[1]:
                deleted_host.logs.remove(log)
        # Add deleted log to deleted host
        deleted_host.log("deleted")
        self.__deleted_hosts.append(deleted_host)

        # Clear flags that include this host id.  Update stats config.
        if host.id in self.__deploy_implementation_required_for_hosts:
            self.__deploy_implementation_required_for_hosts.remove(host.id)
        self.__deploy_stats_config_required = True
        # NOTE: If host was currently discoverable or will be in the future,
        #       host data should be updated.
        # NOTE: If host was currently embedded, new campaign builds are needed.

        # NOTE: caller is responsible for saving now
        #self.save()

    def backup_and_restore_for_migrate(self, action, host):
        if type(host) == str:
            host = self.__hosts[host]

        if action == 'backup':
            ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)
            ssh.exec_command('tar czvf /root/etc.tar.gz /etc/*')
            ssh.get_file('/root/etc.tar.gz', './Migration/' + host.ip_address + '-etc.tar.gz')
        elif action == 'restore':
            if host.provider == 'digitalocean':
                ssh = psi_ssh.SSH(
                        host.ip_address, host.ssh_port,
                        host.ssh_username, None, None,
                        self.__digitalocean_account.base_rsa_private_key)
                ssh.exec_command('echo "root:%s" | chpasswd' % (host.ssh_password))
            elif host.provider == 'linode':
                ssh = psi_ssh.SSH(
                        host.ip_address, host.ssh_port,
                        host.ssh_username, host.ssh_password,
                        self.__linode_account.tcs_base_host_public_key)
            import shlex
            subprocess.Popen(shlex.split('mkdir ./Migration/' + host.ip_address))
            subprocess.Popen(shlex.split('tar xzvf ./Migration/' + host.ip_address + '-etc.tar.gz -C ./Migration/' + host.ip_address))

            for dirpath, dirnames, filenames in os.walk('./Migration/' + host.ip_address + '/etc/ssh/'):
                remote_path = '/etc/ssh/'
                # make remote directory ...
                for filename in filenames:
                    local_path = os.path.join(dirpath, filename)
                    remote_fliepath = os.path.join(remote_path, filename)
                    # put file
                    ssh.put_file(local_path, remote_fliepath)
            ssh.exec_command('sed -i -e "/^PasswordAuthentication no/s/^.*$/PasswordAuthentication yes/" /etc/ssh/sshd_config')
            ssh.exec_command('sed -i -e "/PasswordAuthentication yes/s/^#//" /etc/ssh/sshd_config')
            ssh.exec_command('service ssh restart')
        else:
            print('Action is not supported, please use "backup" or "restore"')
            return

    # Migrating Legacy host to TCS host
    def migrate_to_TCS_entry(self, host, TCS_type):
        if type(host) == str:
            host = self.__hosts[host]

        server = self.get_server_by_ip_address(host.ip_address)

        server.web_server_certificate = re.sub("(.{64})", "\\1\n", server.web_server_certificate, 0, re.DOTALL)
        server.web_server_private_key = re.sub("(.{64})", "\\1\n", server.web_server_private_key, 0, re.DOTALL)

        server.capabilities['ssh-api-requests'] = True
        server.capabilities['VPN'] = False
        server.capabilities['handshake'] = False

        server.web_server_certificate = '-----BEGIN CERTIFICATE-----\n' + server.web_server_certificate + '\n-----END CERTIFICATE-----\n'
        server.web_server_private_key = '-----BEGIN RSA PRIVATE KEY-----\n' + server.web_server_private_key + '\n-----END RSA PRIVATE KEY-----\n'
        server.TCS_ssh_private_key = self.run_command_on_host(host, 'cat /etc/ssh/ssh_host_rsa_key.psiphon_ssh_%s' % (host.ip_address))

        if host.is_TCS == True:
            migrated_from = 'TCS Docker'
        else:
            migrated_from = 'Legacy'

        server.log('Migrated' + ' from ' + migrated_from + ' to TCS ' + TCS_type)

        host.is_TCS = True
        host.TCS_type = TCS_type

        return (host, server)

    # Change hostname and stats users information
    def migrate_hostname_and_users(self, host):
        if type(host) == str:
            host = self.__hosts[host]

        self.run_command_on_host(host, 'useradd -M -d /var/log -s /bin/sh -g adm %s' % (host.stats_ssh_username))
        self.run_command_on_host(host, 'echo "%s:%s" | chpasswd' % (host.stats_ssh_username, host.stats_ssh_password))
        self.run_command_on_host(host, 'hostnamectl set-hostname %s' % (host.id))

        self.run_command_on_host(host, 'service ssh restart')

    def reinstall_host(self, host_id):
        assert(self.is_locked)
        host = self.__hosts[host_id]
        servers = [server for server in self.__servers.itervalues() if server.host_id == host_id]
        psi_ops_install.install_host(host, servers, self.get_existing_server_ids(), self.__TCS_psiphond_config_values, self.__ssh_ip_address_whitelist, self.__TCS_iptables_output_rules, plugins)
        psi_ops_install.change_weekly_crontab_runday(host, None)
        psi_ops_deploy.deploy_implementation(
                            host,
                            servers,
                            self.__get_own_encoded_server_entries_for_host(host.id),
                            self.__discovery_strategy_value_hmac_key,
                            plugins,
                            self.__TCS_psiphond_config_values)
        psi_ops_deploy.deploy_geoip_database_autoupdates(host)
        # New data might have been generated
        # NOTE that if the client version has been incremented but a full deploy has not yet been run,
        # this following psi_ops_deploy.deploy_data call is not safe.  Data will specify a new version
        # that is not yet available on servers (infinite download loop).
        psi_ops_deploy.deploy_data(
                            host,
                            self.__compartmentalize_data_for_host(host.id, host.is_TCS),
                            self.__TCS_traffic_rules_set,
                            self.__TCS_OSL_config,
                            self.__TCS_tactics_config_template,
                            self.__TCS_blocklist_csv)

        host.log('reinstall')

    def reinstall_hosts(self):
        assert(self.is_locked)
        psi_ops_deploy.run_in_parallel(25, self.reinstall_host, [host.id for host in self.__hosts.itervalues()])

    def set_servers_propagation_channel_and_discovery_date_range(self, server_names, propagation_channel_name, discovery_date_range, replace_others=True):
        assert(self.is_locked)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)

        if replace_others:
            self.__replace_propagation_channel_discovery_servers(propagation_channel.id)

        for server_name in server_names:
            server = self.__servers[server_name]
            server.propagation_channel_id = propagation_channel.id
            server.discovery_date_range = self.__copy_date_range(discovery_date_range)
            server.log('propagation channel set to %s' % (propagation_channel.id,))
            server.log('discovery_date_range set to %s - %s' % (server.discovery_date_range[0].isoformat(),
                                                                server.discovery_date_range[1].isoformat()))

        self.__deploy_data_required_for_all = True

    def list_orphans(self, provider):
        provider_controller = globals()["psi_{}".format(provider)]
        provider_account = vars(self)["_PsiphonNetwork__{}_account".format(provider)]
        
        running_machines = provider_controller.get_servers(provider_account) # This method returns a list of provider id
        existing_hosts = [str(host.provider_id) for host in self.get_hosts() if host.provider == provider]
        to_be_removed_hosts = [str(host.provider_id) for host in self._PsiphonNetwork__hosts_to_remove_from_providers if host.provider == provider]
        
        orphans = [o for o in running_machines if o[0] not in existing_hosts + to_be_removed_hosts]
        
        return orphans

    def find_orphans(self):
        for provider in ['linode', 'digitalocean', 'vpsnet']:
            orphans = self.list_orphans(provider)
            sys.stderr.write(provider + ' orphans:\n' + str(orphans) + '\n\n')

    def delete_orphans(self, provider, hosts_provider_id_list):
        pending_deletion = []
        provider_controller = globals()["psi_{}".format(provider)]
        provider_account = vars(self)["_PsiphonNetwork__{}_account".format(provider)]

        for host_provider_id, host_name in hosts_provider_id_list:
            # TODO: safety check to avoid delete production servers
            orphan = provider_controller.get_server(provider_account, host_provider_id)
            print textwrap.dedent('''
                  Provider ID:             %s
                  Host Name/Labe:          %s
                  Status:                  %s
                  Created At:              %s
                  IP Address:              %s
                  Region:                  %s
                  Tags:                    %s
                  ''') % (
                                str(orphan.id),
                                orphan.name if provider=='digitalocean' or provider=='vpsnet' else orphan.label,
                                orphan.state if provider=='vpsnet' else orphan.status,
                                orphan.created_at if provider=='digitalocean' else orphan.public_ips[0]['ip_address']['created_at'] if provider=='vpsnet' else orphan.created.strftime('%Y-%m-%dT%H:%M:%S'),
                                orphan.networks['v4'][0]['ip_address'] if provider=='digitalocean' else orphan.public_ips[0]['ip_address']['ip_address'] if provider=='vpsnet' else orphan.ipv4[0],
                                orphan.region['slug'] if provider=='digitalocean' else orphan.region.id if provider=='linode' else 'No Region infomation',
                                str(orphan.tags) if provider!='vpsnet' else 'VPS.net node has no tags'
                                  )
            user_response = raw_input("Do you want to delete this orphan host? ")
            if user_response in ['yes', 'y', 'Y', 'Yes']:
                print('Adding host to deletion list - the host: {}'.format(host_name))
                pending_deletion.append(orphan.id)
                #provider_controller.remove_server(provider_account, host_provider_id) # method delete server through API
            else:
                print("Do Nothing")

        user_confirm = raw_input('Start deleting following orphan hosts: \n{}\nDo you want to process? '.format(pending_deletion))
        if user_confirm in ['yes', 'y', 'Y', 'Yes']:
            for i in pending_deletion:
                print("Deleting: {}".format(i))
                provider_controller.remove_server(provider_account, i) # method delete server through API
        else:
            print("Abort the delete orphans job.")


    def __copy_date_range(self, date_range):
        return (datetime.datetime(date_range[0].year,
                                  date_range[0].month,
                                  date_range[0].day,
                                  date_range[0].hour,
                                  date_range[0].minute),
                datetime.datetime(date_range[1].year,
                                  date_range[1].month,
                                  date_range[1].day,
                                  date_range[1].hour,
                                  date_range[1].minute))

    def __replace_propagation_channel_discovery_servers(self, propagation_channel_id):
        assert(self.is_locked)
        now = datetime.datetime.now()
        for old_server in self.__servers.itervalues():
            # NOTE: don't instantiate today outside of this loop, otherwise jsonpickle will
            # serialize references to it (for all but the first server in this loop) which
            # are not unpickle-able
            today = datetime.datetime(now.year, now.month, now.day)
            if (old_server.propagation_channel_id == propagation_channel_id and
                old_server.discovery_date_range and
                (old_server.discovery_date_range[0] <= today < old_server.discovery_date_range[1])):
                old_server.discovery_date_range = (old_server.discovery_date_range[0], today)
                old_server.log('replaced')

    def _weighted_random_choice(self, choices):
        '''
        Assumes that each choice has a "rank" attribute, and that the rank is an integer.
        Returns the chosen members of the choices iterable.
        '''
        if not choices:
            raise ValueError('choices must not be empty')

        rank_total = sum([choice.rank for choice in choices])
        rand = random.randrange(rank_total)
        rank_accum = 0
        for choice in choices:
            rank_accum += choice.rank
            if rank_accum > rand:
                break
        return choice

    def __get_remote_server_list_signing_key_pair(self):
        if not self.__remote_server_list_signing_key_pair:
            assert(self.is_locked)
            self.__remote_server_list_signing_key_pair = \
                RemoteServerSigningKeyPair(
                    psi_ops_crypto_tools.generate_key_pair(
                        REMOTE_SERVER_SIGNING_KEY_PAIR_PASSWORD))

        # This may be serialized/deserialized into a unicode string, but M2Crypto won't accept that.
        # The key pair should only contain ascii anyways, so encoding to ascii should be safe.
        self.__remote_server_list_signing_key_pair.pem_key_pair = \
            self.__remote_server_list_signing_key_pair.pem_key_pair.encode('ascii', 'ignore')
        return self.__remote_server_list_signing_key_pair

    def create_feedback_encryption_key_pair(self):
        '''
        Generate a feedback encryption key pair and wrapping password.
        Overwrites any existing values.
        '''

        assert(self.is_locked)

        if self.__feedback_encryption_key_pair:
            print('WARNING: You are overwriting the previous value')

        password = psi_utils.generate_password()

        self.__feedback_encryption_key_pair = \
            FeedbackEncryptionKeyPair(
                psi_ops_crypto_tools.generate_key_pair(password),
                password)

    def get_feedback_encryption_key_pair(self):
        '''
        Retrieves the feedback encryption keypair and wrapping password.
        Generates those values if they don't already exist.
        '''

        if not self.__feedback_encryption_key_pair:
            self.create_feedback_encryption_key_pair()

        # This may be serialized/deserialized into a unicode string, but M2Crypto won't accept that.
        # The key pair should only contain ascii anyways, so encoding to ascii should be safe.
        self.__feedback_encryption_key_pair.pem_key_pair = \
            self.__feedback_encryption_key_pair.pem_key_pair.encode('ascii', 'ignore')
        return self.__feedback_encryption_key_pair

    def create_routes_signing_key_pair(self):
        '''
        Generate a routes signing key pair and wrapping password.
        Overwrites any existing values.
        '''

        assert(self.is_locked)

        if self.__routes_signing_key_pair:
            print('WARNING: You are overwriting the previous value')

        password = psi_utils.generate_password()

        self.__routes_signing_key_pair = \
            RoutesSigningKeyPair(
                psi_ops_crypto_tools.generate_key_pair(password),
                password)

    def get_routes_signing_key_pair(self):
        '''
        Retrieves the routes signing keypair and wrapping password.
        Generates those values if they don't already exist.
        '''

        if not self.__routes_signing_key_pair:
            self.create_routes_signing_key_pair()

        # This may be serialized/deserialized into a unicode string, but M2Crypto won't accept that.
        # The key pair should only contain ascii anyways, so encoding to ascii should be safe.
        self.__routes_signing_key_pair.pem_key_pair = \
            self.__routes_signing_key_pair.pem_key_pair.encode('ascii', 'ignore')
        return self.__routes_signing_key_pair

    def get_feedback_upload_info(self):
        assert(self.__feedback_upload_info)
        return self.__feedback_upload_info

    def set_feedback_upload_info(self, upload_server, upload_path, upload_server_headers):
        assert(self.is_locked)
        if not self.__feedback_upload_info:
            self.__feedback_upload_info = FeedbackUploadInfo(upload_server, upload_path, upload_server_headers)
            self.__feedback_upload_info.log('FeedbackUploadInfo set for first time to: "%s", "%s", "%s"' % (upload_server, upload_path, upload_server_headers))
        else:
            self.__feedback_upload_info.upload_server = upload_server
            self.__feedback_upload_info.upload_path = upload_path
            self.__feedback_upload_info.upload_server_headers = upload_server_headers
            self.__feedback_upload_info.log('FeedbackUploadInfo modified to: "%s", "%s", "%s"' % (upload_server, upload_path, upload_server_headers))

    def get_feedback_upload_urls(self):
        feedback_upload_info = self.get_feedback_upload_info()

        feedback_upload_urls = []
        feedback_upload_urls.append({'URL': base64.b64encode('https://' + feedback_upload_info.upload_server + feedback_upload_info.upload_path),
                                     'RequestHeaders': dict(header.split(':') for header in feedback_upload_info.upload_server_headers.splitlines()),
                                     'OnlyAfterAttempts': 0,
                                     'SkipVerify': False})

        number_of_alternate_feedback_upload_urls = 3
        if self.__alternate_feedback_upload_urls:
            if len(self.__alternate_feedback_upload_urls) > number_of_alternate_feedback_upload_urls:
                alternate_feedback_upload_urls = random.sample(self.__alternate_feedback_upload_urls, number_of_alternate_feedback_upload_urls)
            else:
                alternate_feedback_upload_urls = self.__alternate_feedback_upload_urls

            for url in alternate_feedback_upload_urls:
                feedback_upload_urls.append({'URL': base64.b64encode(url),
                                             'RequestHeaders': dict(header.split(':') for header in feedback_upload_info.upload_server_headers.splitlines()),
                                             'OnlyAfterAttempts': 2,
                                             'SkipVerify': True})

        return feedback_upload_urls

    def __get_upgrade_package_signing_key_pair(self):
        if not self.__upgrade_package_signing_key_pair:
            assert(self.is_locked)
            self.__upgrade_package_signing_key_pair = \
                UpgradePackageSigningKeyPair(
                    psi_ops_crypto_tools.generate_key_pair(
                        UPGRADE_PACKAGE_SIGNING_KEY_PAIR_PASSWORD))

        # This may be serialized/deserialized into a unicode string, but M2Crypto won't accept that.
        # The key pair should only contain ascii anyways, so encoding to ascii should be safe.
        self.__upgrade_package_signing_key_pair.pem_key_pair = \
            self.__upgrade_package_signing_key_pair.pem_key_pair.encode('ascii', 'ignore')
        return self.__upgrade_package_signing_key_pair

    def __split_tunnel_url_format(self):
        return 'https://s3.amazonaws.com/psiphon/routes/%s.route.zlib.json' # TODO get it from psi_ops_s3

    def __split_tunnel_signature_public_key(self):
        if self.__routes_signing_public_key:
            return self.__routes_signing_public_key

        return psi_ops_crypto_tools.get_base64_der_public_key(
                self.get_routes_signing_key_pair().pem_key_pair,
                self.get_routes_signing_key_pair().password)

    def __split_tunnel_dns_server(self):
        return '8.8.4.4'  # TODO get it from psinet?

    def build(
            self,
            propagation_channel_name,
            sponsor_name,
            remote_server_list_url_split,
            OSL_root_url_split,
            info_link_url,
            upgrade_url_split,
            get_new_version_url,
            get_new_version_email,
            faq_url,
            privacy_policy_url,
            platforms=None,
            test=False):
        if not platforms:
            platforms = [CLIENT_PLATFORM_WINDOWS, CLIENT_PLATFORM_ANDROID]

        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        sponsor = self.get_sponsor_by_name(sponsor_name)
        encoded_server_list, expected_egress_ip_addresses = \
                    self.__get_encoded_server_list(propagation_channel.id, test=test, include_propagation_servers=test)

        remote_server_list_signature_public_key = \
            psi_ops_crypto_tools.get_base64_der_public_key(
                self.__get_remote_server_list_signing_key_pair().pem_key_pair,
                REMOTE_SERVER_SIGNING_KEY_PAIR_PASSWORD)

        feedback_encryption_public_key = \
            psi_ops_crypto_tools.get_base64_der_public_key(
                self.get_feedback_encryption_key_pair().pem_key_pair,
                self.get_feedback_encryption_key_pair().password)

        feedback_upload_info = self.get_feedback_upload_info()

        upgrade_signature_public_key = \
            psi_ops_crypto_tools.get_base64_der_public_key(
                self.__get_upgrade_package_signing_key_pair().pem_key_pair,
                UPGRADE_PACKAGE_SIGNING_KEY_PAIR_PASSWORD)

        builders = {
            CLIENT_PLATFORM_WINDOWS: psi_ops_build_windows.build_client,
            CLIENT_PLATFORM_ANDROID: psi_ops_build_android.build_client
        }

        for plugin in plugins:
            if hasattr(plugin, 'build_android_client'):
                builders[CLIENT_PLATFORM_ANDROID] = plugin.build_android_client

        sponsor_banner = sponsor.banner
        if sponsor.use_data_from_sponsor_id:
            sponsor_banner = self.__sponsors[sponsor.use_data_from_sponsor_id].banner

        # The *_urls_json params supercede the legacy *_url_split params

        alternate_download_url_domains = None
        number_of_alternate_download_url_domains = 3
        if self.__alternate_s3_bucket_domains:
            if len(self.__alternate_s3_bucket_domains) > number_of_alternate_download_url_domains:
                alternate_download_url_domains = random.sample(self.__alternate_s3_bucket_domains, number_of_alternate_download_url_domains)
            else:
                alternate_download_url_domains = self.__alternate_s3_bucket_domains

        def download_urls(url_split):
            urls = []
            urls.append({'URL': base64.b64encode(urlparse.urlunsplit(url_split)),
                         'OnlyAfterAttempts': 0,
                         'SkipVerify': False})
            if alternate_download_url_domains and url_split.path.startswith('/psiphon/'):
                for domain in alternate_download_url_domains:
                    urls.append({'URL': base64.b64encode('https://' + domain + url_split.path.split('/psiphon')[1]),
                                 'OnlyAfterAttempts': 2,
                                 'SkipVerify': True})
            return urls

        remote_server_list_urls = download_urls(remote_server_list_url_split)
        OSL_root_urls = download_urls(OSL_root_url_split)
        upgrade_urls = download_urls(upgrade_url_split)

        return [builders[platform](
                        propagation_channel.id,
                        sponsor.id,
                        base64.b64decode(sponsor_banner),
                        encoded_server_list,
                        remote_server_list_signature_public_key,
                        remote_server_list_url_split,
                        json.dumps(remote_server_list_urls).replace('"', '\\"'),
                        OSL_root_url_split,
                        json.dumps(OSL_root_urls).replace('"', '\\"'),
                        self.__server_entry_signing_key_pair[0],
                        self.__exchange_obfuscation_key,
                        feedback_encryption_public_key,
                        feedback_upload_info.upload_server,
                        feedback_upload_info.upload_path,
                        feedback_upload_info.upload_server_headers,
                        json.dumps(self.get_feedback_upload_urls()).replace('"', '\\"'),
                        info_link_url,
                        upgrade_signature_public_key,
                        upgrade_url_split,
                        json.dumps(upgrade_urls).replace('"', '\\"'),
                        get_new_version_url,
                        get_new_version_email,
                        faq_url,
                        privacy_policy_url,
                        self.__split_tunnel_url_format(),
                        self.__split_tunnel_signature_public_key(),
                        self.__split_tunnel_dns_server(),
                        self.__client_versions[platform][-1].version if self.__client_versions[platform] else 0,
                        propagation_channel.propagator_managed_upgrades,
                        test,
                        list(self.__android_home_tab_url_exclusions)) for platform in platforms]

    def __make_upgrade_package_from_build(self, build_filename):
        with open(build_filename, 'rb') as f:
            data = f.read()
        authenticated_data_package  = \
            psi_ops_crypto_tools.make_signed_data(
                self.__get_upgrade_package_signing_key_pair().pem_key_pair,
                UPGRADE_PACKAGE_SIGNING_KEY_PAIR_PASSWORD,
                base64.b64encode(data))
        upgrade_filename = build_filename + psi_ops_s3.DOWNLOAD_SITE_UPGRADE_SUFFIX
        f = gzip.open(upgrade_filename, 'wb')
        try:
            f.write(authenticated_data_package)
        finally:
            f.close()
        return upgrade_filename

    def __deploy_implementation_to_hosts(self, hosts):
        hosts_and_servers = [(host, [server for server in self.__servers.itervalues() if server.host_id == host.id]) for host in hosts]
        psi_ops_deploy.deploy_implementation_to_hosts(
            hosts_and_servers,
            self.__get_own_encoded_server_entries_for_host,
            self.__discovery_strategy_value_hmac_key,
            plugins,
            self.__TCS_psiphond_config_values)

    def deploy(self):
        # Deploy as required:
        #
        # - Implementation to flagged hosts
        # - Builds for required channels and sponsors
        # - Publish, tweet
        # - Email and stats server config
        # - Remove hosts from providers that are marked for removal
        # - Websites
        # - OSLs
        # - Data to all hosts
        #
        # NOTE: Order is important. Hosts get new implementation before
        # new data, in case schema has changed; deploy builds before
        # deploying new data so an upgrade is available when it's needed

        assert(self.is_locked)

        # Host implementation

        hosts = [self.__hosts[host_id] for host_id in self.__deploy_implementation_required_for_hosts]
        self.__deploy_implementation_to_hosts(hosts)

        if len(self.__deploy_implementation_required_for_hosts) > 0:
            self.__deploy_implementation_required_for_hosts.clear()
            self.save()

        # Build

        for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
            deployed_builds_for_platform = False
            for target in self.__deploy_builds_required_for_campaigns[platform].copy():

                propagation_channel_id, sponsor_id = target
                propagation_channel = self.__propagation_channels[propagation_channel_id]
                sponsor = self.__sponsors[sponsor_id]

                for campaign in filter(lambda x: x.propagation_channel_id == propagation_channel_id, sponsor.campaigns):

                    if campaign.platforms != None and not platform in campaign.platforms:
                        continue

                    if not campaign.s3_bucket_name:
                        campaign.s3_bucket_name = psi_ops_s3.create_s3_website_bucket_name()
                        campaign.log('created s3 bucket %s' % (campaign.s3_bucket_name,))

                        # We're no longer actually creating buckets, so we
                        # don't need to save here.
                        # self.save()  # don't leak buckets

                        # When creating a new bucket we'll load the website into
                        # it. Rather than setting flags in all of the creation
                        # methods, we'll use the above creation as the chokepoint.
                        # After this we just have to worry about website updates.
                        # Note that this generates the site. It's not very efficient
                        # to do that here, but it happens infrequently enough to be okay.
                        self.update_static_site_content(sponsor, campaign, True)

                    # Remote server list: for clients to get new servers via S3,
                    # we embed the bucket URL in the build. The remote server
                    # list is placed in the S3 bucket.

                    remote_server_list_url_split = psi_ops_s3.get_s3_bucket_resource_url_split(
                                                campaign.s3_bucket_name,
                                                psi_ops_s3.DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME_COMPRESSED)

                    OSL_root_url_split = psi_ops_s3.get_s3_bucket_resource_url_split(
                                                campaign.s3_bucket_name,
                                                psi_ops_s3.DOWNLOAD_SITE_OSL_ROOT_PATH)

                    info_link_url = psi_ops_s3.get_s3_bucket_home_page_url(campaign.s3_bucket_name)
                    for plugin in plugins:
                        if hasattr(plugin, 'info_link_url'):
                            info_link_url = plugin.info_link_url(platform)

                    remote_server_list = \
                        psi_ops_crypto_tools.make_signed_data(
                            self.__get_remote_server_list_signing_key_pair().pem_key_pair,
                            REMOTE_SERVER_SIGNING_KEY_PAIR_PASSWORD,
                            '\n'.join(self.__get_encoded_server_list(propagation_channel.id)[0]))

                    # compressed server_list
                    # the entire file is compressed instead of just the payload
                    # because the compressed payload would need to be base64 encoded
                    # in the json contents of the file, losing compression
                    remote_server_list_compressed = zlib.compress(remote_server_list)

                    # Build for each client platform

                    client_build_filenames = {
                        CLIENT_PLATFORM_WINDOWS: psi_ops_s3.DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME,
                        CLIENT_PLATFORM_ANDROID: psi_ops_s3.DOWNLOAD_SITE_ANDROID_BUILD_FILENAME
                    }
                    for plugin in plugins:
                        if hasattr(plugin, 'adjust_client_build_filenames'):
                            plugin.adjust_client_build_filenames(client_build_filenames)

                    s3_upgrade_resource_name = client_build_filenames[platform] + psi_ops_s3.DOWNLOAD_SITE_UPGRADE_SUFFIX

                    upgrade_url_split = psi_ops_s3.get_s3_bucket_resource_url_split(campaign.s3_bucket_name, s3_upgrade_resource_name)
                    get_new_version_url = psi_ops_s3.get_s3_bucket_download_page_url(campaign.s3_bucket_name)

                    assert(self.__default_email_autoresponder_account)
                    get_new_version_email = self.__default_email_autoresponder_account.email_address
                    if type(campaign.account) == EmailPropagationAccount:
                        get_new_version_email = campaign.account.email_address

                    faq_url = psi_ops_s3.get_s3_bucket_faq_url(campaign.s3_bucket_name)
                    privacy_policy_url = psi_ops_s3.get_s3_bucket_privacy_policy_url(campaign.s3_bucket_name)

                    build_filename = self.build(
                                        propagation_channel.name,
                                        sponsor.name,
                                        remote_server_list_url_split,
                                        OSL_root_url_split,
                                        info_link_url,
                                        upgrade_url_split,
                                        get_new_version_url,
                                        get_new_version_email,
                                        faq_url,
                                        privacy_policy_url,
                                        [platform])[0]

                    upgrade_filename = self.__make_upgrade_package_from_build(build_filename)

                    # Upload client builds
                    # We only upload the builds for Propagation Channel IDs that need to be known for the host.
                    # UPDATE: Now we copy all builds.  We know that this breaks compartmentalization.
                    # However, we do not want to prevent an upgrade in the case where a user has
                    # downloaded from multiple propagation channels, and might therefore be connecting
                    # to a server from one propagation channel using a build from a different one.
                    # UPDATE: Now clients get update packages out-of-band (S3). This server-hosted
                    # upgrade capability may be resurrected in the future if necessary.
                    #psi_ops_deploy.deploy_build_to_hosts(self.__hosts.itervalues(), build_filename)

                    # Publish to propagation mechanisms

                    client_version = self.__client_versions[platform][-1].version if self.__client_versions[platform] else 0

                    psi_ops_s3.update_s3_download_in_buckets(
                        self.__aws_account,
                        [(build_filename, client_version, client_build_filenames[platform]),
                         (upgrade_filename, client_version, s3_upgrade_resource_name)],
                        remote_server_list,
                        remote_server_list_compressed,
                        [campaign.s3_bucket_name, campaign.alternate_s3_bucket_name])
                    # Don't log this, too much noise
                    #campaign.log('updated s3 bucket %s' % (campaign.s3_bucket_name,))

                    if campaign.propagation_mechanism_type == 'twitter':
                        message = psi_templates.get_tweet_message(campaign.s3_bucket_name)
                        psi_ops_twitter.tweet(campaign.account, message)
                        campaign.log('tweeted')
                    elif campaign.propagation_mechanism_type == 'email-autoresponder':
                        if not self.__deploy_email_config_required:
                            self.__deploy_email_config_required = True
                            # Don't log this, too much noise
                            #campaign.log('email push scheduled')

                # NOTE: before we added remote server lists, it used to be that
                # multiple campaigns with different buckets but the same prop/sponsor IDs
                # could share one build. The "deploy_builds_required_for_campaigns" dirty
                # flag granularity is a hold-over from that. In the current code, this
                # means some builds may be repeated unnecessarily in a failure case.

                self.__deploy_builds_required_for_campaigns[platform].remove(target)
                deployed_builds_for_platform = True

            # NOTE: it is too expensive to save too frequently.
            # Save only after finishing all builds for a platform.
            if deployed_builds_for_platform:
                self.save()

        # Email and stats server configs

        self.deploy_stats_config_if_required()

        if self.__deploy_email_config_required:
            self.push_email_config()
            self.__deploy_email_config_required = False
            self.save()

        # Remove hosts from providers that are marked for removal

        self.remove_hosts_from_providers()

        #
        # Website
        #
        if len(self.__deploy_website_required_for_sponsors) > 0:
            # Generate the static website from source
            website_generator.generate(WEBSITE_GENERATION_DIR)

            # Iterate through a copy so that we can remove as we go
            for sponsor_id in self.__deploy_website_required_for_sponsors.copy():
                sponsor = self.__sponsors[sponsor_id]
                for campaign in sponsor.campaigns:
                    if not campaign.s3_bucket_name:
                        campaign.s3_bucket_name = psi_ops_s3.create_s3_website_bucket_name()
                        campaign.log('created s3 bucket %s' % (campaign.s3_bucket_name,))
                        self.save()  # don't leak buckets

                    self.update_static_site_content(sponsor, campaign)

                self.__deploy_website_required_for_sponsors.remove(sponsor_id)

            self.save()

        # Pave OSLs

        if len(self.__deploy_pave_osls_required_for_propagation_channels) > 0:
            self.pave_OSLs(self.__deploy_pave_osls_required_for_propagation_channels)
            self.__deploy_pave_osls_required_for_propagation_channels.clear()
            self.save()

        # Host data

        if self.__deploy_data_required_for_all:
            psi_ops_deploy.deploy_data_to_hosts(
                self.get_hosts(),
                self.__compartmentalize_data_for_host,
                self.__TCS_traffic_rules_set,
                self.__TCS_OSL_config,
                self.__TCS_tactics_config_template,
                self.__TCS_blocklist_csv)
            self.__deploy_data_required_for_all = False
            self.save()


    def deploy_stats_config_if_required(self):
        if self.__deploy_stats_config_required:
            self.push_stats_config()
            self.push_devops_config()
            self.__deploy_stats_config_required = False
            self.save()


    def pave_OSLs(self, target_propagation_channel_ids, offset=None, period=None):
        # Note: Only writes to buckets for campaigns in target_propagation_channel_ids

        osl_config_filename = os.path.join('.', 'osl_config.json')
        osl_payload_filename = os.path.join('.', 'osl_payload.json')
        signing_key_filename = os.path.join('.', 'signing_key.pem')
        output_dir = tempfile.mkdtemp(prefix='osl')

        now = datetime.datetime.now()
        osl_servers = [server for server in self.__servers.itervalues()
                       if server.osl_ids and server.osl_discovery_date_range and
                       server.osl_discovery_date_range[0] <= now < server.osl_discovery_date_range[1]]

        osl_payload = []
        for osl_server in osl_servers:
            osl_payload.append({'ServerEntry' : self.__get_encoded_server_entry(osl_server),
                                'OSLIDs' : osl_server.osl_ids})

        try:
            # Pave full OSL file sets for all propagation channels in the OSL config.

            osl_config_file = open(osl_config_filename, 'w')
            osl_config_file.write(self.__TCS_OSL_config)
            osl_config_file.close()

            osl_payload_file = open(osl_payload_filename, 'w')
            osl_payload_file.write(json.dumps(osl_payload))
            osl_payload_file.close()

            signing_key_file = open(signing_key_filename, 'w')
            signing_key_file.write(self.__get_remote_server_list_signing_key_pair().pem_key_pair)
            signing_key_file.close()

            config = json.loads(self.__TCS_OSL_config)

            # Source: https://github.com/Psiphon-Labs/psiphon-tunnel-core/tree/master/psiphon/common/osl/paver
            paver_binary = 'paver.exe'
            if os.name == 'posix':
                paver_binary = 'paver'

            paver_command_line = \
                [os.path.join('.', paver_binary),
                 "-config", osl_config_filename,
                 "-payload", osl_payload_filename,
                 "-key", signing_key_filename,
                 "-omit-md5sums", "0",
                 "-output", output_dir]

            if offset:
                paver_command_line += ["-offset", str(offset)]

            if period:
                paver_command_line += ["-period", str(period)]

            # Note: raises CalledProcessError when paver fails
            output = subprocess.check_output(paver_command_line, stderr=subprocess.STDOUT)
            print output

            paved_propagation_channel_ids = set()
            for scheme_index, scheme in enumerate(config['Schemes']):
                for propagation_channel_id in scheme['PropagationChannelIDs']:
                    paved_propagation_channel_ids.add(propagation_channel_id)

            for propagation_channel_id in paved_propagation_channel_ids:

                if not propagation_channel_id in target_propagation_channel_ids:
                    continue

                prop_dir = os.path.join(output_dir, propagation_channel_id)
                upload_filenames = [os.path.join(prop_dir, filename) for filename in os.listdir(prop_dir)]

                for sponsor in self.__sponsors.itervalues():
                    for campaign in sponsor.campaigns:
                        if campaign.propagation_channel_id == str(propagation_channel_id):
                            psi_ops_s3.update_s3_osl_with_files_in_buckets(
                                self.__aws_account,
                                [campaign.s3_bucket_name, campaign.alternate_s3_bucket_name],
                                upload_filenames)

            # Ensure all other buckets have a valid, empty osl-registry. Clients will
            # expect this to exist regardless of whether a propagation channel is part
            # of the OSL config.

            empty_osl_registry = zlib.compress(psi_ops_crypto_tools.make_signed_data(
                    self.__get_remote_server_list_signing_key_pair().pem_key_pair,
                    REMOTE_SERVER_SIGNING_KEY_PAIR_PASSWORD,
                    base64.b64encode('{"FileSpecs" : []}')))

            for sponsor in self.__sponsors.itervalues():
                for campaign in sponsor.campaigns:
                    if not campaign.propagation_channel_id in paved_propagation_channel_ids:
                        if campaign.propagation_channel_id in target_propagation_channel_ids:
                            psi_ops_s3.update_s3_osl_key_in_buckets(
                                self.__aws_account,
                                [campaign.s3_bucket_name, campaign.alternate_s3_bucket_name],
                                'osl-registry',
                                empty_osl_registry)

        finally:
            try:
                os.remove(osl_config_filename)
                os.remove(osl_payload_filename)
                os.remove(signing_key_filename)
                shutil.rmtree(output_dir, ignore_errors=True)
            except:
                pass

    def get_current_propagation_channel_and_osl_ids_for_scheme(self, scheme_id):
        propagation_channel_ids = set()
        osl_ids = set()

        osl_config_filename = os.path.join('.', 'osl_config.json')

        try:
            # Pave full OSL file sets for all propagation channels in the OSL config.

            osl_config_file = open(osl_config_filename, 'w')
            osl_config_file.write(self.__TCS_OSL_config)
            osl_config_file.close()

            # Source: https://github.com/Psiphon-Labs/psiphon-tunnel-core/tree/master/psiphon/common/osl/paver
            paver_binary = 'paver.exe'
            if os.name == 'posix':
                paver_binary = 'paver'

            paver_command_line = \
                [os.path.join('.', paver_binary),
                 "-config", osl_config_filename,
                 "-list-scheme", str(scheme_id)]

            # Note: raises CalledProcessError when paver fails
            output = subprocess.check_output(paver_command_line, stderr=subprocess.STDOUT)

            for line in output.strip().split('\n'):
                propagation_channel_id, osl_id = line.split()
                propagation_channel_ids.add(propagation_channel_id)
                osl_ids.add(osl_id)

        finally:
            try:
                os.remove(osl_config_filename)
            except:
                pass

        return propagation_channel_ids, osl_ids

    def update_static_site_content(self, sponsor, campaign, do_generate=False):
        assert(self.is_locked)

        if do_generate:
            # Generate the static website from source
            website_generator.generate(WEBSITE_GENERATION_DIR)

        assert(self.__default_email_autoresponder_account)
        get_new_version_email = self.__default_email_autoresponder_account.email_address
        if type(campaign.account) == EmailPropagationAccount:
            get_new_version_email = campaign.account.email_address

        sponsor_website_banner = sponsor.website_banner
        sponsor_website_banner_link = sponsor.website_banner_link
        if sponsor.use_data_from_sponsor_id:
            sponsor_website_banner = self.__sponsors[sponsor.use_data_from_sponsor_id].website_banner
            sponsor_website_banner_link = self.__sponsors[sponsor.use_data_from_sponsor_id].website_banner_link

        psi_ops_s3.update_website_in_buckets(
                        self.__aws_account,
                        [campaign.s3_bucket_name, campaign.alternate_s3_bucket_name],
                        campaign.custom_download_site,
                        WEBSITE_GENERATION_DIR,
                        sponsor_website_banner,
                        sponsor_website_banner_link,
                        get_new_version_email)
        campaign.log('updated website in S3 bucket %s' % (campaign.s3_bucket_name,))

    def update_routes(self):
        assert(self.is_locked)  # (host.log is called by deploy)
        psi_routes.make_routes()
        psi_ops_deploy.deploy_routes_to_hosts(self.__hosts.values())

    def update_external_signed_routes(self):
        psi_routes.make_signed_routes(
                self.get_routes_signing_key_pair().pem_key_pair,
                self.get_routes_signing_key_pair().password)
        psi_ops_s3.upload_signed_routes(
                self.__aws_account,
                psi_routes.GEO_ROUTES_ROOT,
                psi_routes.GEO_ROUTES_SIGNED_EXTENSION)

    def push_devops_config(self):
        assert(self.is_locked)
        print 'push devops config...'

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        try:
            temp_file.write(self.__compartmentalize_data_for_devops_server())
            temp_file.close()
            psi_ops_cms.delete_document(for_stats=False)
            psi_ops_cms.import_document(temp_file.name, False, True)
        finally:
            try:
                os.remove(temp_file.name)
            except:
                pass

    def push_stats_config(self):
        assert(self.is_locked)
        print 'push stats config...'

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        try:
            temp_file.write(self.__compartmentalize_data_for_stats_server())
            temp_file.close()
            psi_ops_cms.delete_document(for_stats=True)
            psi_ops_cms.import_document(temp_file.name, True, False)
        finally:
            try:
                os.remove(temp_file.name)
            except:
                pass

    def push_email_config(self):
        # Generate the email server config file, which is a JSON format
        # mapping every request email to a response body containing
        # download links.
        # Currently, we generate the entire config file for any change.

        assert(self.is_locked)
        print 'push email config...'

        emails = []
        for sponsor in self.__sponsors.itervalues():
            for campaign in sponsor.campaigns:
                if (campaign.propagation_mechanism_type == 'email-autoresponder' and
                    campaign.s3_bucket_name != None):

                    # Email without attachments
                    emails.append(
                        {
                         'email_addr': campaign.account.email_address,
                         'body':
                            [
                                ['plain', psi_templates.get_plaintext_email_content(
                                                campaign.s3_bucket_name,
                                                campaign.languages)],
                                ['html', psi_templates.get_html_email_content(
                                                campaign.s3_bucket_name,
                                                campaign.languages)]
                            ],
                         'attachments': None,
                         'send_method': 'SES'
                        })

                    # Email with attachments
                    attachments = []
                    if campaign.platforms == None or CLIENT_PLATFORM_WINDOWS in campaign.platforms:
                        attachments.append([campaign.s3_bucket_name,
                                            psi_ops_s3.DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME,
                                            psi_ops_s3.EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME])
                    if campaign.platforms == None or CLIENT_PLATFORM_ANDROID in campaign.platforms:
                        attachments.append([campaign.s3_bucket_name,
                                            psi_ops_s3.DOWNLOAD_SITE_ANDROID_BUILD_FILENAME,
                                            psi_ops_s3.EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME])

                    emails.append(
                        {
                         'email_addr': campaign.account.email_address,
                         'body':
                            [
                                ['plain', psi_templates.get_plaintext_attachment_email_content(
                                                campaign.s3_bucket_name,
                                                psi_ops_s3.EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME,
                                                psi_ops_s3.EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME,
                                                campaign.languages,
                                                campaign.platforms)],
                                ['html', psi_templates.get_html_attachment_email_content(
                                                campaign.s3_bucket_name,
                                                psi_ops_s3.EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME,
                                                psi_ops_s3.EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME,
                                                campaign.languages,
                                                campaign.platforms)]
                            ],
                         'attachments': attachments,
                         'send_method': 'SMTP'
                        })
                    # Don't log this, too much noise
                    #campaign.log('configuring email')

        psi_ops_s3.put_string_to_key_in_bucket(self.__aws_account,
                                               self.__automation_bucket,
                                               EMAIL_RESPONDER_CONFIG_BUCKET_KEY,
                                               json.dumps(emails, indent=2),
                                               False)  # not public

    def upgrade_all_TCS_hosts(self):
        TCS_hosts = [host for host in self.__hosts.itervalues() if host.is_TCS]
        self.__deploy_implementation_to_hosts(TCS_hosts)

    def add_legacy_server_version(self):
        assert(self.is_locked)
        # Marks all hosts for re-deployment of server implementation
        for host in self.__hosts.itervalues():
            if host.is_TCS:
                continue
            self.__deploy_implementation_required_for_hosts.add(host.id)
            host.log('marked for implementation deployment')

    def set_TCS_traffic_rules_set(self, traffic_rules_set):
        assert(self.is_locked)

        # Check that the input is valid JSON
        json.loads(traffic_rules_set)

        self.__TCS_traffic_rules_set = traffic_rules_set

        self.__deploy_data_required_for_all = True

    def set_TCS_OSL_config(self, OSL_config):
        assert(self.is_locked)

        # Check that the input is valid JSON
        json.loads(OSL_config)

        self.__TCS_OSL_config = OSL_config

        self.__deploy_data_required_for_all = True

        for propagation_channel_id in self.__propagation_channels.iterkeys():
            self.__deploy_pave_osls_required_for_propagation_channels.add(propagation_channel_id)

    def set_TCS_tactics_config_template(self, tactics_config_template):
        assert(self.is_locked)

        # Check that the input is valid JSON
        json.loads(tactics_config_template)

        self.__TCS_tactics_config_template = tactics_config_template

        self.__deploy_data_required_for_all = True

    def set_TCS_psiphond_config_values(self, psiphond_config_values):
        assert(self.is_locked)
        assert(isinstance(psiphond_config_values, dict))

        self.__TCS_psiphond_config_values = psiphond_config_values

        for host in self.__hosts.itervalues():
            if host.is_TCS:
                self.__deploy_implementation_required_for_hosts.add(host.id)

    def set_TCS_blocklist_csv(self, blocklist_csv):
        assert(self.is_locked)

        # Check that the CSV is valid
        csvreader = csv.reader(blocklist_csv.split('\n'), delimiter=',')
        for row in csvreader:
            if row:
                assert(len(row) == 3)

        self.__TCS_blocklist_csv = blocklist_csv

        self.__deploy_data_required_for_all = True

    def add_TCS_server_version(self):
        assert(self.is_locked)
        # Marks all hosts for re-deployment of server implementation
        for host in self.__hosts.itervalues():
            if host.is_TCS:
                self.__deploy_implementation_required_for_hosts.add(host.id)
                host.log('marked for implementation deployment')

    def add_client_version(self, platform, description):
        assert(self.is_locked)
        assert(platform in [CLIENT_PLATFORM_WINDOWS, CLIENT_PLATFORM_ANDROID])
        # Records the new version number to trigger upgrades
        next_version = 1
        if len(self.__client_versions[platform]) > 0:
            next_version = int(self.__client_versions[platform][-1].version) + 1
        client_version = ClientVersion(str(next_version), description)
        self.__client_versions[platform].append(client_version)
        # Mark deploy flag to rebuild and upload all clients
        for sponsor in self.__sponsors.itervalues():
            for campaign in sponsor.campaigns:
                self.__deploy_builds_required_for_campaigns[platform].add(
                        (campaign.propagation_channel_id, sponsor.id))
                # Don't log this, too much noise
                #campaign.log('marked for build and publish (upgraded %s client)' % (platform,))
        # Need to deploy data as well for auto-update
        self.__deploy_data_required_for_all = True

    def get_server_entry(self, server_id):
        server = filter(lambda x: x.id == server_id, self.__servers.itervalues())[0]
        return self.__get_encoded_server_entry(server)

    def deploy_implementation_and_data_for_host_with_server(self, server_id):
        server = filter(lambda x: x.id == server_id, self.__servers.itervalues())[0]
        host = filter(lambda x: x.id == server.host_id, self.__hosts.itervalues())[0]
        servers = [server for server in self.__servers.itervalues() if server.host_id == host.id]
        psi_ops_deploy.deploy_implementation(host, servers, self.__discovery_strategy_value_hmac_key, plugins, self.__TCS_psiphond_config_values)
        psi_ops_deploy.deploy_data(
            host,
            self.__compartmentalize_data_for_host(host.id, host.is_TCS),
            self.__TCS_traffic_rules_set,
            self.__TCS_OSL_config,
            self.__TCS_tactics_config_template,
            self.__TCS_blocklist_csv)

    def deploy_implementation_and_data_for_propagation_channel(self, propagation_channel_name):
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        servers = [server for server in self.__servers.itervalues() if server.propagation_channel_id == propagation_channel.id]
        for server in servers:
            self.deploy_implementation_and_data_for_host_with_server(server.id)

    def set_aws_account(self, access_id, secret_key):
        assert(self.is_locked)
        psi_utils.update_recordtype(
            self.__aws_account,
            access_id=access_id, secret_key=secret_key)

    def upsert_provider_rank(self, provider, rank):
        '''
        Inserts or updates a Provider-Rank entry. The "key" for an entry is provider.
        rank: the higher the score, the more the provider will be preferred when
            provideres are being randomly selected among.
        '''
        assert(self.is_locked)
        if provider not in ProviderRank.provider_values:
            raise ValueError('bad provider value: %s' % provider)

        pr = ProviderRank()
        found = False
        for existing_pr in self.__provider_ranks:
            if existing_pr.provider == provider:
                pr = existing_pr
                found = True
                break

        if not found:
            self.__provider_ranks.append(pr)

        psi_utils.update_recordtype(
            pr,
            provider=provider, rank=rank)

    def set_linode_account(self, api_key, base_id, base_ip_address, base_ssh_port,
                           base_root_password, base_stats_username, base_host_public_key,
                           base_known_hosts_entry, base_rsa_private_key, base_rsa_public_key,
                           base_tarball_path, api_token):
        assert(self.is_locked)
        psi_utils.update_recordtype(
            self.__linode_account,
            api_key=api_key, base_id=base_id, base_ip_address=base_ip_address,
            base_ssh_port=base_ssh_port, base_root_password=base_root_password,
            base_stats_username=base_stats_username, base_host_public_key=base_host_public_key,
            base_known_hosts_entry=base_known_hosts_entry, base_rsa_private_key=base_rsa_private_key,
            base_rsa_public_key=base_rsa_public_key, base_tarball_path=base_tarball_path, api_token=api_token)

    def set_digitalocean_account(self, client_id, api_key, base_id, base_size_id, base_region_id, base_ssh_port,
                                 base_stats_username, base_host_public_key,
                                 base_rsa_private_key, ssh_key_template_id):
        assert(self.is_locked)
        psi_utils.update_recordtype(
            self.__digitalocean_account,
            client_id=client_id, api_key=api_key, base_id=base_id,
            base_size_id=base_size_id, base_region_id=base_region_id, base_ssh_port=base_ssh_port,
            base_stats_username=base_stats_username, base_host_public_key=base_host_public_key,
            base_rsa_private_key=base_rsa_private_key, ssh_key_template_id=ssh_key_template_id)

    def set_vpsnet_account(self, account_id, api_key, api_base_url, base_ssh_port,
                           base_root_password, base_stats_username,
                           base_cloud_id, base_system_template, base_ssd_plan):
        assert(self.is_locked)
        psi_utils.update_recordtype(
            self.__vpsnet_account,
            account_id=account_id, api_key=api_key, api_base_url=api_base_url,
            base_ssh_port=base_ssh_port, base_root_password=base_root_password,
            base_stats_username=base_stats_username, base_cloud_id=base_cloud_id,
            base_system_template=base_system_template, base_ssd_plan=base_ssd_plan)

    def set_vps247_account(self, account_id, api_key, api_base_url, base_ssh_port,
                        base_root_password, base_stats_username,
                        base_rsa_private_key, base_region_id, base_package_id):
        assert(self.is_locked)
        psi_utils.update_recordtype(
            self.__vps247_account,
            account_id=account_id, api_key=api_key, api_base_url=api_base_url, base_ssh_port=base_ssh_port,
            base_root_password=base_root_password, base_stats_username=base_stats_username,
            base_rsa_private_key=base_rsa_private_key,
            base_region_id=base_region_id, base_package_id=base_package_id)

    def upsert_elastichosts_account(self, zone, uuid, api_key, base_drive_id,
                                    cpu, mem, base_host_public_key, root_username,
                                    base_root_password, base_ssh_port, stats_username, rank):
        '''
        Inserts or updates an ElasticHosts account information entry. The "key"
        for an entry is zone+uuid.
        rank: the higher the score, the more the account will be preferred when
            the ElasticHosts accounts are being randomly selected among.
        '''
        assert(self.is_locked)
        if zone not in ElasticHostsAccount.zone_values:
            raise ValueError('bad zone value: %s' % zone)

        acct = ElasticHostsAccount()
        found = False
        for existing_acct in self.__elastichosts_accounts:
            if existing_acct.zone == zone and existing_acct.uuid == uuid:
                acct = existing_acct
                found = True
                break

        if not found:
            self.__elastichosts_accounts.append(acct)

        psi_utils.update_recordtype(
            acct,
            zone=zone, uuid=uuid,
            api_key=acct.api_key if api_key is None else api_key,
            base_drive_id=acct.base_drive_id if base_drive_id is None else base_drive_id,
            cpu=acct.cpu if cpu is None else cpu,
            mem=acct.mem if mem is None else mem,
            base_host_public_key=acct.base_host_public_key if base_host_public_key is None else base_host_public_key,
            root_username=acct.root_username if root_username is None else root_username,
            base_root_password=acct.base_root_password if base_root_password is None else base_root_password,
            base_ssh_port=acct.base_ssh_port if base_ssh_port is None else base_ssh_port,
            stats_username=acct.stats_username if stats_username is None else stats_username,
            rank=acct.rank if rank is None else rank)

    def set_automation_bucket(self, bucket):
        assert(self.is_locked)
        self.__automation_bucket = bucket
        self.__deploy_email_config_required = True
        # TODO: Log the change? Where?

    def set_stats_server_account(self, ip_address, ssh_port,
                                 ssh_username, ssh_password, ssh_host_key):
        assert(self.is_locked)
        psi_utils.update_recordtype(
            self.__stats_server_account,
            ip_address=ip_address, ssh_port=ssh_port, ssh_username=ssh_username,
            ssh_password=ssh_password, ssh_host_key=ssh_host_key)

    def add_speed_test_url(self, server_address, server_port, request_path):
        assert(self.is_locked)
        if (server_address, server_port, request_path) not in [
                (s.server_address, s.server_port, s.request_path) for s in self.__speed_test_urls]:
            self.__speed_test_urls.append(SpeedTestURL(server_address, server_port, request_path))
            self.__deploy_data_required_for_all = True

    def __get_encoded_server_entry(self, server):

        # TCS web server certificate has PEM headers and newlines, so strip those now
        # for legacy format compatibility
        web_server_certificate = server.web_server_certificate
        host = self.get_host_for_server(server)
        if host and host.is_TCS:
            web_server_certificate = ''.join(server.web_server_certificate.split('\n')[1:-2])

        # Double-check that we're not giving our blank server credentials
        # ...this has happened in the past when following manual build steps
        assert(len(server.ip_address) > 1)
        assert(len(server.web_server_port) > 1)
        assert(len(server.web_server_secret) > 1)
        assert(len(web_server_certificate) > 1)

        # Extended (i.e., new) entry fields are in a JSON string
        extended_config = {}

        # NOTE: also putting original values in extended config for easier parsing for new clients
        extended_config['ipAddress'] = server.ip_address
        extended_config['webServerPort'] = server.web_server_port
        extended_config['webServerSecret'] = server.web_server_secret
        extended_config['webServerCertificate'] = web_server_certificate

        extended_config['sshPort'] = int(server.ssh_port) if server.ssh_port else 0
        extended_config['sshUsername'] = server.ssh_username if server.ssh_username else ''
        extended_config['sshPassword'] = server.ssh_password if server.ssh_password else ''

        extended_config['sshHostKey'] = ''
        if server.ssh_host_key:
            ssh_host_key_type, extended_config['sshHostKey'] = server.ssh_host_key.split(' ')
            assert(ssh_host_key_type == 'ssh-rsa')

        extended_config['sshObfuscatedPort'] = int(server.ssh_obfuscated_port) if server.ssh_obfuscated_port else 0
        # Use the latest alternate port unless tunneling through meek
        if server.alternate_ssh_obfuscated_ports and not (server.capabilities['FRONTED-MEEK'] or server.capabilities['UNFRONTED-MEEK'] or server.capabilities['UNFRONTED-MEEK-SESSION-TICKET']):
            extended_config['sshObfuscatedPort'] = int(server.alternate_ssh_obfuscated_ports[-1])
        extended_config['sshObfuscatedQUICPort'] = int(server.ssh_obfuscated_quic_port) if server.ssh_obfuscated_quic_port else 0
        extended_config['sshObfuscatedTapdancePort'] = int(server.ssh_obfuscated_tapdance_port) if server.ssh_obfuscated_tapdance_port else 0
        extended_config['sshObfuscatedConjurePort'] = int(server.ssh_obfuscated_conjure_port) if server.ssh_obfuscated_conjure_port else 0
        extended_config['sshObfuscatedKey'] = server.ssh_obfuscated_key if server.ssh_obfuscated_key else ''

        host = self.__hosts[server.host_id]
        extended_config['region'] = host.region

        server_capabilities = copy_server_capabilities(server.capabilities) if server.capabilities else None
        if server_capabilities and server_capabilities['UNFRONTED-MEEK'] and int(host.meek_server_port) == 443:
            server_capabilities['UNFRONTED-MEEK'] = False
            server_capabilities['UNFRONTED-MEEK-HTTPS'] = True

        extended_config['meekServerPort'] = int(host.meek_server_port) if host.meek_server_port else 0
        extended_config['meekObfuscatedKey'] = host.meek_server_obfuscated_key if host.meek_server_obfuscated_key else ''
        extended_config['meekFrontingDomain'] = host.meek_server_fronting_domain if host.meek_server_fronting_domain else ''
        extended_config['meekFrontingHost'] = host.meek_server_fronting_host if host.meek_server_fronting_host else ''
        extended_config['meekCookieEncryptionPublicKey'] = host.meek_cookie_encryption_public_key if host.meek_cookie_encryption_public_key else ''

        if host.meek_server_fronting_domain:
            # Copy the set to avoid shuffling the original
            alternate_meek_fronting_addresses = list(self.__alternate_meek_fronting_addresses[host.meek_server_fronting_domain])
            if len(alternate_meek_fronting_addresses) > 0:
                random.shuffle(alternate_meek_fronting_addresses)
                extended_config['meekFrontingAddresses'] = alternate_meek_fronting_addresses[:3]

            extended_config['meekFrontingAddressesRegex'] = self.__alternate_meek_fronting_addresses_regex[host.meek_server_fronting_domain]
            extended_config['meekFrontingDisableSNI'] = self.__meek_fronting_disable_SNI[host.meek_server_fronting_domain]

        if host.alternate_meek_server_fronting_hosts:
            # Copy the set to avoid shuffling the original
            alternate_meek_server_fronting_hosts = list(host.alternate_meek_server_fronting_hosts)
            random.shuffle(alternate_meek_server_fronting_hosts)
            extended_config['meekFrontingHosts'] = alternate_meek_server_fronting_hosts[:3]
            if server_capabilities['FRONTED-MEEK']:
                server_capabilities['FRONTED-MEEK-HTTP'] = True

        if host.fronting_provider_id:
            extended_config['frontingProviderID'] = host.fronting_provider_id

        extended_config['tacticsRequestPublicKey'] = host.tactics_request_public_key if host.tactics_request_public_key else ''
        extended_config['tacticsRequestObfuscatedKey'] = host.tactics_request_obfuscated_key if host.tactics_request_obfuscated_key else ''

        extended_config['capabilities'] = [capability for capability, enabled in server_capabilities.iteritems() if enabled] if server_capabilities else []

        if host.passthrough_address is not None and len(host.passthrough_address) > 0:
            masked_capabilities = []
            for capability in extended_config['capabilities']:
                if psi_ops_deploy.server_entry_capability_supports_passthrough(capability):
                    capability += '-PASSTHROUGH'
                masked_capabilities.append(capability)
            extended_config['capabilities'] = masked_capabilities

        extended_config['configurationVersion'] = server.configuration_version

        encoded_server_entry = binascii.hexlify('%s %s %s %s %s' % (
                                    server.ip_address,
                                    server.web_server_port,
                                    server.web_server_secret,
                                    web_server_certificate,
                                    json.dumps(extended_config)))

        # The following server entries will be signed, once server_entry_signing_key_pair is initialzed:
        # entries mbedded in client builds; entries paved into remote and obfuscated server lists; entries
        # used in test_server; discovery entries paved into psinet for psiphond.
        #
        # The following will _not_ be signed: discovery entries issued by legacy, psi_web-based servers.

        if self.__server_entry_signing_key_pair != None:
            encoded_server_entry = self.sign_encoded_server_entry(encoded_server_entry)

        return encoded_server_entry

    def sign_encoded_server_entry(self, encoded_server_entry):
        server_entry_signer_binary = 'server-entry-signer.exe'
        if os.name == 'posix':
            server_entry_signer_binary = 'server-entry-signer'
        args = [os.path.join('.', server_entry_signer_binary), 'sign']
        env = {'SIGNER_PUBLIC_KEY': str(self.__server_entry_signing_key_pair[0]),
               'SIGNER_PRIVATE_KEY': str(self.__server_entry_signing_key_pair[1]),
               'SIGNER_SERVER_ENTRY': encoded_server_entry}
        return subprocess.Popen(args, env=env, stdout=subprocess.PIPE).communicate()[0].strip()

    def __get_encoded_server_list(self, propagation_channel_id,
                                  client_ip_address_strategy_value=None, event_logger=None, discovery_date=None, test=False, include_propagation_servers=True):
        if not client_ip_address_strategy_value:
            # embedded (propagation) server list
            # output all servers for propagation channel ID with no discovery date
            # NEW: include a random selection of permanent servers for greater load balancing
            permanent_server_ids = [server.id for server in self.__servers.itervalues()
                                    if server.propagation_channel_id != propagation_channel_id
                                    and server.is_permanent]
            random.shuffle(permanent_server_ids)

            servers = [server for server in self.__servers.itervalues()
                       if (server.propagation_channel_id == propagation_channel_id and
                           (server.is_permanent or (server.is_embedded and include_propagation_servers)))
                       or (not test and (server.id in permanent_server_ids[0:200]))]
        else:
            # discovery case
            if not discovery_date:
                discovery_date = datetime.datetime.now()


            # All discovery servers that are discoverable on this day are eligable for discovery.
            # Note: use used to compartmentalize this list by propagation channel, but now we
            # do not, making more discovery servers more broadly available and feeding into
            # the following discovery strategies.

            candidate_servers = [server for server in self.__servers.itervalues()
                                 if server.discovery_date_range is not None and
                                 server.discovery_date_range[0] <= discovery_date < server.discovery_date_range[1]]

            servers = psi_ops_discovery.select_servers(candidate_servers, client_ip_address_strategy_value)

        # optional logger (used by server to log each server IP address disclosed)
        if event_logger:
            for server in servers:
                event_logger(server.ip_address)
        return ([self.__get_encoded_server_entry(server) for server in servers],
                [server.egress_ip_address for server in servers])

    def __get_sponsor_home_pages(self, sponsor_id, region, client_platform):
        # Web server support function: fails gracefully
        if sponsor_id not in self.__sponsors:
            return []
        sponsor = self.__sponsors[sponsor_id]
        sponsor_home_pages = []
        home_pages = sponsor.home_pages
        if client_platform in (CLIENT_PLATFORM_ANDROID, CLIENT_PLATFORM_IOS):
            if sponsor.mobile_home_pages:
                home_pages = sponsor.mobile_home_pages
        # case: lookup succeeded and corresponding region home page found
        if region in home_pages:
            sponsor_home_pages = [home_page.url for home_page in home_pages[region]]
        # case: lookup failed or no corresponding region home page found --> use default
        if not sponsor_home_pages and 'None' in home_pages:
            sponsor_home_pages = [home_page.url for home_page in home_pages['None']]
        # client_region query parameter substitution
        sponsor_home_pages = [sponsor_home_page.replace('client_region=XX', 'client_region=' + region)
                                for sponsor_home_page in sponsor_home_pages]
        return sponsor_home_pages

    def _get_sponsor_page_view_regexes(self, sponsor_id):
        # Web server support function: fails gracefully
        if sponsor_id not in self.__sponsors:
            return []
        sponsor = self.__sponsors[sponsor_id]
        return sponsor.page_view_regexes

    def _get_sponsor_https_request_regexes(self, sponsor_id):
        # Web server support function: fails gracefully
        if sponsor_id not in self.__sponsors:
            return []
        sponsor = self.__sponsors[sponsor_id]
        return sponsor.https_request_regexes

    def __check_upgrade(self, platform, client_version):
        # check last version number against client version number
        # assumes versions list is in ascending version order
        if not self.__client_versions.get(platform):
            return None
        last_version = self.__client_versions[platform][-1].version
        if int(last_version) > int(client_version):
            return last_version
        return None

    def handshake(self, server_ip_address, client_ip_address_strategy_value,
                  client_region, propagation_channel_id, sponsor_id,
                  client_platform_string, client_version, event_logger=None):
        # Legacy handshake output is a series of Name:Value lines returned to
        # the client. That format will continue to be supported (old client
        # versions expect it), but the new format of a JSON-ified object will
        # also be output.

        config = {}

        # Match a client platform to client_platform_string
        platform = CLIENT_PLATFORM_WINDOWS
        if CLIENT_PLATFORM_ANDROID.lower() in client_platform_string.lower():
            platform = CLIENT_PLATFORM_ANDROID
        elif client_platform_string.startswith(CLIENT_PLATFORM_IOS):
            platform = CLIENT_PLATFORM_IOS

        if sponsor_id not in self.__sponsors and self.__default_sponsor_id and self.__default_sponsor_id in self.__sponsors:
            sponsor_id = self.__default_sponsor_id

        # Randomly choose one landing page from a set of landing pages
        # to give the client to open when connection established
        homepages = self.__get_sponsor_home_pages(sponsor_id, client_region, platform)
        random.shuffle(homepages)
        config['homepages'] = homepages

        # Tell client if an upgrade is available
        config['upgrade_client_version'] = self.__check_upgrade(platform, client_version)

        # Discovery
        # NOTE: Clients are expecting at least an empty list
        config['encoded_server_list'] = []
        if client_ip_address_strategy_value:
            config['encoded_server_list'], _ = \
                        self.__get_encoded_server_list(
                                                    propagation_channel_id,
                                                    client_ip_address_strategy_value,
                                                    event_logger=event_logger)

        # VPN relay protocol info
        # Note: The VPN PSK will be added in higher up the call stack

        # SSH relay protocol info
        #
        # SSH Session ID is a randomly generated unique ID used for
        # client-side session duration reporting
        #
        server = next(server for server in self.__servers.itervalues()
                      if server.internal_ip_address == server_ip_address)

        config['ssh_username'] = server.ssh_username
        config['ssh_password'] = server.ssh_password
        ssh_host_key_type, config['ssh_host_key'] = server.ssh_host_key.split(' ')
        assert(ssh_host_key_type == 'ssh-rsa')
        config['ssh_session_id'] = binascii.hexlify(os.urandom(8))
        if server.ssh_port:
            config['ssh_port'] = int(server.ssh_port)
        if server.ssh_obfuscated_port:
            config['ssh_obfuscated_port'] = int(server.ssh_obfuscated_port)
            config['ssh_obfuscated_key'] = server.ssh_obfuscated_key
        if server.alternate_ssh_obfuscated_ports and not (server.capabilities['FRONTED-MEEK'] or server.capabilities['UNFRONTED-MEEK']):
            config['ssh_obfuscated_port'] = int(server.alternate_ssh_obfuscated_ports[-1])
            config['ssh_obfuscated_key'] = server.ssh_obfuscated_key

        # Give client a set of regexes indicating which pages should have individual stats
        config['page_view_regexes'] = []
        for sponsor_regex in self._get_sponsor_page_view_regexes(sponsor_id):
            config['page_view_regexes'].append({
                                                'regex': sponsor_regex.regex,
                                                'replace': sponsor_regex.replace
                                                })

        config['https_request_regexes'] = []
        for sponsor_regex in self._get_sponsor_https_request_regexes(sponsor_id):
            config['https_request_regexes'].append({
                                                'regex': sponsor_regex.regex,
                                                'replace': sponsor_regex.replace
                                                })

        # If there are speed test URLs, select one at random and return it
        if self.__speed_test_urls:
            speed_test_url = random.choice(self.__speed_test_urls)
            config['speed_test_url'] = {
                'server_address': speed_test_url.server_address,
                # For backwards-compatibility reasons, this can't be cast to int
                'server_port': speed_test_url.server_port,
                'request_path': speed_test_url.request_path
            }

        return config

    def get_host_by_provider_id(self, provider_id):
        for host in self.__hosts.itervalues():
            if host.provider_id and host.provider_id == provider_id:
                return host

    def get_host_for_server(self, server):
        return self.__hosts[server.host_id]

    def get_hosts(self):
        return list(self.__hosts.itervalues())

    def get_servers(self):
        return list(self.__servers.itervalues())

    def get_propagation_channels(self):
        return list(self.__propagation_channels.itervalues())

    def get_sponsors(self):
        return list(self.__sponsors.itervalues())

    def __compartmentalize_data_for_host(self, host_id, is_TCS, discovery_date=datetime.datetime.now()):
        # Create a compartmentalized database with only the information needed by a particular host
        # - all propagation channels because any client may connect to servers on this host
        # - host data
        #   only region info is required for discovery
        # - servers data
        #   omit discovery servers not on this host whose discovery time period has elapsed
        #   also, omit propagation servers not on this host
        #   (not on this host --> because servers on this host still need to run, even if not discoverable)
        # - send home pages for all sponsors, but omit names, banners, campaigns
        # - send versions info for upgrades

        if is_TCS:
            return self.__compartmentalize_data_for_tcs(discovery_date)

        copy = PsiphonNetwork(initialize_plugins=False)

        for propagation_channel in self.__propagation_channels.itervalues():
            copy.__propagation_channels[propagation_channel.id] = PropagationChannel(
                                                                    propagation_channel.id,
                                                                    '',  # Omit name
                                                                    '',  # Omit mechanism type
                                                                    '',  # Omit propagator_managed_upgrades
                                                                    '',  # Omit new server counts
                                                                    '',  # Omit new server counts
                                                                    '',  # Omit new server counts
                                                                    '',  # Omit server ages
                                                                    '',  # Omit server ages
                                                                    '')  # Omit server ages

        for host in self.__hosts.itervalues():
            copy.__hosts[host.id] = Host(
                                        host.id,
                                        host.is_TCS,
                                        '',  # Omit: TCS_type isn't needed
                                        '',  # Omit: provider isn't needed
                                        '',  # Omit: provider_id isn't needed
                                        '',  # Omit: ip_address isn't needed
                                        '',  # Omit: ssh_port isn't needed
                                        '',  # Omit: root ssh_username isn't needed
                                        '',  # Omit: root ssh_password isn't needed
                                        '',  # Omit: ssh_host_key isn't needed
                                        '',  # Omit: stats_ssh_username isn't needed
                                        '',  # Omit: stats_ssh_password isn't needed
                                        '',  # Omit: datacenter_name isn't needed
                                        host.region,
                                        host.fronting_provider_id,
                                        None, # Omit: passthrough_address isn't needed
                                        host.meek_server_port,
                                        host.meek_server_obfuscated_key,
                                        host.meek_server_fronting_domain,
                                        host.meek_server_fronting_host,
                                        [],  # Omit: alternate_meek_server_fronting_hosts isn't needed
                                        host.meek_cookie_encryption_public_key,
                                        '',  # Omit: meek_cookie_encryption_private_key isn't needed
                                        host.tactics_request_public_key,
                                        '', # Omit: tactics_request_private_key isn't needed
                                        host.tactics_request_obfuscated_key,
                                        None # Omit: run_packet_manipulator isn't needed
                                        )

        for server in self.__servers.itervalues():
            if ((server.discovery_date_range and server.host_id != host_id and server.discovery_date_range[1] <= discovery_date) or
                (not server.discovery_date_range and server.host_id != host_id)):
                continue

            copy.__servers[server.id] = Server(
                                                server.id,
                                                server.host_id,
                                                server.ip_address,
                                                server.egress_ip_address,
                                                server.internal_ip_address,
                                                server.propagation_channel_id,
                                                server.is_embedded,
                                                server.is_permanent,
                                                server.discovery_date_range,
                                                server.capabilities,
                                                server.web_server_port,
                                                server.web_server_secret,
                                                server.web_server_certificate,
                                                server.web_server_private_key,
                                                server.ssh_port,
                                                server.ssh_username,
                                                server.ssh_password,
                                                server.ssh_host_key,
                                                None,
                                                server.ssh_obfuscated_port,
                                                server.ssh_obfuscated_quic_port,
                                                server.ssh_obfuscated_tapdance_port,
                                                server.ssh_obfuscated_conjure_port,
                                                server.ssh_obfuscated_key,
                                                server.alternate_ssh_obfuscated_ports,
                                                None,
                                                None,
                                                server.configuration_version)

        for sponsor in self.__sponsors.itervalues():
            sponsor_data = sponsor
            if sponsor.use_data_from_sponsor_id:
                sponsor_data = self.__sponsors[sponsor.use_data_from_sponsor_id]
            copy_sponsor = Sponsor(
                                sponsor.id,
                                '',  # Omit name
                                '',  # Omit banner
                                None,  # Omit website_banner
                                None,  # Omit website_banner_link
                                {},
                                {},
                                [],  # Omit campaigns
                                [],
                                [])
            for region, home_pages in sponsor_data.home_pages.iteritems():
                copy_sponsor.home_pages[region] = []
                for home_page in home_pages:
                    copy_sponsor.home_pages[region].append(SponsorHomePage(
                                                             home_page.region,
                                                             home_page.url))
            for region, mobile_home_pages in sponsor_data.mobile_home_pages.iteritems():
                copy_sponsor.mobile_home_pages[region] = []
                for mobile_home_page in mobile_home_pages:
                    copy_sponsor.mobile_home_pages[region].append(SponsorHomePage(
                                                             mobile_home_page.region,
                                                             mobile_home_page.url))
            for page_view_regex in sponsor_data.page_view_regexes:
                copy_sponsor.page_view_regexes.append(SponsorRegex(
                                                             page_view_regex.regex,
                                                             page_view_regex.replace))
            # global_https_request_regexes have top priority
            for https_request_regex in self.__global_https_request_regexes + sponsor_data.https_request_regexes:
                copy_sponsor.https_request_regexes.append(SponsorRegex(
                                                             https_request_regex.regex,
                                                             https_request_regex.replace))
            copy.__sponsors[copy_sponsor.id] = copy_sponsor

        for platform in self.__client_versions.iterkeys():
            for client_version in self.__client_versions[platform]:
                copy.__client_versions[platform].append(ClientVersion(
                                                client_version.version,
                                                ''))  # Omit description

        for speed_test_url in self.__speed_test_urls:
            copy.__speed_test_urls.append(
                SpeedTestURL(
                    speed_test_url.server_address,
                    speed_test_url.server_port,
                    speed_test_url.request_path))

        copy.__default_sponsor_id = self.__default_sponsor_id

        return jsonpickle.encode(copy)

    def __get_server_tag(self, server):
        return base64.b64encode(hmac.new(
            str(server.web_server_secret),
            msg=str(server.ip_address),
            digestmod=hashlib.sha256).digest())

    def __json_serializer(self, obj):
        # JSON serializer for datetime objects
        # to be consumed by psiphond
        if isinstance(obj, datetime.datetime):
            # psiphond json deserialization expects RFC 3339 format
            timestamp = obj.isoformat()
            if obj.tzinfo == None:
                timestamp += 'Z'
            return timestamp
        if isinstance(obj, set):
            return list(obj)
        else:
            # Handle psi_utils.recordtype() object
            # Host, Server, SponsorHomePage, ...
            return obj.todict()

    def __compartmentalize_data_for_tcs(self, discovery_date=datetime.datetime.now()):
        # Create a compartmentalized database for tunnel-core-server with only the information needed by a particular host
        # - all propagation channels because any client may connect to servers on this host
        # - host data
        #   only region info is required for discovery
        # - servers data
        #   only include discovery servers whose discovery time period has not elapsed
        #   NOTE that TCS only uses psinet for discovery. Unlike legacy servers,
        #   TCS does not require its own server records in psinet.
        # - send home pages for all sponsors, but omit names, banners, campaigns
        # - send versions info for upgrades

        copy = PsiphonNetwork(initialize_plugins=False)

        for propagation_channel in self.__propagation_channels.itervalues():
            copy.__propagation_channels[propagation_channel.id] = PropagationChannel(
                                                                    propagation_channel.id,
                                                                    '',  # Omit name
                                                                    '',  # Omit mechanism type
                                                                    '',  # Omit propagator_managed_upgrades
                                                                    '',  # Omit new server counts
                                                                    '',  # Omit new server counts
                                                                    '',  # Omit new server counts
                                                                    '',  # Omit server ages
                                                                    '',  # Omit server ages
                                                                    '')  # Omit server ages

        for sponsor in self.__sponsors.itervalues():
            sponsor_data = sponsor
            if sponsor.use_data_from_sponsor_id:
                sponsor_data = self.__sponsors[sponsor.use_data_from_sponsor_id]
            copy_sponsor = Sponsor(
                                sponsor.id,
                                '',  # Omit name
                                '',  # Omit banner
                                None,  # Omit website_banner
                                None,  # Omit website_banner_link
                                {},
                                {},
                                [],  # Omit campaigns
                                [],
                                [])
            for region, home_pages in sponsor_data.home_pages.iteritems():
                copy_sponsor.home_pages[region] = []
                for home_page in home_pages:
                    copy_sponsor.home_pages[region].append(SponsorHomePage(
                                                             home_page.region,
                                                             home_page.url))
            for region, mobile_home_pages in sponsor_data.mobile_home_pages.iteritems():
                copy_sponsor.mobile_home_pages[region] = []
                for mobile_home_page in mobile_home_pages:
                    copy_sponsor.mobile_home_pages[region].append(SponsorHomePage(
                                                             mobile_home_page.region,
                                                             mobile_home_page.url))
            for page_view_regex in sponsor_data.page_view_regexes:
                copy_sponsor.page_view_regexes.append(SponsorRegex(
                                                             page_view_regex.regex,
                                                             page_view_regex.replace))
            # global_https_request_regexes have top priority
            for https_request_regex in self.__global_https_request_regexes + sponsor_data.https_request_regexes:
                copy_sponsor.https_request_regexes.append(SponsorRegex(
                                                             https_request_regex.regex,
                                                             https_request_regex.replace))
            copy.__sponsors[copy_sponsor.id] = copy_sponsor.todict()

        for platform in self.__client_versions.iterkeys():
            for client_version in self.__client_versions[platform]:
                copy.__client_versions[platform].append(ClientVersion(
                                                client_version.version,
                                                ''))  # Omit description

        valid_server_entry_tags = {}
        for server in self.__servers.itervalues():
            tag = self.__get_server_tag(server)
            valid_server_entry_tags[tag] = True

        discovery_servers = []
        for server in self.__servers.itervalues():
            if server.discovery_date_range and server.discovery_date_range[1] > discovery_date:
                discovery_server = {
                    "discovery_date_range": [server.discovery_date_range[0], server.discovery_date_range[1]],
                    "encoded_server_entry": self.__get_encoded_server_entry(server)
                }
                discovery_servers.append(discovery_server)

        return json.dumps({
            "client_versions": copy.__client_versions,
            "valid_server_entry_tags": valid_server_entry_tags,
            "discovery_servers": discovery_servers,
            "sponsors": copy.__sponsors,
            "default_sponsor_id": self.__default_sponsor_id
        }, default=self.__json_serializer)

    def __get_own_encoded_server_entries_for_host(self, host_id):
        own_encoded_server_entries = {}
        for server in self.__servers.itervalues():
            if server.host_id == host_id:
                own_encoded_server_entries[self.__get_server_tag(server)] = self.__get_encoded_server_entry(server)
        return own_encoded_server_entries

    def __compartmentalize_data_for_devops_server(self):
        # The database is for DevOps and used by Nagios for testing and monitoring
        # DevOps people who needs to be able to connect to all hosts through SSH

        copy = PsiphonNetwork(initialize_plugins=False)

        for host in self.__hosts.itervalues():
            copy.__hosts[host.id] = Host(
                                            host.id,
                                            host.is_TCS,
                                            host.TCS_type,
                                            host.provider,
                                            host.provider_id,
                                            host.ip_address,
                                            host.ssh_port,
                                            host.ssh_username,
                                            host.ssh_password,
                                            host.ssh_host_key,
                                            host.stats_ssh_username,
                                            host.stats_ssh_password,
                                            host.datacenter_name,
                                            host.region,
                                            host.fronting_provider_id,
                                            host.passthrough_address,
                                            host.meek_server_port,
                                            host.meek_server_obfuscated_key,
                                            host.meek_server_fronting_domain,
                                            host.meek_server_fronting_host,
                                            host.alternate_meek_server_fronting_hosts,
                                            host.meek_cookie_encryption_public_key,
                                            '',  # Omit: meek_cookie_encryption_private_key
                                            '', '', '', # Omit: tactics fields
                                            host.run_packet_manipulator
                                            )
            copy.__hosts[host.id].logs = host.logs

        for server in self.__servers.itervalues():
            copy.__servers[server.id] = Server(
                                            server.id,
                                            server.host_id,
                                            server.ip_address,
                                            server.egress_ip_address,
                                            '',   # Omit: server.internal_ip_address,
                                            '',   # Omit: propagation_channel_id
                                            '',   # Omit: server.is_embedded,
                                            '',   # Omit: server.is_permanent,
                                            '',   # Omit: server.discovery_date_range,
                                            server.capabilities,
                                            server.web_server_port,
                                            server.web_server_secret,
                                            server.web_server_certificate,
                                            None, # Omit: server.web_server_private_key
                                            server.ssh_port,
                                            server.ssh_username,
                                            server.ssh_password,
                                            server.ssh_host_key,
                                            None, # Omit: server.TCS_ssh_private_key
                                            server.ssh_obfuscated_port,
                                            server.ssh_obfuscated_quic_port,
                                            server.ssh_obfuscated_tapdance_port,
                                            server.ssh_obfuscated_conjure_port,
                                            server.ssh_obfuscated_key,
                                            server.alternate_ssh_obfuscated_ports)
                                            # Omit: propagation, web server, ssh info, version
            copy.__servers[server.id].logs = server.logs

        for deleted_server in self.__deleted_servers.itervalues():
            copy.__deleted_servers[deleted_server.id] = Server(
                                            deleted_server.id,
                                            deleted_server.host_id,
                                            deleted_server.ip_address,
                                            None,
                                            '', # Omit: deleted_server.internal_ip_address,
                                            None,
                                            '', # Omit: deleted_server.is_embedded,
                                            '', # Omit: deleted_server.is_permanent,
                                            '', # Omit: deleted_server.discovery_date_range,
                                            deleted_server.capabilities)
                                            # Omit: propagation, web server, ssh info, version
            copy.__deleted_servers[deleted_server.id].logs = deleted_server.logs

        for propagation_channel in self.__propagation_channels.itervalues():
            copy.__propagation_channels[propagation_channel.id] = PropagationChannel(
                                        propagation_channel.id,
                                        propagation_channel.name,
                                        [],  # Omit mechanism info
                                        '',  # Omit propagator_managed_upgrades
                                        '',  # Omit new server counts
                                        '',  # Omit new server counts
                                        '',  # Omit new server counts
                                        '',  # Omit server ages
                                        '',  # Omit server ages
                                        '')  # Omit server ages

        for k,addresses in self.__alternate_meek_fronting_addresses.iteritems():
            for address in addresses:
                copy.__alternate_meek_fronting_addresses[k].add(address)

        for k,regex in self.__alternate_meek_fronting_addresses_regex.iteritems():
            copy.__alternate_meek_fronting_addresses_regex[k] = regex

        for k,v in self.__meek_fronting_disable_SNI.iteritems():
            copy.__meek_fronting_disable_SNI[k] = v

        copy.__routes_signing_public_key = self.__split_tunnel_signature_public_key()

        return jsonpickle.encode(copy)

    def __compartmentalize_data_for_stats_server(self):
        # The stats server needs to be able to connect to all hosts and needs
        # the information to replace server IPs with server IDs, sponsor IDs
        # with names and propagation IDs with names

        copy = PsiphonNetwork(initialize_plugins=False)

        for host in self.__hosts.itervalues():
            copy.__hosts[host.id] = Host(
                                            host.id,
                                            host.is_TCS,
                                            '',  # Omit: host.TCS_type,
                                            host.provider,
                                            '',  # Omit: provider id isn't needed
                                            host.ip_address,
                                            host.ssh_port,
                                            '',  # Omit: root ssh username
                                            '',  # Omit: root ssh password
                                            host.ssh_host_key,
                                            host.stats_ssh_username,
                                            host.stats_ssh_password,
                                            host.datacenter_name,
                                            host.region,
                                            None, # Omit: fronting_provider_id
                                            None, # Omit: passthrough_address
                                            host.meek_server_port,
                                            '',  # Omit: host.meek_server_obfuscated_key,
                                            '',  # Omit: host.meek_server_fronting_domain,
                                            '',  # Omit: host.meek_server_fronting_host,
                                            [],  # Omit: alternate_meek_server_fronting_hosts
                                            '',  # Omit: meek_cookie_encryption_public_key
                                            '',  # Omit: meek_cookie_encryption_private_key
                                            '', '', '', # Omit: tactics fields
                                            host.run_packet_manipulator
                                            )
            copy.__hosts[host.id].logs = host.logs

        for server in self.__servers.itervalues():
            copy.__servers[server.id] = Server(
                                            server.id,
                                            server.host_id,
                                            server.ip_address,
                                            None, # Omit: egress_ip_address
                                            '',   # Omit: server.internal_ip_address,
                                            None, # Omit: propagation_channel_id
                                            '',   # Omit: server.is_embedded,
                                            '',   # Omit: server.is_permanent,
                                            '',   # Omit: server.discovery_date_range,
                                            server.capabilities)
                                            # Omit: propagation, web server, ssh info, version
            copy.__servers[server.id].logs = server.logs

        for deleted_server in self.__deleted_servers.itervalues():
            copy.__deleted_servers[deleted_server.id] = Server(
                                            deleted_server.id,
                                            deleted_server.host_id,
                                            deleted_server.ip_address,
                                            None,
                                            '', # Omit: deleted_server.internal_ip_address,
                                            None,
                                            '', # Omit: deleted_server.is_embedded,
                                            '', # Omit: deleted_server.is_permanent,
                                            '', # Omit: deleted_server.discovery_date_range,
                                            deleted_server.capabilities)
                                            # Omit: propagation, web server, ssh info, version
            copy.__deleted_servers[deleted_server.id].logs = deleted_server.logs

        for propagation_channel in self.__propagation_channels.itervalues():
            copy.__propagation_channels[propagation_channel.id] = PropagationChannel(
                                        propagation_channel.id,
                                        propagation_channel.name,
                                        [],  # Omit mechanism info
                                        '',  # Omit propagator_managed_upgrades
                                        '',  # Omit new server counts
                                        '',  # Omit new server counts
                                        '',  # Omit new server counts
                                        '',  # Omit server ages
                                        '',  # Omit server ages
                                        '')  # Omit server ages

        for sponsor in self.__sponsors.itervalues():
            copy.__sponsors[sponsor.id] = Sponsor(
                                        sponsor.id,
                                        sponsor.name,
                                        '',     # omit banner
                                        None,   # omit website_banner
                                        None,   # omit website_banner_link
                                        {},     # omit home_pages
                                        {},     # omit mobile_home_pages
                                        sponsor.campaigns,
                                        [],     # omit page_view_regexes
                                        [])     # omit https_request_regexes

        return jsonpickle.encode(copy)

    def run_command_on_host(self, host, command):
        if type(host) == str:
            host = self.__hosts[host]
        ssh = psi_ssh.SSH(
                host.ip_address, host.ssh_port,
                host.ssh_username, host.ssh_password,
                host.ssh_host_key)
        ssh_output = ssh.exec_command(command)
        ssh.close()
        return ssh_output

    def run_command_on_hosts(self, command):

        @psi_ops_deploy.retry_decorator_returning_exception
        def do_run_command_on_host(host):
            self.run_command_on_host(host, command)

        psi_ops_deploy.run_in_parallel(20, do_run_command_on_host, self.__hosts.itervalues())

    def copy_file_from_host(self, host, remote_source_filename, local_destination_filename):
        ssh = psi_ssh.SSH(
                host.ip_address, host.ssh_port,
                host.ssh_username, host.ssh_password,
                host.ssh_host_key)

        ssh.get_file(remote_source_filename, local_destination_filename)

    def copy_file_to_host(self, host, source_filename, dest_filename):
        ssh = psi_ssh.SSH(
                host.ip_address, host.ssh_port,
                host.ssh_username, host.ssh_password,
                host.ssh_host_key)

        ssh.put_file(source_filename, dest_filename)

    def copy_file_to_hosts(self, source_filename, dest_filename):

        @psi_ops_deploy.retry_decorator_returning_exception
        def do_copy_file_to_host(host):
            self.copy_file_to_host(host, source_filename, dest_filename)

        psi_ops_deploy.run_in_parallel(50, do_copy_file_to_host, self.__hosts.itervalues())

    def swap_host_ip_address(self, host, new_ip_address):
        assert(self.is_locked)
        if type(host) == str:
            host = self.__hosts[host]
        server = [s for s in self.get_servers() if s.host_id == host.id][0]
        try:
            host.ip_address = new_ip_address
            server.ip_address = new_ip_address
            server.egress_ip_address = new_ip_address
            server.internal_ip_address = new_ip_address
            self.reinstall_host(host.id)
        except:
            pass

    def restore_deleted_host(self, host_id):
        assert(self.is_locked)
        try:
            deleted_host = [host for host in self.__deleted_hosts if host.id == host_id][0]
            deleted_server = [server for server in self.__deleted_servers.values() if server.host_id == host_id][0]

            # Add Restored log
            deleted_host.log('restored')
            deleted_server.log('restored')

            # Clean up old Deleted log
            for log in copy.copy(deleted_host.logs):
                if 'deleted' in log[1]:
                    deleted_host.logs.remove(log)
            for log in copy.copy(deleted_server.logs):
                if 'deleted' in log[1]:
                    deleted_server.logs.remove(log)

            self.__hosts[deleted_host.id] = deleted_host
            self.__deleted_hosts.remove(deleted_host)
            self.__servers[deleted_server.id] = self.__deleted_servers.pop(deleted_server.id)
        except:
            pass


    def __test_server(self, server, test_cases, version, test_propagation_channel_id, executable_path):

        return psi_ops_test_windows.test_server(
                                server,
                                self.__hosts[server.host_id],
                                self.__get_encoded_server_entry(server),
                                self.__split_tunnel_url_format(),
                                self.__split_tunnel_signature_public_key(),
                                self.__split_tunnel_dns_server(),
                                version,
                                [server.egress_ip_address],
                                test_propagation_channel_id,
                                test_cases,
                                executable_path)

    def __test_servers(self, servers, test_cases, build_with_embedded_servers=False):
        results = {}
        passes = 0
        failures = 0
        servers_with_errors = set()

        test_propagation_channel = None
        try:
            test_propagation_channel = self.get_propagation_channel_by_name('Testing')
        except:
            pass
        test_propagation_channel_id = test_propagation_channel.id if test_propagation_channel else '0'

        version = self.__client_versions[CLIENT_PLATFORM_WINDOWS][-1].version if self.__client_versions[CLIENT_PLATFORM_WINDOWS] else 0  # This uses the Windows client

        executable_path = None
        # We will need a build if no test_cases are specified (run all tests) or if at least one of the following are requested
        if ((not build_with_embedded_servers) and
            ((True in [server.capabilities['VPN'] for server in servers])
            and (not test_cases or set(test_cases).intersection(set(['VPN']))))):
            executable_path = psi_ops_build_windows.build_client(
                                    test_propagation_channel_id,
                                    '0',        # sponsor_id
                                    None,       # banner
                                    [],
                                    '',         # remote_server_list_signature_public_key
                                    ('','','','',''), # remote_server_list_url
                                    ('[{}]'), # remote_server_list_urls_json
                                    '', # OSL_root_url_split
                                    ('[{}]'), # OSL_root_urls_json
                                    None,       # server_entry_signature_public_key
                                    None,       # server_entry_exchange_obfuscation_key
                                    '',         # feedback_encryption_public_key
                                    '',         # feedback_upload_server
                                    '',         # feedback_upload_path
                                    '',         # feedback_upload_server_headers
                                    '',         # info_link_url
                                    '',         # upgrade_signature_public_key
                                    ('','','','',''), # upgrade_url
                                    ('[{}]'), #upgrade_urls_json
                                    '',         # get_new_version_url
                                    '',         # get_new_version_email
                                    '',         # faq_url
                                    '',         # privacy_policy_url
                                    self.__split_tunnel_url_format(),
                                    self.__split_tunnel_signature_public_key(),
                                    self.__split_tunnel_dns_server(),
                                    version,
                                    False,
                                    False)

        for server in servers:
            result = self.__test_server(server, test_cases, version, test_propagation_channel_id, executable_path)
            results[server.id] = result
            for test_result in result.itervalues():
                if 'FAIL' in test_result:
                    servers_with_errors.add(server.id)
                    break
        # One final pass to re-test servers that failed
        for server_id in servers_with_errors:
            server = self.__servers[server_id]
            result = self.__test_server(server, test_cases, version, test_propagation_channel_id, executable_path)
            results[server.id] = result
        # Process results
        servers_with_errors.clear()
        for server_id, result in results.iteritems():
            for test_result in result.itervalues():
                if 'FAIL' in test_result:
                    failures += 1
                    servers_with_errors.add(server_id)
                else:
                    passes += 1
            if server_id in servers_with_errors:
                pprint.pprint((server_id, result), stream=sys.stderr)
            else:
                pprint.pprint((server_id, result))
        sys.stderr.write('servers tested:      %d\n' % (len(servers),))
        sys.stderr.write('servers with errors: %d\n' % (len(servers_with_errors),))
        sys.stderr.write('tests passed:        %d\n' % (passes,))
        sys.stderr.write('tests failed:        %d\n' % (failures,))
        sys.stderr.write('SUCCESS\n' if failures == 0 else 'FAIL\n')
        assert(failures == 0)

    def test_server(self, server_id, test_cases=None, build_with_embedded_servers=False):
        if not server_id in self.__servers:
            print 'Server "%s" not found' % (server_id,)
        elif self.__servers[server_id].propagation_channel_id == None:
            print 'Server "%s" does not have a propagation channel id' % (server_id,)
        else:
            servers = [self.__servers[server_id]]
            self.__test_servers(servers, test_cases, build_with_embedded_servers)

    def test_host(self, host_id, test_cases=None):
        if not host_id in self.__hosts:
            print 'Host "%s" not found' % (host_id,)
        else:
            servers = [server for server in self.__servers.itervalues() if server.host_id == host_id and server.propagation_channel_id != None]
            self.__test_servers(servers, test_cases)

    def test_propagation_channel(self, propagation_channel_name, test_cases=None):
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        servers = [server for server in self.__servers.itervalues() if server.propagation_channel_id == propagation_channel.id]
        self.__test_servers(servers, test_cases)

    def test_sponsor(self, sponsor_name, test_cases=None):
        sponsor = self.get_sponsor_by_name(sponsor_name)
        propagation_channel_ids = set()
        for campaign in sponsor.campaigns:
            propagation_channel_ids.add(campaign.propagation_channel_id)
        servers = [server for server in self.__servers.itervalues()
                   if server.propagation_channel_id in propagation_channel_ids]
        self.__test_servers(servers, test_cases)

    def test_servers(self, test_cases=None):
        servers = [server for server in self.__servers.itervalues() if server.propagation_channel_id != None]
        self.__test_servers(servers, test_cases)

    def server_distribution(self):
        users_on_host = {}
        total_users = 0
        for host in self.get_hosts():
            user_count = self.__count_users_on_host(host.id)
            total_users += user_count
            users_on_host[host.id] = user_count
        sorted_users_on_host = sorted(users_on_host.iteritems(), key=operator.itemgetter(1))
        print 'Total users: %d\n' % (total_users,)
        for host_user_count in sorted_users_on_host:
            print host_user_count[1]

    def save(self):
        assert(self.is_locked)
        print 'saving...'
        super(PsiphonNetwork, self).save()


def unit_test():
    psinet = PsiphonNetwork()
    psinet.add_propagation_channel('email-channel', ['email-autoresponder'])
    psinet.add_sponsor('sponsor1')
    psinet.set_sponsor_home_page('sponsor1', 'CA', 'http://psiphon.ca')
    psinet.add_sponsor_email_campaign('sponsor1', 'email-channel', 'get@psiphon.ca')
    psinet.set_sponsor_page_view_regex('sponsor1', r'^http://psiphon\.ca', r'$&')
    psinet.set_sponsor_page_view_regex('sponsor1', r'^http://psiphon\.ca/', r'$&')
    psinet.remove_sponsor_page_view_regex('sponsor1', r'^http://psiphon\.ca/')
    psinet.set_sponsor_https_request_regex('sponsor1', r'^http://psiphon\.ca', r'$&')
    psinet.set_sponsor_https_request_regex('sponsor1', r'^http://psiphon\.ca/', r'$&')
    psinet.remove_sponsor_https_request_regex('sponsor1', r'^http://psiphon\.ca/')
    psinet.show_status(verbose=True)


def create():
    # Create a new network object and persist it
    psinet = PsiphonNetwork()
    psinet.is_locked = True
    psinet.save()
    psinet.release()


def interact(lock):
    # Load an existing network object, interact with it, then save changes
    print 'loading...'
    psinet = PsiphonNetwork.load(lock)
    psinet.show_status()
    import code
    try:
        code.interact(
                'Psiphon 3 Console\n' +
                '-----------------\n' +
                ('%s mode\n' % ('EDIT' if lock else 'READ-ONLY',)) +
                'Interact with the \'psinet\' object...\n',
                local=locals())
    except SystemExit as e:
        if lock:
            psinet.release()
        raise


def edit():
    interact(lock=True)


def view():
    interact(lock=False)


def test(tests):
    psinet = PsiphonNetwork.load(lock=False)
    psinet.show_status()
    psinet.test_servers(tests)


def update_external_signed_routes():
    psinet = PsiphonNetwork.load(lock=False)
    psinet.update_external_signed_routes()


def prune_all_propagation_channels():
    psinet = PsiphonNetwork.load(lock=True)
    psinet.show_status()
    try:
        propagation_channels = psinet._PsiphonNetwork__propagation_channels.values()
        for propagation_channel in propagation_channels:
            number_removed, number_disabled = psinet.prune_propagation_channel_servers(propagation_channel.name)
            sys.stderr.write('Pruned %d servers from %s\n' % (number_removed, propagation_channel.name))
            sys.stderr.write('Disabled %d servers from %s\n' % (number_disabled, propagation_channel.name))
        # NEW: deploy() is called by another process
        #psinet.deploy()
    finally:
        # Attempt to update the stats db immediately if required
        try:
            psinet.deploy_stats_config_if_required()
        except:
            pass
        psinet.show_status()
        psinet.release()


def replace_propagation_channel_servers(propagation_channel_name):
    psinet = PsiphonNetwork.load(lock=True)
    psinet.show_status()
    try:
        psinet.replace_propagation_channel_servers(propagation_channel_name)
    finally:
        psinet.show_status()
        psinet.release()


def run_deploy():
    psinet = PsiphonNetwork.load(lock=True)
    psinet.show_status()
    try:
        psinet.deploy()
    finally:
        psinet.show_status()
        psinet.release()


def find_orphans():
    psinet = PsiphonNetwork.load(lock=False)
    psinet.find_orphans()


if __name__ == "__main__":
    parser = optparse.OptionParser('usage: %prog [options]')
    parser.add_option("-r", "--read-only", dest="readonly", action="store_true",
                      help="don't lock the network object")
    parser.add_option("-t", "--test", dest="test", action="append",
                      choices=('handshake', 'VPN', 'OSSH', 'SSH', 'FRONTED-MEEK-OSSH', 'FRONTED-MEEK-HTTP-OSSH', 'UNFRONTED-MEEK-OSSH', 'UNFRONTED-MEEK-HTTPS-OSSH', 'UNFRONTED-MEEK-SESSION-TICKET-OSSH', 'QUIC-OSSH', 'FRONTED-MEEK-QUIC-OSSH'),
                      help="specify once for each of: handshake, VPN, OSSH, SSH, FRONTED-MEEK-OSSH, FRONTED-MEEK-HTTP-OSSH, UNFRONTED-MEEK-OSSH, UNFRONTED-MEEK-HTTPS-OSSH, UNFRONTED-MEEK-SESSION-TICKET-OSSH, QUIC-OSSH, FRONTED-MEEK-QUIC-OSSH")
    parser.add_option("-u", "--update-routes", dest="updateroutes", action="store_true",
                      help="update external signed routes files")
    parser.add_option("-d", "--deploy", dest="deploy", action="store_true",
                      help="run deploy")
    parser.add_option("-p", "--prune", dest="prune", action="store_true",
                      help="prune all propagation channels")
    parser.add_option("-n", "--new-servers", dest="channel", action="store", type="string",
                      help="create new servers for this propagation channel")
    parser.add_option("-o", "--orphans", dest="orphans", action="store_true",
                      help="find VPSes that are not in psinet")
    (options, _) = parser.parse_args()
    if options.orphans:
        find_orphans()
    elif options.channel:
        replace_propagation_channel_servers(options.channel)
    elif options.prune:
        prune_all_propagation_channels()
    elif options.deploy:
        run_deploy()
    elif options.updateroutes:
        update_external_signed_routes()
    elif options.test:
        test(options.test)
    elif options.readonly:
        view()
    else:
        edit()
