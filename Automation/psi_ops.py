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

import sys
import os
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
from pkg_resources import parse_version

import psi_utils
import psi_ops_cms
import psi_ops_discovery

# Modules available only on the automation server

try:
    import psi_ops_crypto_tools
except ImportError as error:
    print error

try:
    import psi_ssh
except ImportError as error:
    print error

try:
    import psi_linode
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

# NOTE: update compartmentalize() functions when adding fields

PropagationChannel = psi_utils.recordtype(
    'PropagationChannel',
    'id, name, propagation_mechanism_types, ' +
    'new_discovery_servers_count, new_propagation_servers_count, ' +
    'max_discovery_server_age_in_days, max_propagation_server_age_in_days')

PropagationMechanism = psi_utils.recordtype(
    'PropagationMechanism',
    'type')

TwitterPropagationAccount = psi_utils.recordtype(
    'TwitterPropagationAccount',
    'name, consumer_key, consumer_secret, access_token_key, access_token_secret')

EmailPropagationAccount = psi_utils.recordtype(
    'EmailPropagationAccount',
    'email_address')

Sponsor = psi_utils.recordtype(
    'Sponsor',
    'id, name, banner, home_pages, campaigns, page_view_regexes, https_request_regexes')

SponsorHomePage = psi_utils.recordtype(
    'SponsorHomePage',
    'region, url')

SponsorCampaign = psi_utils.recordtype(
    'SponsorCampaign',
    'propagation_channel_id, propagation_mechanism_type, account, s3_bucket_name, languages, custom_download_site')

SponsorRegex = psi_utils.recordtype(
    'SponsorRegex',
    'regex, replace')

Host = psi_utils.recordtype(
    'Host',
    'id, provider, provider_id, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key, ' +
    'stats_ssh_username, stats_ssh_password, ' +
    'datacenter_name',
    default=None)

Server = psi_utils.recordtype(
    'Server',
    'id, host_id, ip_address, egress_ip_address, internal_ip_address, ' +
    'propagation_channel_id, is_embedded, is_permanent, discovery_date_range, capabilities, ' +
    'web_server_port, web_server_secret, web_server_certificate, web_server_private_key, ' +
    'ssh_port, ssh_username, ssh_password, ssh_host_key, ssh_obfuscated_port, ssh_obfuscated_key',
    default=None)


def ServerCapabilities():
    capabilities = {}
    for capability in ('handshake', 'VPN', 'SSH', 'OSSH'):
        capabilities[capability] = True
    return capabilities


def copy_server_capabilities(caps):
    capabilities = {}
    for capability in ('handshake', 'VPN', 'SSH', 'OSSH'):
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
ProviderRank.provider_values = ('linode', 'elastichosts')

LinodeAccount = psi_utils.recordtype(
    'LinodeAccount',
    'api_key, base_id, base_ip_address, base_ssh_port, ' +
    'base_root_password, base_stats_username, base_host_public_key, ' +
    'base_known_hosts_entry, base_rsa_private_key, base_rsa_public_key, ' +
    'base_tarball_path',
    default=None)

ElasticHostsAccount = psi_utils.recordtype(
    'ElasticHostsAccount',
    'zone, uuid, api_key, base_drive_id, cpu, mem, base_host_public_key, ' +
    'root_username, base_root_password, base_ssh_port, stats_username, rank',
    default=None)
ElasticHostsAccount.zone_values = ('ELASTICHOSTS_US1',  # sat-p
                                   'ELASTICHOSTS_UK1',  # lon-p
                                   'ELASTICHOSTS_UK2')  # lon-b

EmailServerAccount = psi_utils.recordtype(
    'EmailServerAccount',
    'ip_address, ssh_port, ssh_username, ssh_pkey, ssh_host_key, ' +
    'config_file_path',
    default=None)

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

CLIENT_PLATFORM_WINDOWS = 'Windows'
CLIENT_PLATFORM_ANDROID = 'Android'


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
        self.__client_versions = {
            CLIENT_PLATFORM_WINDOWS: [],
            CLIENT_PLATFORM_ANDROID: []
        }
        self.__email_server_account = EmailServerAccount()
        self.__stats_server_account = StatsServerAccount()
        self.__aws_account = AwsAccount()
        self.__provider_ranks = []
        self.__linode_account = LinodeAccount()
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
        self.__upgrade_package_signing_key_pair = None
        if initialize_plugins:
            self.initialize_plugins()

    class_version = '0.17'

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
            Hosts:                  %d
            Servers:                %d
            Email Server:           %s
            Stats Server:           %s
            Windows Client Version: %s %s
            Android Client Version: %s %s
            AWS Account:            %s
            Provider Ranks:         %s
            Linode Account:         %s
            ElasticHosts Account:   %s
            Deploys Pending:        Host Implementations    %d
                                    Host Data               %s
                                    Windows Campaign Builds %d
                                    Android Campaign Builds %d
                                    Stats Server Config     %s
                                    Email Server Config     %s
            ''') % (
                len(self.__sponsors),
                len(self.__propagation_channels),
                sum([len(filter(lambda x:x.propagation_mechanism_type == 'twitter', sponsor.campaigns))
                     for sponsor in self.__sponsors.itervalues()]),
                sum([len(filter(lambda x:x.propagation_mechanism_type == 'email-autoresponder', sponsor.campaigns))
                     for sponsor in self.__sponsors.itervalues()]),
                sum([len(sponsor.campaigns)
                     for sponsor in self.__sponsors.itervalues()]),
                len(self.__hosts),
                len(self.__servers),
                self.__email_server_account.ip_address if self.__email_server_account else 'None',
                self.__stats_server_account.ip_address if self.__stats_server_account else 'None',
                self.__client_versions[CLIENT_PLATFORM_WINDOWS][-1].version if self.__client_versions[CLIENT_PLATFORM_WINDOWS] else 'None',
                self.__client_versions[CLIENT_PLATFORM_WINDOWS][-1].description if self.__client_versions[CLIENT_PLATFORM_WINDOWS] else '',
                self.__client_versions[CLIENT_PLATFORM_ANDROID][-1].version if self.__client_versions[CLIENT_PLATFORM_ANDROID] else 'None',
                self.__client_versions[CLIENT_PLATFORM_ANDROID][-1].description if self.__client_versions[CLIENT_PLATFORM_ANDROID] else '',
                'Configured' if self.__aws_account.access_id else 'None',
                'Configured' if self.__provider_ranks else 'None',
                'Configured' if self.__linode_account.api_key else 'None',
                'Configured' if self.__elastichosts_accounts else 'None',
                len(self.__deploy_implementation_required_for_hosts),
                'Yes' if self.__deploy_data_required_for_all else 'No',
                len(self.__deploy_builds_required_for_campaigns[CLIENT_PLATFORM_WINDOWS]),
                len(self.__deploy_builds_required_for_campaigns[CLIENT_PLATFORM_ANDROID]),
                'Yes' if self.__deploy_stats_config_required else 'No',
                'Yes' if self.__deploy_email_config_required else 'No')

    def __show_logs(self, obj):
        for timestamp, message in obj.get_logs():
            print '%s: %s' % (timestamp.isoformat(), message)
        print ''

    def show_sponsors(self):
        for s in self.__sponsors.itervalues():
            self.show_sponsor(s.name)

    def show_sponsor(self, sponsor_name):
        s = self.__get_sponsor_by_name(sponsor_name)
        print textwrap.dedent('''
            ID:                      %(id)s
            Name:                    %(name)s
            Home Pages:              %(home_pages)s
            Page View Regexes:       %(page_view_regexes)s
            HTTPS Request Regexes:   %(https_request_regexes)s
            Campaigns:               %(campaigns)s
            ''') % {
                    'id': s.id,
                    'name': s.name,
                    'home_pages': '\n                         '.join(['%s: %s' % (region.ljust(5) if region else 'All',
                                                         '\n                                '.join([h.url for h in home_pages]))
                                                         for region, home_pages in sorted(s.home_pages.items())]),
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
            ID:                                %s
            Name:                              %s
            Propagation Mechanisms:            %s
            New Propagation Servers:           %s
            Max Propagation Server Age (days): %s
            New Discovery Servers:             %s
            Max Discovery Server Age (days):   %s
            ''') % (
                p.id,
                p.name,
                '\n                                   '.join(p.propagation_mechanism_types),
                str(p.new_propagation_servers_count),
                str(p.max_propagation_server_age_in_days),
                str(p.new_discovery_servers_count),
                str(p.max_discovery_server_age_in_days))

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
            Server:                  %s
            Host:                    %s %s %s/%s
            IP Address:              %s
            Propagation Channel:     %s
            Is Embedded:             %s
            Is Permanent:            %s
            Discovery Date Range:    %s
            ''') % (
                s.id,
                s.host_id,
                self.__hosts[s.host_id].ip_address,
                self.__hosts[s.host_id].ssh_username,
                self.__hosts[s.host_id].ssh_password,
                s.ip_address,
                self.__propagation_channels[s.propagation_channel_id].name if s.propagation_channel_id else 'None',
                s.is_embedded,
                s.is_permanent,
                ('%s - %s' % (s.discovery_date_range[0].isoformat(),
                            s.discovery_date_range[1].isoformat())) if s.discovery_date_range else 'None')
        self.__show_logs(s)

    def show_host(self, host_id, show_logs=False):
        host = self.__hosts[host_id]
        servers = [self.__servers[s].id + (' (permanent)' if self.__servers[s].is_permanent else '')
                   for s in self.__servers
                   if self.__servers[s].host_id == host_id]

        print textwrap.dedent('''
            Host ID:                 %(id)s
            Provider:                %(provider)s (%(provider_id)s)
            Datacenter:              %(datacenter_name)s
            IP Address:              %(ip_address)s
            SSH:                     %(ssh_port)s %(ssh_username)s / %(ssh_password)s
            Stats User:              %(stats_ssh_username)s / %(stats_ssh_password)s
            Servers:                 %(servers)s
            ''') % {
                    'id': host.id,
                    'provider': host.provider,
                    'provider_id': host.provider_id,
                    'datacenter_name': host.datacenter_name,
                    'ip_address': host.ip_address,
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
        return filter(lambda x: x.name == name,
                      self.__propagation_channels.itervalues())[0]

    def get_propagation_channel_by_id(self, id):
        return self.__propagation_channels[id] if id in self.__propagation_channels else None

    def add_propagation_channel(self, name, propagation_mechanism_types):
        assert(self.is_locked)
        self.import_propagation_channel(self.__generate_id(), name, propagation_mechanism_types)

    def import_propagation_channel(self, id, name, propagation_mechanism_types):
        assert(self.is_locked)
        for type in propagation_mechanism_types:
            assert(type in self.__propagation_mechanisms)
        propagation_channel = PropagationChannel(id, name, propagation_mechanism_types, 0, 0, 0, 0)
        assert(id not in self.__propagation_channels)
        assert(not filter(lambda x: x.name == name, self.__propagation_channels.itervalues()))
        self.__propagation_channels[id] = propagation_channel

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

    def __get_sponsor_by_name(self, name):
        return filter(lambda x: x.name == name,
                      self.__sponsors.itervalues())[0]

    def get_sponsor_by_id(self, id):
        return self.__sponsors[id] if id in self.__sponsors else None

    def add_sponsor(self, name):
        assert(self.is_locked)
        self.import_sponsor(self.__generate_id(), name)

    def import_sponsor(self, id, name):
        assert(self.is_locked)
        sponsor = Sponsor(id, name, None, {}, [], [], [])
        assert(id not in self.__sponsors)
        assert(not filter(lambda x: x.name == name, self.__sponsors.itervalues()))
        self.__sponsors[id] = sponsor

    def set_sponsor_banner(self, name, banner_filename):
        assert(self.is_locked)
        with open(banner_filename, 'rb') as file:
            banner = base64.b64encode(file.read())
        sponsor = self.__get_sponsor_by_name(name)
        sponsor.banner = banner
        sponsor.log('set banner')
        for campaign in sponsor.campaigns:
            for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                self.__deploy_builds_required_for_campaigns[platform].add(
                    (campaign.propagation_channel_id, sponsor.id))
            campaign.log('marked for build and publish (new banner)')

    def add_sponsor_email_campaign(self, sponsor_name, propagation_channel_name, email_account):
        assert(self.is_locked)
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_mechanism_type = 'email-autoresponder'
        assert(propagation_mechanism_type in propagation_channel.propagation_mechanism_types)
        # TODO: assert(email_account not in ...)
        campaign = SponsorCampaign(propagation_channel.id,
                                   propagation_mechanism_type,
                                   EmailPropagationAccount(email_account),
                                   None,
                                   None,
                                   False)
        if campaign not in sponsor.campaigns:
            sponsor.campaigns.append(campaign)
            sponsor.log('add email campaign %s' % (email_account,))
            for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                self.__deploy_builds_required_for_campaigns[platform].add(
                        (campaign.propagation_channel_id, sponsor.id))
            campaign.log('marked for build and publish (new campaign)')

    def add_sponsor_twitter_campaign(self, sponsor_name,
                                     propagation_channel_name,
                                     twitter_account_name,
                                     twitter_account_consumer_key,
                                     twitter_account_consumer_secret,
                                     twitter_account_access_token_key,
                                     twitter_account_access_token_secret):
        assert(self.is_locked)
        sponsor = self.__get_sponsor_by_name(sponsor_name)
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
                                   False)
        if campaign not in sponsor.campaigns:
            sponsor.campaigns.append(campaign)
            sponsor.log('add twitter campaign %s' % (twitter_account_name,))
            for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                self.__deploy_builds_required_for_campaigns[platform].add(
                        (campaign.propagation_channel_id, sponsor.id))
            campaign.log('marked for build and publish (new campaign)')

    def add_sponsor_static_download_campaign(self, sponsor_name, propagation_channel_name):
        assert(self.is_locked)
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        propagation_mechanism_type = 'static-download'
        assert(propagation_mechanism_type in propagation_channel.propagation_mechanism_types)
        campaign = SponsorCampaign(propagation_channel.id,
                                   propagation_mechanism_type,
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
            campaign.log('marked for build and publish (new campaign)')

    def set_sponsor_campaign_s3_bucket_name(self, sponsor_name, propagation_channel_name, account, s3_bucket_name):
        assert(self.is_locked)
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        for campaign in sponsor.campaigns:
            if (campaign.propagation_channel_id == propagation_channel.id and
                campaign.account[0] == account):
                    campaign.s3_bucket_name = s3_bucket_name
                    campaign.log('set campaign s3 bucket name to %s' % (s3_bucket_name,))
                    for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
                        self.__deploy_builds_required_for_campaigns[platform].add(
                            (campaign.propagation_channel_id, sponsor.id))
                    campaign.log('marked for build and publish (modified campaign)')

    def set_sponsor_home_page(self, sponsor_name, region, url):
        assert(self.is_locked)
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        home_page = SponsorHomePage(region, url)
        if region not in sponsor.home_pages:
            sponsor.home_pages[region] = []
        if home_page not in sponsor.home_pages[region]:
            sponsor.home_pages[region].append(home_page)
            sponsor.log('set home page %s for %s' % (url, region if region else 'All'))
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def remove_sponsor_home_page(self, sponsor_name, region, url):
        assert(self.is_locked)
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        home_page = SponsorHomePage(region, url)
        if (region in sponsor.home_pages
            and home_page in sponsor.home_pages[region]):
            sponsor.home_pages[region].remove(home_page)
            sponsor.log('deleted home page %s for %s' % (url, region))
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def set_sponsor_page_view_regex(self, sponsor_name, regex, replace):
        assert(self.is_locked)
        sponsor = self.__get_sponsor_by_name(sponsor_name)
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
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        match = [sponsor.page_view_regexes.pop(idx)
                 for (idx, rx)
                 in enumerate(sponsor.page_view_regexes)
                 if rx.regex == regex]
        if match:
            sponsor.page_view_regexes.remove(regex)
            sponsor.log('deleted page view regex %s' % regex)
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def set_sponsor_https_request_regex(self, sponsor_name, regex, replace):
        assert(self.is_locked)
        sponsor = self.__get_sponsor_by_name(sponsor_name)
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
        sponsor = self.__get_sponsor_by_name(sponsor_name)
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
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        sponsor.name = (new_sponsor_name)
        self.__deploy_stats_config_required = True
        sponsor.log('set sponsor name from \'%s\' to \'%s\'' % (sponsor_name, new_sponsor_name))

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

    def import_host(self, id, provider, provider_id, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key,
                    stats_ssh_username, stats_ssh_password):
        assert(self.is_locked)
        host = Host(
                id,
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
                    ssh_host_key)

        assert(server.id not in self.__servers)
        self.__servers[server.id] = server

    def __disable_server(self, server):
        assert(self.is_locked)
        # Prevent users from establishing new connections to this server,
        # while allowing existing connections to be maintained.
        server.capabilities['handshake'] = False
        server.capabilities['SSH'] = False
        server.capabilities['OSSH'] = False
        host = self.__hosts[server.host_id]
        servers = [s for s in self.__servers.itervalues() if s.host_id == server.host_id]
        psi_ops_install.install_firewall_rules(host, servers, plugins)
        self.save()

    def __count_users_on_host(self, host_id):
        vpn_users = int(self.run_command_on_host(self.__hosts[host_id],
                                                 'ifconfig | grep ppp | wc -l'))
        ssh_users = int(self.run_command_on_host(self.__hosts[host_id],
                                                 'ps ax | grep ssh | grep psiphon | wc -l')) / 2
        return vpn_users + ssh_users

    def __upgrade_host_datacenter_names(self):
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
            if users_on_host == 0:
                self.remove_host(server.host_id)
                number_removed += 1
            elif users_on_host < 10:
                self.__disable_server(server)
                number_disabled += 1
        return number_removed, number_disabled

    def prune_propagation_channel_servers(self, propagation_channel_name,
                                          max_discovery_server_age_in_days=None,
                                          max_propagation_server_age_in_days=None):
        assert(self.is_locked)

        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        now = datetime.datetime.now()
        today = datetime.datetime(now.year, now.month, now.day)

        # Remove old servers with low activity
        number_removed = 0
        number_disabled = 0

        if max_discovery_server_age_in_days == None:
            max_discovery_server_age_in_days = propagation_channel.max_discovery_server_age_in_days
        if max_discovery_server_age_in_days > 0:
            old_discovery_servers = [server for server in self.__servers.itervalues()
                if server.propagation_channel_id == propagation_channel.id
                and server.discovery_date_range
                and server.discovery_date_range[1] < (today - datetime.timedelta(days=max_discovery_server_age_in_days))
                and self.__hosts[server.host_id].provider == 'linode']
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
                and self.__hosts[server.host_id].provider == 'linode']
            removed, disabled = self.__prune_servers(old_propagation_servers)
            number_removed += removed
            number_disabled += disabled

        # This deploy will update the stats server, so it doesn't try to pull stats from
        # hosts that no longer exist
        self.deploy()

        return number_removed, number_disabled

    def replace_propagation_channel_servers(self, propagation_channel_name,
                                            new_discovery_servers_count=None,
                                            new_propagation_servers_count=None):
        assert(self.is_locked)

        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        now = datetime.datetime.now()
        today = datetime.datetime(now.year, now.month, now.day)

        # Use a default 2 week discovery date range.
        new_discovery_date_range = (today, today + datetime.timedelta(weeks=2))

        if new_discovery_servers_count == None:
            new_discovery_servers_count = propagation_channel.new_discovery_servers_count
        if new_discovery_servers_count > 0:
            self.add_servers(new_discovery_servers_count, propagation_channel_name, new_discovery_date_range)

        if new_propagation_servers_count == None:
            new_propagation_servers_count = propagation_channel.new_propagation_servers_count
        if new_propagation_servers_count > 0:
            self.add_servers(new_propagation_servers_count, propagation_channel_name, None)

    def get_existing_server_ids(self):
        return [server.id for server in self.__servers.itervalues()] + \
               [deleted_server.id for deleted_server in self.__deleted_servers.itervalues()]

    def add_server_to_host(self, host, new_servers):
        
        existing_servers = [server for server in self.get_servers() if server.host_id == host.id]
        servers_on_host = existing_servers + new_servers
        
        psi_ops_install.install_host(host, servers_on_host, self.get_existing_server_ids(), plugins)
        host.log('install with new servers')
        
        assert(host.id in self.__hosts)
        
        for server in new_servers:
            assert(server.id not in self.__servers)
            self.__servers[server.id] = server
            
        psi_ops_deploy.deploy_data(
                            host,
                            self.__compartmentalize_data_for_host(host.id))

        for server in servers_on_host:
            self.test_server(server.id, ['handshake'])
            
    def setup_server(self, host, servers):
        # Install Psiphon 3 and generate configuration values
        # Here, we're assuming one server/IP address per host
        psi_ops_install.install_host(host, servers, self.get_existing_server_ids(), plugins)
        host.log('install')

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

        # Deploy will upload web server source database data and client builds
        # (Only deploying for the new host, not broadcasting info yet...)
        psi_ops_deploy.deploy_implementation(host, plugins)
        psi_ops_deploy.deploy_data(
                            host,
                            self.__compartmentalize_data_for_host(host.id))
        psi_ops_deploy.deploy_geoip_database_autoupdates(host)
        psi_ops_deploy.deploy_routes(host)
        host.log('initial deployment')

        for server in servers:
            self.test_server(server.id, ['handshake'])

    def add_servers(self, count, propagation_channel_name, discovery_date_range, replace_others=True, server_capabilities=None):
        assert(self.is_locked)
        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)

        # Embedded servers (aka "propagation servers") are embedded in client
        # builds, where as discovery servers are only revealed when clients
        # connect to a server.
        is_embedded_server = (discovery_date_range is None)

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
            else:
                self.__replace_propagation_channel_discovery_servers(propagation_channel.id)

        for new_server_number in range(count):
            provider = self._weighted_random_choice(self.__provider_ranks).provider

            # This is pretty dirty. We should use some proper OO technique.
            provider_launch_new_server = None
            provider_account = None
            if provider.lower() == 'linode':
                provider_launch_new_server = psi_linode.launch_new_server
                provider_account = self.__linode_account
            elif provider.lower() == 'elastichosts':
                provider_launch_new_server = psi_elastichosts.ElasticHosts().launch_new_server
                provider_account = self._weighted_random_choice(self.__elastichosts_accounts)
            else:
                raise ValueError('bad provider value: %s' % provider)

            print 'starting %s process (up to 20 minutes)...' % provider

            # Create a new cloud VPS
            def provider_launch_new_server_with_retries():
                for _ in range(3):
                    try:
                        return provider_launch_new_server(provider_account, plugins)
                    except Exception as ex:
                        print str(ex)
                        pass
                raise ex

            server_info = provider_launch_new_server_with_retries()
            host = Host(*server_info)
            host.provider = provider.lower()

            # NOTE: jsonpickle will serialize references to discovery_date_range, which can't be
            # resolved when unpickling, if discovery_date_range is used directly.
            # So create a copy instead.
            discovery = self.__copy_date_range(discovery_date_range) if discovery_date_range else None

            ssh_port = '22'
            ossh_port = random.choice(['465', '587', '993', '995'])
            capabilities = ServerCapabilities()
            if server_capabilities:
                capabilities = copy_server_capabilities(server_capabilities)
            elif new_server_number % 2 == 1:
                # We would like every other new server created to be somewhat obfuscated
                capabilities['handshake'] = False
                capabilities['VPN'] = False
                capabilities['SSH'] = False
                ssh_port = None
                ossh_ports = range(1,1023)
                ossh_ports.remove(15)
                ossh_ports.remove(135)
                ossh_ports.remove(136)
                ossh_ports.remove(137)
                ossh_ports.remove(138)
                ossh_ports.remove(139)
                ossh_ports.remove(515)
                ossh_port = random.choice(ossh_ports)

            server = Server(
                        None,
                        host.id,
                        host.ip_address,
                        host.ip_address,
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
                        ossh_port)

            self.setup_server(host, [server])

            self.save()

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
                        campaign.log('marked for build and publish (new embedded server)')

        # Ensure new server configuration is saved to CMS before deploying new
        # server info to the network

        # TODO: add need-save flag
        self.save()

        # This deploy will broadcast server info, propagate builds, and update
        # the stats and email server
        self.deploy()

    def remove_host(self, host_id):
        assert(self.is_locked)
        host = self.__hosts[host_id]
        if host.provider == 'linode':
            provider_remove_host = psi_linode.remove_server
            provider_account = self.__linode_account
        else:
            raise ValueError('can\'t remove host from provider %s' % host.provider)

        # Remove the actual host through the provider's API
        provider_remove_host(provider_account, host.provider_id)

        # Mark host and its servers as delete in the database. We keep the
        # records around for historical info and to ensure we never recycle
        # server IDs
        server_ids_on_host = []
        for server in self.__servers.itervalues():
            if server.host_id == host.id:
                server_ids_on_host.append(server.id)
        for server_id in server_ids_on_host:
            assert(server_id not in self.__deleted_servers)
            self.__deleted_servers[server_id] = self.__servers.pop(server_id)
        # We don't assign host IDs and can't guarentee uniqueness, so not
        # archiving deleted host keyed by ID.
        self.__deleted_hosts.append(self.__hosts.pop(host.id))

        # Clear flags that include this host id.  Update stats config.
        if host.id in self.__deploy_implementation_required_for_hosts:
            self.__deploy_implementation_required_for_hosts.remove(host.id)
        self.__deploy_stats_config_required = True
        # NOTE: If host was currently discoverable or will be in the future,
        #       host data should be updated.
        # NOTE: If host was currently embedded, new campaign builds are needed.

        self.save()

    def reinstall_host(self, host_id):
        assert(self.is_locked)
        host = self.__hosts[host_id]
        servers = [server for server in self.__servers.itervalues() if server.host_id == host_id]
        psi_ops_install.install_host(host, servers, self.get_existing_server_ids(), plugins)
        psi_ops_deploy.deploy_implementation(host, plugins)
        # New data might have been generated
        # NOTE that if the client version has been incremented but a full deploy has not yet been run,
        # this following psi_ops_deploy.deploy_data call is not safe.  Data will specify a new version
        # that is not yet available on servers (infinite download loop).
        psi_ops_deploy.deploy_data(
                                host,
                                self.__compartmentalize_data_for_host(host.id))
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

    def build(
            self,
            propagation_channel_name,
            sponsor_name,
            remote_server_list_url,
            info_link_url,
            upgrade_url,
            platforms=None,
            test=False):
        if not platforms:
            platforms = [CLIENT_PLATFORM_WINDOWS, CLIENT_PLATFORM_ANDROID]

        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        encoded_server_list, expected_egress_ip_addresses = \
                    self.__get_encoded_server_list(propagation_channel.id)

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

        return [builders[platform](
                        propagation_channel.id,
                        sponsor.id,
                        base64.b64decode(sponsor.banner),
                        encoded_server_list,
                        remote_server_list_signature_public_key,
                        remote_server_list_url,
                        feedback_encryption_public_key,
                        feedback_upload_info.upload_server,
                        feedback_upload_info.upload_path,
                        feedback_upload_info.upload_server_headers,
                        info_link_url,
                        upgrade_signature_public_key,
                        upgrade_url,
                        self.__client_versions[platform][-1].version if self.__client_versions[platform] else 0,
                        test) for platform in platforms]

    def build_android_library(
            self,
            propagation_channel_name,
            sponsor_name):

        propagation_channel = self.get_propagation_channel_by_name(propagation_channel_name)
        sponsor = self.__get_sponsor_by_name(sponsor_name)

        campaigns = filter(lambda x: x.propagation_channel_id == propagation_channel.id, sponsor.campaigns)
        assert campaigns

        encoded_server_list, _ = \
                    self.__get_encoded_server_list(propagation_channel.id)

        remote_server_list_signature_public_key = \
            psi_ops_crypto_tools.get_base64_der_public_key(
                self.__get_remote_server_list_signing_key_pair().pem_key_pair,
                REMOTE_SERVER_SIGNING_KEY_PAIR_PASSWORD)

        feedback_encryption_public_key = \
            psi_ops_crypto_tools.get_base64_der_public_key(
                self.get_feedback_encryption_key_pair().pem_key_pair,
                self.get_feedback_encryption_key_pair().password)

        remote_server_list_url = psi_ops_s3.get_s3_bucket_resource_url(
                                    campaign.s3_bucket_name,
                                    psi_ops_s3.DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME)

        info_link_url = psi_ops_s3.get_s3_bucket_home_page_url(campaigns[0].s3_bucket_name)
        for plugin in plugins:
            if hasattr(plugin, 'info_link_url'):
                info_link_url = plugin.info_link_url(CLIENT_PLATFORM_ANDROID)

        return psi_ops_build_android.build_library(
                        propagation_channel.id,
                        sponsor.id,
                        encoded_server_list,
                        remote_server_list_signature_public_key,
                        feedback_encryption_public_key,
                        remote_server_list_url,
                        info_link_url,
                        self.__client_versions[CLIENT_PLATFORM_ANDROID][-1].version if self.__client_versions[CLIENT_PLATFORM_ANDROID] else 0)

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

    def deploy(self):
        # Deploy as required:
        #
        # - Implementation to flagged hosts
        # - Builds for required channels and sponsors
        # - Publish, tweet
        # - Data to all hosts
        # - Email and stats server config
        #
        # NOTE: Order is important. Hosts get new implementation before
        # new data, in case schema has changed; deploy builds before
        # deploying new data so an upgrade is available when it's needed

        assert(self.is_locked)

        # Host implementation

        hosts = [self.__hosts[host_id] for host_id in self.__deploy_implementation_required_for_hosts]
        psi_ops_deploy.deploy_implementation_to_hosts(hosts, plugins)

        if len(self.__deploy_implementation_required_for_hosts) > 0:
            self.__deploy_implementation_required_for_hosts.clear()
            self.save()

        # Build

        for platform in self.__deploy_builds_required_for_campaigns.iterkeys():
            for target in self.__deploy_builds_required_for_campaigns[platform].copy():

                propagation_channel_id, sponsor_id = target
                propagation_channel = self.__propagation_channels[propagation_channel_id]
                sponsor = self.__sponsors[sponsor_id]

                for campaign in filter(lambda x: x.propagation_channel_id == propagation_channel_id, sponsor.campaigns):

                    if not campaign.s3_bucket_name:
                        campaign.s3_bucket_name = psi_ops_s3.create_s3_bucket(self.__aws_account)
                        campaign.log('created s3 bucket %s' % (campaign.s3_bucket_name,))
                        self.save()  # don't leak buckets

                    # Remote server list: for clients to get new servers via S3, we embed the
                    # bucket URL in the build. So now we're ensuring the bucket exists and we
                    # have its URL before the build is uploaded to S3. The remote server list
                    # is placed in the S3 bucket.

                    remote_server_list_url = psi_ops_s3.get_s3_bucket_resource_url(
                                                campaign.s3_bucket_name,
                                                psi_ops_s3.DOWNLOAD_SITE_REMOTE_SERVER_LIST_FILENAME)

                    info_link_url = psi_ops_s3.get_s3_bucket_home_page_url(campaign.s3_bucket_name)
                    for plugin in plugins:
                        if hasattr(plugin, 'info_link_url'):
                            info_link_url = plugin.info_link_url(platform)

                    remote_server_list = \
                        psi_ops_crypto_tools.make_signed_data(
                            self.__get_remote_server_list_signing_key_pair().pem_key_pair,
                            REMOTE_SERVER_SIGNING_KEY_PAIR_PASSWORD,
                            '\n'.join(self.__get_encoded_server_list(propagation_channel.id)[0]))

                    # Build for each client platform

                    client_build_filenames = {
                        CLIENT_PLATFORM_WINDOWS: psi_ops_s3.DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME,
                        CLIENT_PLATFORM_ANDROID: psi_ops_s3.DOWNLOAD_SITE_ANDROID_BUILD_FILENAME
                    }
                    for plugin in plugins:
                        if hasattr(plugin, 'adjust_client_build_filenames'):
                            plugin.adjust_client_build_filenames(client_build_filenames)

                    s3_upgrade_resource_name = client_build_filenames[platform] + psi_ops_s3.DOWNLOAD_SITE_UPGRADE_SUFFIX

                    upgrade_url = psi_ops_s3.get_s3_bucket_resource_url(campaign.s3_bucket_name, s3_upgrade_resource_name)

                    build_filename = self.build(
                                        propagation_channel.name,
                                        sponsor.name,
                                        remote_server_list_url,
                                        info_link_url,
                                        upgrade_url,
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

                    psi_ops_s3.update_s3_download(
                        self.__aws_account,
                        [(build_filename, client_build_filenames[platform]),
                         (upgrade_filename, s3_upgrade_resource_name)],
                        remote_server_list,
                        campaign.s3_bucket_name,
                        campaign.custom_download_site)
                    campaign.log('updated s3 bucket %s' % (campaign.s3_bucket_name,))

                    if campaign.propagation_mechanism_type == 'twitter':
                        message = psi_templates.get_tweet_message(campaign.s3_bucket_name)
                        psi_ops_twitter.tweet(campaign.account, message)
                        campaign.log('tweeted')
                    elif campaign.propagation_mechanism_type == 'email-autoresponder':
                        if not self.__deploy_email_config_required:
                            self.__deploy_email_config_required = True
                            campaign.log('email push scheduled')

                # NOTE: before we added remote server lists, it used to be that
                # multiple campaigns with different buckets but the same prop/sponsor IDs
                # could share one build. The "deploy_builds_required_for_campaigns" dirty
                # flag granularity is a hold-over from that. In the current code, this
                # means some builds may be repeated unnecessarily in a failure case.

                self.__deploy_builds_required_for_campaigns[platform].remove(target)
                self.save()

        # Host data

        if self.__deploy_data_required_for_all:
            host_and_data_list = []
            for host in self.__hosts.itervalues():
                host_and_data_list.append(dict(host=host, data=self.__compartmentalize_data_for_host(host.id)))

            psi_ops_deploy.deploy_data_to_hosts(host_and_data_list)
            self.__deploy_data_required_for_all = False
            self.save()

        # Email and stats server configs

        if self.__deploy_stats_config_required:
            self.push_stats_config()
            self.__deploy_stats_config_required = False
            self.save()

        if self.__deploy_email_config_required:
            self.push_email_config()
            self.__deploy_email_config_required = False
            self.save()

    def update_static_site_content(self):
        assert(self.is_locked)
        for sponsor in self.__sponsors.itervalues():
            for campaign in sponsor.campaigns:
                if campaign.s3_bucket_name:
                    psi_ops_s3.update_s3_download(self.__aws_account, None, None, campaign.s3_bucket_name, campaign.custom_download_site)
                    campaign.log('updated s3 bucket %s' % (campaign.s3_bucket_name,))

    def update_routes(self):
        assert(self.is_locked)  # (host.log is called by deploy)
        psi_routes.make_routes()
        psi_ops_deploy.deploy_routes_to_hosts(self.__hosts.values())

    def push_stats_config(self):
        assert(self.is_locked)
        print 'push stats config...'

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        try:
            temp_file.write(self.__compartmentalize_data_for_stats_server())
            temp_file.close()
            psi_ops_cms.import_document(temp_file.name, True)
            self.__stats_server_account.log('pushed')
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
                    emails.append(
                        {
                         'email_addr': campaign.account.email_address,
                         'body':
                            [
                                ['plain', psi_templates.get_plaintext_attachment_email_content(
                                                campaign.s3_bucket_name,
                                                psi_ops_s3.EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME,
                                                psi_ops_s3.EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME,
                                                campaign.languages)],
                                ['html', psi_templates.get_html_attachment_email_content(
                                                campaign.s3_bucket_name,
                                                psi_ops_s3.EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME,
                                                psi_ops_s3.EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME,
                                                campaign.languages)]
                            ],
                         'attachments': [
                                         [campaign.s3_bucket_name,
                                          psi_ops_s3.DOWNLOAD_SITE_WINDOWS_BUILD_FILENAME,
                                          psi_ops_s3.EMAIL_RESPONDER_WINDOWS_ATTACHMENT_FILENAME],
                                         [campaign.s3_bucket_name,
                                          psi_ops_s3.DOWNLOAD_SITE_ANDROID_BUILD_FILENAME,
                                          psi_ops_s3.EMAIL_RESPONDER_ANDROID_ATTACHMENT_FILENAME]
                                        ],
                         'send_method': 'SMTP'
                        })

                    campaign.log('configuring email')

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        try:
            temp_file.write(json.dumps(emails, indent=2))
            temp_file.close()
            ssh = psi_ssh.SSH(
                    self.__email_server_account.ip_address,
                    self.__email_server_account.ssh_port,
                    self.__email_server_account.ssh_username,
                    None,
                    self.__email_server_account.ssh_host_key,
                    ssh_pkey=self.__email_server_account.ssh_pkey)
            ssh.put_file(
                    temp_file.name,
                    self.__email_server_account.config_file_path)
            self.__email_server_account.log('pushed')
        finally:
            try:
                os.remove(temp_file.name)
            except:
                pass

    def add_server_version(self):
        assert(self.is_locked)
        # Marks all hosts for re-deployment of server implementation
        for host in self.__hosts.itervalues():
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
                campaign.log('marked for build and publish (upgraded %s client)' % (platform,))
        # Need to deploy data as well for auto-update
        self.__deploy_data_required_for_all = True

    def get_server_entry(self, server_id):
        server = filter(lambda x: x.id == server_id, self.__servers.itervalues())[0]
        return self.__get_encoded_server_entry(server)

    def deploy_implementation_and_data_for_host_with_server(self, server_id):
        server = filter(lambda x: x.id == server_id, self.__servers.itervalues())[0]
        host = filter(lambda x: x.id == server.host_id, self.__hosts.itervalues())[0]
        psi_ops_deploy.deploy_implementation(host, plugins)
        psi_ops_deploy.deploy_data(host, self.__compartmentalize_data_for_host(host.id))

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
                           base_tarball_path):
        assert(self.is_locked)
        psi_utils.update_recordtype(
            self.__linode_account,
            api_key=api_key, base_id=base_id, base_ip_address=base_ip_address,
            base_ssh_port=base_ssh_port, base_root_password=base_root_password,
            base_stats_username=base_stats_username, base_host_public_key=base_host_public_key,
            base_known_hosts_entry=base_known_hosts_entry, base_rsa_private_key=base_rsa_private_key,
            base_rsa_public_key=base_rsa_public_key, base_tarball_path=base_tarball_path)

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

    def set_email_server_account(self, ip_address, ssh_port,
                                 ssh_username, ssh_pkey, ssh_host_key,
                                 config_file_path):
        assert(self.is_locked)
        psi_utils.update_recordtype(
            self.__email_server_account,
            ip_address=ip_address, ssh_port=ssh_port, ssh_username=ssh_username,
            ssh_pkey=ssh_pkey, ssh_host_key=ssh_host_key, config_file_path=config_file_path)

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
        # Double-check that we're not giving our blank server credentials
        # ...this has happened in the past when following manual build steps
        assert(len(server.ip_address) > 1)
        assert(len(server.web_server_port) > 1)
        assert(len(server.web_server_secret) > 1)
        assert(len(server.web_server_certificate) > 1)

        # Extended (i.e., new) entry fields are in a JSON string
        extended_config = {}

        # NOTE: also putting original values in extended config for easier parsing for new clients
        extended_config['ipAddress'] = server.ip_address
        extended_config['webServerPort'] = server.web_server_port
        extended_config['webServerSecret'] = server.web_server_secret
        extended_config['webServerCertificate'] = server.web_server_certificate

        extended_config['sshPort'] = int(server.ssh_port) if server.ssh_port else 0
        extended_config['sshUsername'] = server.ssh_username if server.ssh_username else ''
        extended_config['sshPassword'] = server.ssh_password if server.ssh_password else ''

        extended_config['sshHostKey'] = ''
        if server.ssh_host_key:
            ssh_host_key_type, extended_config['sshHostKey'] = server.ssh_host_key.split(' ')
            assert(ssh_host_key_type == 'ssh-rsa')

        extended_config['sshObfuscatedPort'] = int(server.ssh_obfuscated_port) if server.ssh_obfuscated_port else 0
        extended_config['sshObfuscatedKey'] = server.ssh_obfuscated_key if server.ssh_obfuscated_key else ''

        extended_config['capabilities'] = [capability for capability, enabled in server.capabilities.iteritems() if enabled] if server.capabilities else []

        return binascii.hexlify('%s %s %s %s %s' % (
                                    server.ip_address,
                                    server.web_server_port,
                                    server.web_server_secret,
                                    server.web_server_certificate,
                                    json.dumps(extended_config)))

    def __get_encoded_server_list(self, propagation_channel_id,
                                  client_ip_address=None, event_logger=None, discovery_date=None):
        if not client_ip_address:
            # embedded (propagation) server list
            # output all servers for propagation channel ID with no discovery date
            servers = [server for server in self.__servers.itervalues()
                       if server.propagation_channel_id == propagation_channel_id and
                           server.is_embedded]
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

            servers = psi_ops_discovery.select_servers(candidate_servers, client_ip_address)

        # optional logger (used by server to log each server IP address disclosed)
        if event_logger:
            for server in servers:
                event_logger(server.ip_address)
        return ([self.__get_encoded_server_entry(server) for server in servers],
                [server.egress_ip_address for server in servers])

    def __get_sponsor_home_pages(self, sponsor_id, region):
        # Web server support function: fails gracefully
        if sponsor_id not in self.__sponsors:
            return []
        sponsor = self.__sponsors[sponsor_id]
        # case: lookup succeeded and corresponding region home page found
        sponsor_home_pages = []
        if region in sponsor.home_pages:
            sponsor_home_pages = [home_page.url for home_page in sponsor.home_pages[region]]
        # case: lookup failed or no corresponding region home page found --> use default
        if not sponsor_home_pages and 'None' in sponsor.home_pages:
            sponsor_home_pages = [home_page.url for home_page in sponsor.home_pages['None']]
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
        if not self.__client_versions[platform]:
            return None
        last_version = self.__client_versions[platform][-1].version
        if int(last_version) > int(client_version):
            return last_version
        return None

    def handshake(self, server_ip_address, client_ip_address,
                  client_region, propagation_channel_id, sponsor_id,
                  client_platform_string, client_version, event_logger=None):
        # Legacy handshake output is a series of Name:Value lines returned to
        # the client. That format will continue to be supported (old client
        # versions expect it), but the new format of a JSON-ified object will
        # also be output.

        config = {}

        # Give client a set of landing pages to open when connection established
        config['homepages'] = self.__get_sponsor_home_pages(sponsor_id, client_region)

        # Match a client platform to client_platform_string
        platform = CLIENT_PLATFORM_WINDOWS
        if CLIENT_PLATFORM_ANDROID.lower() in client_platform_string.lower():
            platform = CLIENT_PLATFORM_ANDROID

        # Tell client if an upgrade is available
        config['upgrade_client_version'] = self.__check_upgrade(platform, client_version)

        # Discovery
        # NOTE: Clients are expecting at least an empty list
        config['encoded_server_list'] = []
        if client_ip_address:
            config['encoded_server_list'], _ = \
                        self.__get_encoded_server_list(
                                                    propagation_channel_id,
                                                    client_ip_address,
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

    def __compartmentalize_data_for_host(self, host_id, discovery_date=datetime.datetime.now()):
        # Create a compartmentalized database with only the information needed by a particular host
        # - all propagation channels because any client may connect to servers on this host
        # - servers data
        #   omit discovery servers not on this host whose discovery time period has elapsed
        #   also, omit propagation servers not on this host
        #   (not on this host --> because servers on this host still need to run, even if not discoverable)
        # - send home pages for all sponsors, but omit names, banners, campaigns
        # - send versions info for upgrades

        copy = PsiphonNetwork(initialize_plugins=False)

        for propagation_channel in self.__propagation_channels.itervalues():
            copy.__propagation_channels[propagation_channel.id] = PropagationChannel(
                                                                    propagation_channel.id,
                                                                    '',  # Omit name
                                                                    '',  # Omit mechanism type
                                                                    '',  # Omit new server counts
                                                                    '',  # Omit new server counts
                                                                    '',  # Omit server ages
                                                                    '')  # Omit server ages

        for server in self.__servers.itervalues():
            if ((server.discovery_date_range and server.host_id != host_id and server.discovery_date_range[1] <= discovery_date) or
                (not server.discovery_date_range and server.host_id != host_id)):
                continue

            copy.__servers[server.id] = Server(
                                                server.id,
                                                '',  # Omit host_id
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
                                                server.ssh_obfuscated_port,
                                                server.ssh_obfuscated_key)

        for sponsor in self.__sponsors.itervalues():
            copy_sponsor = Sponsor(
                                sponsor.id,
                                '',  # Omit name
                                '',  # Omit banner
                                {},
                                [],  # Omit campaigns
                                sponsor.page_view_regexes,
                                sponsor.https_request_regexes)
            for region, home_pages in sponsor.home_pages.iteritems():
                copy_sponsor.home_pages[region] = home_pages
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

        return jsonpickle.encode(copy)

    def __compartmentalize_data_for_stats_server(self):
        # The stats server needs to be able to connect to all hosts and needs
        # the information to replace server IPs with server IDs, sponsor IDs
        # with names and propagation IDs with names

        copy = PsiphonNetwork(initialize_plugins=False)

        for host in self.__hosts.itervalues():
            copy.__hosts[host.id] = Host(
                                            host.id,
                                            host.provider,
                                            '',  # Omit: provider id isn't needed
                                            host.ip_address,
                                            host.ssh_port,
                                            '',  # Omit: root ssh username
                                            '',  # Omit: root ssh password
                                            host.ssh_host_key,
                                            host.stats_ssh_username,
                                            host.stats_ssh_password,
                                            host.datacenter_name)

        for server in self.__servers.itervalues():
            copy.__servers[server.id] = Server(
                                            server.id,
                                            server.host_id,
                                            server.ip_address,
                                            None,
                                            server.internal_ip_address,
                                            None,
                                            server.is_embedded,
                                            server.is_permanent,
                                            server.discovery_date_range)
                                            # Omit: propagation, web server, ssh info

        for deleted_server in self.__deleted_servers.itervalues():
            copy.__deleted_servers[deleted_server.id] = Server(
                                            deleted_server.id,
                                            deleted_server.host_id,
                                            deleted_server.ip_address,
                                            None,
                                            deleted_server.internal_ip_address,
                                            None,
                                            deleted_server.is_embedded,
                                            deleted_server.is_permanent,
                                            deleted_server.discovery_date_range)
                                            # Omit: propagation, web server, ssh info

        for propagation_channel in self.__propagation_channels.itervalues():
            copy.__propagation_channels[propagation_channel.id] = PropagationChannel(
                                        propagation_channel.id,
                                        propagation_channel.name,
                                        [],  # Omit mechanism info
                                        '',  # Omit new server counts
                                        '',  # Omit new server counts
                                        '',  # Omit server ages
                                        '')  # Omit server ages

        for sponsor in self.__sponsors.itervalues():
            copy.__sponsors[sponsor.id] = Sponsor(
                                        sponsor.id,
                                        sponsor.name,
                                        '',
                                        {},
                                        [],
                                        [],
                                        [])  # Omit banner, home pages, campaigns, regexes

        return jsonpickle.encode(copy)

    def run_command_on_host(self, host, command):
        ssh = psi_ssh.SSH(
                host.ip_address, host.ssh_port,
                host.ssh_username, host.ssh_password,
                host.ssh_host_key)

        return ssh.exec_command(command)

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

    def __test_server(self, server, test_cases):
        test_propagation_channel = None
        try:
            test_propagation_channel = self.get_propagation_channel_by_name('Testing')
        except:
            pass
        test_propagation_channel_id = test_propagation_channel.id if test_propagation_channel else '0'

        return psi_ops_test_windows.test_server(
                                server.ip_address,
                                server.capabilities,
                                server.web_server_port,
                                server.web_server_secret,
                                [self.__get_encoded_server_entry(server)],
                                self.__client_versions[CLIENT_PLATFORM_WINDOWS][-1].version if self.__client_versions[CLIENT_PLATFORM_WINDOWS] else 0,  # This uses the Windows client
                                [server.egress_ip_address],
                                test_propagation_channel_id,
                                test_cases)

    def __test_servers(self, servers, test_cases):
        results = {}
        passes = 0
        failures = 0
        servers_with_errors = set()
        for server in servers:
            result = self.__test_server(server, test_cases)
            results[server.id] = result
            for test_result in result.itervalues():
                if 'FAIL' in test_result:
                    servers_with_errors.add(server.id)
                    break
        # One final pass to re-test servers that failed
        for server_id in servers_with_errors:
            server = self.__servers[server_id]
            result = self.__test_server(server, test_cases)
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

    def test_server(self, server_id, test_cases=None):
        if not server_id in self.__servers:
            print 'Server "%s" not found' % (server_id,)
        elif self.__servers[server_id].propagation_channel_id == None:
            print 'Server "%s" does not have a propagation channel id' % (server_id,)
        else:
            servers = [self.__servers[server_id]]
            self.__test_servers(servers, test_cases)

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
        sponsor = self.__get_sponsor_by_name(sponsor_name)
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


def prune_all_propagation_channels():
    psinet = PsiphonNetwork.load(lock=True)
    psinet.show_status()
    try:
        for propagation_channel in psinet._PsiphonNetwork__propagation_channels.itervalues():
            number_removed, number_disabled = psinet.prune_propagation_channel_servers(propagation_channel.name)
            sys.stderr.write('Pruned %d servers from %s\n' % (number_removed, propagation_channel.name))
            sys.stderr.write('Disabled %d servers from %s\n' % (number_disabled, propagation_channel.name))
    finally:
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


if __name__ == "__main__":
    parser = optparse.OptionParser('usage: %prog [options]')
    parser.add_option("-r", "--read-only", dest="readonly", action="store_true",
                      help="don't lock the network object")
    parser.add_option("-t", "--test", dest="test", action="append",
                      choices=('handshake', 'VPN', 'OSSH', 'SSH'),
                      help="specify once for each of: handshake, VPN, OSSH, SSH")
    parser.add_option("-p", "--prune", dest="prune", action="store_true",
                      help="prune all propagation channels")
    parser.add_option("-n", "--new-servers", dest="channel", action="store", type="string",
                      help="create new servers for this propagation channel")
    (options, _) = parser.parse_args()
    if options.channel:
        replace_propagation_channel_servers(options.channel)
    elif options.prune:
        prune_all_propagation_channels()
    elif options.test:
        test(options.test)
    elif options.readonly:
        view()
    else:
        edit()
