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
import time
import datetime
import pprint
import json
import textwrap
import itertools
import binascii
import base64
import jsonpickle
import tempfile
import pprint
import struct
import socket
import random
from pkg_resources import parse_version

import psi_utils
import psi_ops_cms

# Modules available only on the automation server

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
    import psi_ops_build
except ImportError as error:
    print error
    
try:
    import psi_ops_test
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
    
# Modules available only on the node server

try:
    import GeoIP
except ImportError:
    pass

# NOTE: update compartmentalize() functions when adding fields

PropagationChannel = psi_utils.recordtype(
    'PropagationChannel',
    'id, name, propagation_mechanism_types')

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
    'propagation_channel_id, propagation_mechanism_type, account, s3_bucket_name')

SponsorRegex = psi_utils.recordtype(
    'SponsorRegex',
    'regex, replace')

Host = psi_utils.recordtype(
    'Host',
    'id, provider, provider_id, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key, '+
    'stats_ssh_username, stats_ssh_password')

Server = psi_utils.recordtype(
    'Server',
    'id, host_id, ip_address, egress_ip_address, '+
    'propagation_channel_id, is_embedded, discovery_date_range, '+
    'web_server_port, web_server_secret, web_server_certificate, web_server_private_key, '+
    'ssh_port, ssh_username, ssh_password, ssh_host_key, ssh_obfuscated_port, ssh_obfuscated_key',
    default=None)

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
    'api_key, base_id, base_ip_address, base_ssh_port, '+
    'base_root_password, base_stats_username, base_host_public_key, '+
    'base_known_hosts_entry, base_rsa_private_key, base_rsa_public_key, '+
    'base_tarball_path',
    default=None)

ElasticHostsAccount = psi_utils.recordtype(
    'ElasticHostsAccount',
    'zone, uuid, api_key, base_drive_id, cpu, mem, base_host_public_key, '+
        'root_username, base_root_password, base_ssh_port, stats_username, rank', 
    default=None)
ElasticHostsAccount.zone_values = ('ELASTICHOSTS_US1', # sat-p
                                   'ELASTICHOSTS_UK1', # lon-p
                                   'ELASTICHOSTS_UK2') # lon-b

EmailServerAccount = psi_utils.recordtype(
    'EmailServerAccount',
    'ip_address, ssh_port, ssh_username, ssh_pkey, ssh_host_key, '+
    'config_file_path',
    default=None)

StatsServerAccount = psi_utils.recordtype(
    'StatsServerAccount',
    'ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key',
    default=None)


class PsiphonNetwork(psi_ops_cms.PersistentObject):

    def __init__(self):
        super(PsiphonNetwork, self).__init__()
        # TODO: what is this __version for?
        self.__version = '1.0'
        self.__sponsors = {}
        self.__propagation_mechanisms = {
            'twitter' : PropagationMechanism('twitter'),
            'email-autoresponder' : PropagationMechanism('email-autoresponder'),
            'static-download' : PropagationMechanism('static-download')
        }
        self.__propagation_channels = {}
        self.__hosts = {}
        self.__servers = {}
        self.__client_versions = []
        self.__email_server_account = EmailServerAccount()
        self.__stats_server_account = StatsServerAccount()
        self.__aws_account = AwsAccount()
        self.__provider_ranks = []
        self.__linode_account = LinodeAccount()
        self.__elastichosts_accounts = []
        self.__deploy_implementation_required_for_hosts = set()
        self.__deploy_data_required_for_all = False
        self.__deploy_builds_required_for_campaigns = set()
        self.__deploy_stats_config_required = False
        self.__deploy_email_config_required = False

    class_version = '0.4'

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

    def show_status(self):
        # NOTE: verbose mode prints credentials to stdout
        print textwrap.dedent('''
            Sponsors:             %d
            Channels:             %d
            Twitter Campaigns:    %d
            Email Campaigns:      %d
            Hosts:                %d
            Servers:              %d
            Email Server:         %s
            Stats Server:         %s
            Client Version:       %s %s
            AWS Account:          %s
            Provider Ranks:       %s
            Linode Account:       %s
            ElasticHosts Account: %s
            Deploys Pending:      Host Implementations    %d                              
                                  Host Data               %s
                                  Campaign Builds         %d
                                  Stats Server Config     %s
                                  Email Server Config     %s
            ''') % (
                len(self.__sponsors),
                len(self.__propagation_channels),
                sum([len(filter(lambda x:x.propagation_mechanism_type == 'twitter', sponsor.campaigns))
                     for sponsor in self.__sponsors.itervalues()]),
                sum([len(filter(lambda x:x.propagation_mechanism_type == 'email-autoresponder', sponsor.campaigns))
                     for sponsor in self.__sponsors.itervalues()]),
                len(self.__hosts),
                len(self.__servers),
                self.__email_server_account.ip_address if self.__email_server_account else 'None',
                self.__stats_server_account.ip_address if self.__stats_server_account else 'None',
                self.__client_versions[-1].version if self.__client_versions else 'None',
                self.__client_versions[-1].description if self.__client_versions else '',
                'Configured' if self.__aws_account.access_id else 'None',
                'Configured' if self.__provider_ranks else 'None',
                'Configured' if self.__linode_account.api_key else 'None',
                'Configured' if self.__elastichosts_accounts else 'None',
                len(self.__deploy_implementation_required_for_hosts),
                'Yes' if self.__deploy_data_required_for_all else 'No',
                len(self.__deploy_builds_required_for_campaigns),
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
            Page View Regexes:       %(page_view_regexes)d
            HTTPS Request Regexes:   %(https_request_regexes)d
            Campaigns:               %(campaigns)s
            ''') % {
                    'id': s.id,
                    'name': s.name,
                    'home_pages': ', '.join(['%s: %s' % (region if region else 'All',
                                                         ', '.join([h.url for h in home_pages]))
                                                         for region, home_pages in s.home_pages.iteritems()]),
                    'page_view_regexes': ', '.join(len(s.page_view_regexes)),
                    'https_request_regexes': ', '.join(len(s.https_request_regexes)),
                    'campaigns': ', '.join(['%s %s %s %s' % (
                                                             self.__propagation_channels[c.propagation_channel_id].name,
                                                             c.propagation_mechanism_type,
                                                             c.account[0] if c.account else 'None',
                                                             c.s3_bucket_name)
                                            for c in s.campaigns])
                    }
        self.__show_logs(s)

    def show_campaigns_on_propagation_channel(self, propagation_channel_name):
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)
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
        
    def show_propagation_channels(self):
        for p in self.__propagation_channels.itervalues():
            self.show_propagation_channel(p.name)
        
    def show_propagation_channel(self, propagation_channel_name, now=None):
        if now == None:
            now = datetime.datetime.now()
        p = self.__get_propagation_channel_by_name(propagation_channel_name)
        embedded_servers = [server.id for server in self.__servers.itervalues()
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
            ID:                       %s
            Name:                     %s
            Propagation Mechanisms:   %s
            Embedded Servers:         %s
            Discovery Servers:        %s
            Future Discovery Servers: %s
            Old Propagation Servers:  %s
            Old Discovery Servers:    %s
            ''') % (
                p.id,
                p.name,
                '\n                          '.join(p.propagation_mechanism_types),
                '\n                          '.join(embedded_servers),
                '\n                          '.join(current_discovery_servers),
                '\n                          '.join(future_discovery_servers),
                '\n                          '.join(old_propagation_servers),
                '\n                          '.join(old_discovery_servers))
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
            Host:                    %s %s/%s
            IP Address:              %s
            Propagation Channel:     %s
            Is Embedded:             %s
            Discovery Date Range:    %s
            ''') % (
                s.id,
                s.host_id,
                self.__hosts[s.host_id].ssh_username,
                self.__hosts[s.host_id].ssh_password,
                s.ip_address,
                self.__propagation_channels[s.propagation_channel_id].name if s.propagation_channel_id else 'None',
                s.is_embedded,
                ('%s - %s' % (s.discovery_date_range[0].isoformat(),
                            s.discovery_date_range[1].isoformat())) if s.discovery_date_range else 'None')
        self.__show_logs(s)

    def show_provider_ranks(self):
        for r in self.__provider_ranks:
            print textwrap.dedent('''
                Provider:   %s
                Rank:       %s
                ''') % (r.provider, r.rank)
            
    def __generate_id(self):
        count = 16
        chars = '0123456789ABCDEF'
        return ''.join([chars[ord(os.urandom(1))%len(chars)] for i in range(count)])

    def __get_propagation_channel_by_name(self, name):
        return filter(lambda x:x.name == name,
                      self.__propagation_channels.itervalues())[0]

    def add_propagation_channel(self, name, propagation_mechanism_types):
        self.import_propagation_channel(self.__generate_id(), name, propagation_mechanism_types)

    def import_propagation_channel(self, id, name, propagation_mechanism_types):
        for type in propagation_mechanism_types: assert(type in self.__propagation_mechanisms)
        propagation_channel = PropagationChannel(id, name, propagation_mechanism_types)
        assert(id not in self.__propagation_channels)
        assert(not filter(lambda x:x.name == name, self.__propagation_channels.itervalues()))
        self.__propagation_channels[id] = propagation_channel

    def __get_sponsor_by_name(self, name):
        return filter(lambda x:x.name == name,
                      self.__sponsors.itervalues())[0]

    def add_sponsor(self, name):
        self.import_sponsor(self.__generate_id(), name)

    def import_sponsor(self, id, name):
        sponsor = Sponsor(id, name, None, {}, [], [])
        assert(id not in self.__sponsors)
        assert(not filter(lambda x:x.name == name, self.__sponsors.itervalues()))
        self.__sponsors[id] = sponsor

    def set_sponsor_banner(self, name, banner_filename):
        with open(banner_filename, 'rb') as file:
            banner = base64.b64encode(file.read())
        sponsor = self.__get_sponsor_by_name(name)
        sponsor.banner = banner
        sponsor.log('set banner')
        for campaign in sponsor.campaigns:
            self.__deploy_builds_required_for_campaigns.add(
                (campaign.propagation_channel_id, sponsor.id))
            campaign.log('marked for build and publish (new banner)')

    def add_sponsor_email_campaign(self, sponsor_name, propagation_channel_name, email_account):
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)
        propagation_mechanism_type = 'email-autoresponder'
        assert(propagation_mechanism_type in propagation_channel.propagation_mechanism_types)
        # TODO: assert(email_account not in ...)
        campaign = SponsorCampaign(propagation_channel.id,
                                   propagation_mechanism_type,
                                   EmailPropagationAccount(email_account),
                                   None)
        if campaign not in sponsor.campaigns:
            sponsor.campaigns.append(campaign)
            sponsor.log('add email campaign %s' % (email_account,))
            self.__deploy_builds_required_for_campaigns.add(
                    (campaign.propagation_channel_id, sponsor.id))
            campaign.log('marked for build and publish (new campaign)')

    def add_sponsor_twitter_campaign(self, sponsor_name,
                                     propagation_channel_name,
                                     twitter_account_name,
                                     twitter_account_consumer_key,
                                     twitter_account_consumer_secret,
                                     twitter_account_access_token_key,
                                     twitter_account_access_token_secret):
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)
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
                                   None)
        if campaign not in sponsor.campaigns:
            sponsor.campaigns.append(campaign)
            sponsor.log('add twitter campaign %s' % (twitter_account_name,))
            self.__deploy_builds_required_for_campaigns.add(
                    (campaign.propagation_channel_id, sponsor.id))
            campaign.log('marked for build and publish (new campaign)')

    def add_sponsor_static_download_campaign(self, sponsor_name, propagation_channel_name):
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)
        propagation_mechanism_type = 'static-download'
        assert(propagation_mechanism_type in propagation_channel.propagation_mechanism_types)
        campaign = SponsorCampaign(propagation_channel.id,
                                   propagation_mechanism_type,
                                   None,
                                   None)
        if campaign not in sponsor.campaigns:
            sponsor.campaigns.append(campaign)
            sponsor.log('add static download campaign')
            self.__deploy_builds_required_for_campaigns.add(
                    (campaign.propagation_channel_id, sponsor.id))
            campaign.log('marked for build and publish (new campaign)')

    def set_sponsor_campaign_s3_bucket_name(self, sponsor_name, propagation_channel_name, account, s3_bucket_name):
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)
        for campaign in sponsor.campaigns:
            if (campaign.propagation_channel_id == propagation_channel.id and
                campaign.account[0] == account):
                    campaign.s3_bucket_name = s3_bucket_name
                    campaign.log('set campaign s3 bucket name to %s' % (s3_bucket_name,))
                    self.__deploy_builds_required_for_campaigns.add(
                        (campaign.propagation_channel_id, sponsor.id))
                    campaign.log('marked for build and publish (modified campaign)')
            
    def set_sponsor_home_page(self, sponsor_name, region, url):
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
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        home_page = SponsorHomePage(region, url)
        if (region in sponsor.home_pages
            and home_page in sponsor.home_pages[region]):
            sponsor.home_pages[region].remove(home_page)
            sponsor.log('deleted home page %s for %s' % (url, region))
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def set_sponsor_page_view_regex(self, sponsor_name, regex, replace):
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
        assert(not filter(lambda x:x.name == new_sponsor_name, self.__sponsors.itervalues()))
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        sponsor.name = (new_sponsor_name)
        self.__deploy_stats_config_required = True
        sponsor.log('set sponsor name from \'%s\' to \'%s\'' % (sponsor_name, new_sponsor_name))
        
    def get_server_by_ip_address(self, ip_address):
        servers = filter(lambda x:x.ip_address == ip_address, self.__servers.itervalues())
        if len(servers) == 1:
            return servers[0]
        return None

    def import_host(self, id, provider, provider_id, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key,
                    stats_ssh_username, stats_ssh_password):
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

    def import_server(self, server_id, host_id, ip_address, egress_ip_address, propagation_channel_id,
                      is_embedded, discovery_date_range, web_server_port, web_server_secret,
                      web_server_certificate, web_server_private_key, ssh_port, ssh_username,
                      ssh_password, ssh_host_key):
        server = Server(
                    server_id,
                    host_id,
                    ip_address,
                    egress_ip_address,
                    propagation_channel_id,
                    is_embedded,
                    discovery_date_range,
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
        
    def add_servers(self, count, propagation_channel_name, discovery_date_range, replace_others=True):
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)

        # Embedded servers (aka "propagation servers") are embedded in client
        # builds, where as discovery servers are only revealed when clients
        # connect to a server.
        is_embedded_server = (discovery_date_range is None)

        if replace_others:
            # If we are creating new propagation servers, stop embedding the old ones
            # (they are still active, but not embedded in builds or discovered)
            if is_embedded_server:
                for old_server in self.__servers.itervalues():
                    if (old_server.propagation_channel_id == propagation_channel.id and
                        old_server.is_embedded):
                        old_server.is_embedded = False
                        old_server.log('unembedded')
            # If we are creating new discovery servers, stop discovering existing ones
            else:
                self.__replace_propagation_channel_discovery_servers(propagation_channel.id)

        for _ in range(count):
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
            server_info = provider_launch_new_server(provider_account)
            host = Host(*server_info)
            host.provider = provider.lower()

            # NOTE: jsonpickle will serialize references to discovery_date_range, which can't be
            # resolved when unpickling, if discovery_date_range is used directly.
            # So create a copy instead.
            discovery = self.__copy_date_range(discovery_date_range) if discovery_date_range else None
            
            server = Server(
                        None,
                        host.id,
                        host.ip_address,
                        host.ip_address,
                        propagation_channel.id,
                        is_embedded_server,
                        discovery,
                        '8080',
                        None,
                        None,
                        None,
                        '22',
                        None,
                        None,
                        None,
                        '995')

            # Install Psiphon 3 and generate configuration values
            # Here, we're assuming one server/IP address per host
            existing_server_ids = [existing_server.id for existing_server in self.__servers.itervalues()]
            psi_ops_install.install_host(host, [server], existing_server_ids)
            host.log('install')

            # Update database

            # Add new server (we also add a host; here, the host and server are
            # one-to-one, but legacy networks have many servers per host and we
            # retain support for this in the data model and general functionality)
            # Note: this must be done before deploy_data otherwise the deployed
            # data will not include this host and server
            assert(host.id not in self.__hosts)
            self.__hosts[host.id] = host
            assert(server.id not in self.__servers)
            self.__servers[server.id] = server

            # Deploy will upload web server source database data and client builds
            # (Only deploying for the new host, not broadcasting info yet...)
            psi_ops_deploy.deploy_implementation(host)
            psi_ops_deploy.deploy_data(
                                host,
                                self.__compartmentalize_data_for_host(host.id))
            psi_ops_deploy.deploy_routes(host)
            host.log('initial deployment')

            self.test_server(server.id, test_vpn=False, test_ssh=False)
            
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
                        self.__deploy_builds_required_for_campaigns.add(
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
        host = self.__hosts[host_id]
        if host.provider == 'linode':
            provider_remove_host = psi_linode.remove_server
            provider_account = self.__linode_account
        else:
            raise ValueError('can\'t remove host from provider %s' % host.provider)
        
        # Remove the actual host through the provider's API
        provider_remove_host(provider_account, host.provider_id)
        
        # Delete the host and it's servers from the DB
        server_ids_on_host = []
        for server in self.__servers.itervalues():
            if server.host_id == host.id:
                server_ids_on_host.append(server.id)
        for server_id in server_ids_on_host:
            self.__servers.pop(server_id)
        self.__hosts.pop(host.id)
        
        # Clear flags that include this host id.  Update stats config.
        if host.id in self.__deploy_implementation_required_for_hosts:
            self.__deploy_implementation_required_for_hosts.remove(host.id)
        self.__deploy_stats_config_required = True
        # NOTE: If host was currently discoverable or will be in the future, 
        #       host data should be updated.
        # NOTE: If host was currently embedded, new campaign builds are needed.
        
        self.save()

    def reinstall_host(self, host_id):
        host = self.__hosts[host_id]
        servers = [server for server in self.__servers.itervalues() if server.host_id == host_id]
        existing_server_ids = [existing_server.id for existing_server in self.__servers.itervalues()]
        psi_ops_install.install_host(host, servers, existing_server_ids)
        psi_ops_deploy.deploy_implementation(host)
        # New data might have been generated
        # NOTE that if the client version has been incremented but a full deploy has not yet been run,
        # this following psi_ops_deploy.deploy_data call is not safe.  Data will specify a new version
        # that is not yet available on servers (infinite download loop).
        psi_ops_deploy.deploy_data(
                                host,
                                self.__compartmentalize_data_for_host(host.id))
        host.log('reinstall')

    def reinstall_hosts(self):
        for host in self.__hosts.itervalues():
            self.reinstall_host(host.id)
            
    def set_servers_propagation_channel_and_discovery_date_range(self, server_names, propagation_channel_name, discovery_date_range, replace_others=True):
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)

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

    def build(self, propagation_channel_name, sponsor_name, test=False):
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        version = self.__client_versions[-1].version
        encoded_server_list, expected_egress_ip_addresses = \
                    self.__get_encoded_server_list(propagation_channel.id)
        
        # A sponsor may use the same propagation channel for multiple
        # campaigns; we need only build and upload the client once.
        return psi_ops_build.build_client(
                        propagation_channel.id,
                        sponsor.id,
                        base64.b64decode(sponsor.banner),
                        encoded_server_list,
                        version,
                        test)

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

        # Host implementation

        for host_id in self.__deploy_implementation_required_for_hosts:
            host = self.__hosts[host_id]
            psi_ops_deploy.deploy_implementation(host)
            host.log('deploy implementation')
        
        if len(self.__deploy_implementation_required_for_hosts) > 0:
            self.__deploy_implementation_required_for_hosts.clear()
            self.save()

        # Build

        for target in self.__deploy_builds_required_for_campaigns.copy():

            propagation_channel_id, sponsor_id = target
            propagation_channel = self.__propagation_channels[propagation_channel_id]
            sponsor = self.__sponsors[sponsor_id]

            # Build and upload to hosts
                
            build_filename = self.build(propagation_channel.name, sponsor.name)

            # Upload client builds
            # We only upload the builds for Propagation Channel IDs that need to be known for the host.
            # UPDATE: Now we copy all builds.  We know that this breaks compartmentalization.
            # However, we do not want to prevent an upgrade in the case where a user has
            # downloaded from multiple propagation channels, and might therefore be connecting
            # to a server from one propagation channel using a build from a different one.
            for host in self.__hosts.itervalues():
                psi_ops_deploy.deploy_build(host, build_filename)

            # Publish to propagation mechanisms

            for campaign in filter(lambda x:x.propagation_channel_id == propagation_channel_id, sponsor.campaigns):
                if campaign.s3_bucket_name:
                    psi_ops_s3.update_s3_download(self.__aws_account, build_filename, campaign.s3_bucket_name)
                    campaign.log('updated s3 bucket %s' % (campaign.s3_bucket_name,))
                else:
                    campaign.s3_bucket_name = psi_ops_s3.publish_s3_download(self.__aws_account, build_filename)
                    campaign.log('created s3 bucket %s' % (campaign.s3_bucket_name,))

                if campaign.propagation_mechanism_type == 'twitter':
                    message = psi_templates.get_tweet_message(campaign.s3_bucket_name)
                    psi_ops_twitter.tweet(campaign.account, message)
                    campaign.log('tweeted')
                elif campaign.propagation_mechanism_type == 'email-autoresponder':
                    if not self.__deploy_email_config_required:
                        self.__deploy_email_config_required = True
                        campaign.log('email push scheduled')
                    
            self.__deploy_builds_required_for_campaigns.remove(target)
            self.save()

        # Host data

        if self.__deploy_data_required_for_all:
            for host in self.__hosts.itervalues():
                psi_ops_deploy.deploy_data(
                                    host,
                                    self.__compartmentalize_data_for_host(host.id))
                host.log('deploy data')
        
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

    def update_routes(self):
        psi_routes.make_routes()
        for host in self.__hosts.itervalues():
            psi_ops_deploy.deploy_routes(host)
            host.log('deploy routes')

    def push_stats_config(self):
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
        
        print 'push email config...'
        
        emails = {}
        for sponsor in self.__sponsors.itervalues():
            for campaign in sponsor.campaigns:
                if (campaign.propagation_mechanism_type == 'email-autoresponder' and
                    campaign.s3_bucket_name != None):
                    emails[campaign.account.email_address] = \
                    {
                     'body': 
                        [
                            ['plain', psi_templates.get_plaintext_email_content(campaign.s3_bucket_name)],
                            ['html', psi_templates.get_html_email_content(campaign.s3_bucket_name)]
                        ],
                     'attachment_bucket': campaign.s3_bucket_name
                    }
                    campaign.log('configuring email')
        
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        try:
            temp_file.write(json.dumps(emails))
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
        # Marks all hosts for re-deployment of server implementation
        for host in self.__hosts.itervalues():
            self.__deploy_implementation_required_for_hosts.add(host.id)
            host.log('marked for implementation deployment')

    def add_client_version(self, description):
        # Records the new version number to trigger upgrades
        next_version = 1
        if len(self.__client_versions) > 0:
            next_version = int(self.__client_versions[-1].version)+1
        client_version = ClientVersion(str(next_version), description)
        self.__client_versions.append(client_version)
        # Mark deploy flag to rebuild and upload all clients
        for sponsor in self.__sponsors.itervalues():
            for campaign in sponsor.campaigns:
                self.__deploy_builds_required_for_campaigns.add(
                        (campaign.propagation_channel_id, sponsor.id))
                campaign.log('marked for build and publish (upgraded client)')
        # Need to deploy data as well for auto-update
        self.__deploy_data_required_for_all = True

    def get_server_entry(self, server_id):
        server = filter(lambda x:x.id == server_id,self.__servers.itervalues())[0]
        return self.__get_encoded_server_entry(server)
    
    def deploy_implementation_for_host_with_server(self, server_id):
        server = filter(lambda x:x.id == server_id,self.__servers.itervalues())[0]
        host = filter(lambda x:x.id == server.host_id,self.__hosts.itervalues())[0]
        psi_ops_deploy.deploy_implementation(host)

    def set_aws_account(self, access_id, secret_key):
        psi_utils.update_recordtype(
            self.__aws_account,
            access_id=access_id, secret_key=secret_key)

    def upsert_provider_rank(self, provider, rank):
        '''
        Inserts or updates a Provider-Rank entry. The "key" for an entry is provider. 
        rank: the higher the score, the more the provider will be preferred when
            provideres are being randomly selected among.
        '''
        
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
        psi_utils.update_recordtype(
            self.__email_server_account,
            ip_address=ip_address, ssh_port=ssh_port, ssh_username=ssh_username,
            ssh_pkey=ssh_pkey, ssh_host_key=ssh_host_key, config_file_path=config_file_path)

    def set_stats_server_account(self, ip_address, ssh_port,
                                 ssh_username, ssh_password, ssh_host_key):
        psi_utils.update_recordtype(
            self.__stats_server_account,
            ip_address=ip_address, ssh_port=ssh_port, ssh_username=ssh_username,
            ssh_password=ssh_password, ssh_host_key=ssh_host_key)

    def __get_encoded_server_entry(self, server):
        # Double-check that we're not giving our blank server credentials
        # ...this has happened in the past when following manual build steps
        assert(len(server.ip_address) > 1)
        assert(len(server.web_server_port) > 1)
        assert(len(server.web_server_secret) > 1)
        assert(len(server.web_server_certificate) > 1)
        return binascii.hexlify('%s %s %s %s' % (
                                    server.ip_address,
                                    server.web_server_port,
                                    server.web_server_secret,
                                    server.web_server_certificate))    
    
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
            # count servers for propagation channel ID to be discovered in current date range
            servers = [server for server in self.__servers.itervalues()
                       if server.propagation_channel_id == propagation_channel_id and (
                           server.discovery_date_range is not None and
                           server.discovery_date_range[0] <= discovery_date < server.discovery_date_range[1])]
            # number of IP Address buckets is number of matching servers, so just
            # give the client the one server in their bucket
            # NOTE: when there are many servers, we could return more than one per bucket. For example,
            # with 4 matching servers, we could make 2 buckets of 2. But if we have that many servers,
            # it would be better to mix in an additional strategy instead of discovering extra servers
            # for no additional "effort".
            bucket_count = len(servers)
            if bucket_count == 0:
                return ([], None)
            bucket = struct.unpack('!L',socket.inet_aton(client_ip_address))[0] % bucket_count
            servers = [servers[bucket]]
        # optional logger (used by server to log each server IP address disclosed)
        if event_logger:
            for server in servers:
                event_logger(server.ip_address)
        return ([self.__get_encoded_server_entry(server) for server in servers],
                [server.egress_ip_address for server in servers])
        
    def get_region(self, client_ip_address):
        try:
            region = None
            # Use the commercial "city" database is available
            city_db_filename = '/usr/local/share/GeoIP/GeoIPCity.dat'
            if os.path.isfile(city_db_filename):
                record = GeoIP.open(city_db_filename,
                                    GeoIP.GEOIP_MEMORY_CACHE).record_by_name(client_ip_address)
                if record:
                    region = record['country_code']
            else:
                region = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE).country_code_by_name(client_ip_address)
            if region is None:
                region = 'None'
            return region
        except NameError:
            # Handle the case where the GeoIP module isn't installed
            return 'None'
    
    def __get_sponsor_home_pages(self, sponsor_id, client_ip_address, region=None):
        # Web server support function: fails gracefully
        if sponsor_id not in self.__sponsors:
            return []
        sponsor = self.__sponsors[sponsor_id]
        if not region:
            region = self.get_region(client_ip_address)
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
    
    def __check_upgrade(self, client_version):
        # check last version number against client version number
        # assumes versions list is in ascending version order
        if not self.__client_versions:
            return None
        last_version = self.__client_versions[-1].version
        if int(last_version) > int(client_version):
            return last_version
        return None    
    
    def handshake(self, server_ip_address, client_ip_address,
                  propagation_channel_id, sponsor_id, client_version, event_logger=None):
        # Handshake output is a series of Name:Value lines returned to the client
        output = []
    
        # Give client a set of landing pages to open when connection established
        homepage_urls = self.__get_sponsor_home_pages(sponsor_id, client_ip_address)
        for homepage_url in homepage_urls:
            output.append('Homepage: %s' % (homepage_url,))
    
        # Tell client if an upgrade is available
        upgrade_client_version = self.__check_upgrade(client_version)
        if upgrade_client_version:
            output.append('Upgrade: %s' % (upgrade_client_version,))
    
        # Discovery
        encoded_server_list, expected_egress_ip_addresses = \
                    self.__get_encoded_server_list(
                                                propagation_channel_id,
                                                client_ip_address,
                                                event_logger=event_logger)
        for encoded_server_entry in encoded_server_list:
            output.append('Server: %s' % (encoded_server_entry,))
    
        # VPN relay protocol info
        # Note: this is added in the handshake handler in psi_web
        # output.append(psi_psk.set_psk(self.server_ip_address))
    
        # SSH relay protocol info
        #
        # SSH Session ID is a randomly generated unique ID used for
        # client-side session duration reporting
        #
        server = filter(lambda x : x.ip_address == server_ip_address,
                        self.__servers.itervalues())[0]
        if server.ssh_host_key:
            output.append('SSHPort: %s' % (server.ssh_port,))
            output.append('SSHUsername: %s' % (server.ssh_username,))
            output.append('SSHPassword: %s' % (server.ssh_password,))
            key_type, host_key = server.ssh_host_key.split(' ')
            assert(key_type == 'ssh-rsa')
            output.append('SSHHostKey: %s' % (host_key,))
            output.append('SSHSessionID: %s' % (binascii.hexlify(os.urandom(8)),))
            # Obfuscated SSH fields are optional
            if server.ssh_obfuscated_port:
                output.append('SSHObfuscatedPort: %s' % (server.ssh_obfuscated_port,))
                output.append('SSHObfuscatedKey: %s' % (server.ssh_obfuscated_key,))

        # Additional Configuration
        # Extra config is JSON-encoded.
        # Give client a set of regexes indicating which pages should have individual stats
        config = {}
        
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
        
        output.append('Config: ' + json.dumps(config))
        
        return output
    
    def get_host_by_provider_id(self, provider_id):
        for host in self.__hosts.itervalues():
            if host.provider_id and host.provider_id == provider_id:
                return host
    
    def get_hosts(self):
        return list(self.__hosts.itervalues())
        
    def get_servers(self):
        return list(self.__servers.itervalues())
    
    def __compartmentalize_data_for_host(self, host_id, discovery_date=datetime.datetime.now()):
        # Create a compartmentalized database with only the information needed by a particular host
        # - all propagation channels because any client may connect to servers on this host
        # - servers data
        #   omit discovery servers not on this host whose discovery time period has elapsed
        #   also, omit propagation servers not on this host
        #   (not on this host --> because servers on this host still need to run, even if not discoverable)
        # - send home pages for all sponsors, but omit names, banners, campaigns
        # - send versions info for upgrades

        copy = PsiphonNetwork()

        for propagation_channel in self.__propagation_channels.itervalues():
            copy.__propagation_channels[propagation_channel.id] = PropagationChannel(
                                                                    propagation_channel.id,
                                                                    '', # Omit name
                                                                    '') # Omit mechanism type

        for server in self.__servers.itervalues():
            if ((server.discovery_date_range and server.host_id != host_id and server.discovery_date_range[1] <= discovery_date) or
                (not server.discovery_date_range and server.host_id != host_id)):
                continue
            
            copy.__servers[server.id] = Server(
                                                server.id,
                                                '', # Omit host_id
                                                server.ip_address,
                                                server.egress_ip_address,
                                                server.propagation_channel_id,
                                                server.is_embedded,
                                                server.discovery_date_range,
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
                                '', # Omit name
                                '', # Omit banner
                                {},
                                [], # Omit campaigns
                                sponsor.page_view_regexes,
                                sponsor.https_request_regexes) 
            for region, home_pages in sponsor.home_pages.iteritems():
                copy_sponsor.home_pages[region] = home_pages
            copy.__sponsors[copy_sponsor.id] = copy_sponsor

        for client_version in self.__client_versions:
            copy.__client_versions.append(ClientVersion(
                                            client_version.version,
                                            '')) # Omit description

        return jsonpickle.encode(copy)

    def __compartmentalize_data_for_stats_server(self):
        # The stats server needs to be able to connect to all hosts and needs
        # the information to replace server IPs with server IDs, sponsor IDs
        # with names and propagation IDs with names
        
        copy = PsiphonNetwork()
    
        for host in self.__hosts.itervalues():
            copy.__hosts[host.id] = Host(
                                            host.id,
                                            '', # Omit: provider isn't needed
                                            '', # Omit: provider id isn't needed
                                            host.ip_address,
                                            host.ssh_port,
                                            '', # Omit: root ssh username
                                            '', # Omit: root ssh password
                                            host.ssh_host_key,
                                            host.stats_ssh_username,
                                            host.stats_ssh_password)

        for server in self.__servers.itervalues():
            copy.__servers[server.id] = Server(
                                            server.id,
                                            server.host_id,
                                            server.ip_address)
                                            # Omit: propagation, web server, ssh info
    
        for propagation_channel in self.__propagation_channels.itervalues():
            copy.__propagation_channels[propagation_channel.id] = PropagationChannel(
                                        propagation_channel.id,
                                        propagation_channel.name,
                                        [])
                                        # Omit mechanism info

        for sponsor in self.__sponsors.itervalues():
            copy.__sponsors[sponsor.id] = Sponsor(
                                        sponsor.id,
                                        sponsor.name,
                                        '',
                                        {},
                                        [],
                                        [],
                                        []) # Omit banner, home pages, campaigns, regexes

        return jsonpickle.encode(copy)

    def run_command_on_host(self, host, command):
        ssh = psi_ssh.SSH(
                host.ip_address, host.ssh_port,
                host.ssh_username, host.ssh_password,
                host.ssh_host_key)

        ssh.exec_command(command)

    def __test_server(self, server, test_web_server, test_vpn, test_ssh):
        return psi_ops_test.test_server(
                                server.ip_address,
                                server.web_server_port,
                                server.web_server_secret,
                                [self.__get_encoded_server_entry(server)],
                                self.__client_versions[-1].version,
                                [server.egress_ip_address],
                                test_web_server,
                                test_vpn,
                                test_ssh)

    def __test_servers(self, servers, test_web_server, test_vpn, test_ssh):
        results = {}
        passes = 0
        failures = 0
        for server in servers:
            result = self.__test_server(server, test_web_server, test_vpn, test_ssh)
            results[server.id] = result
            for test_result in result.itervalues():
                if 'FAIL' in test_result:
                    failures += 1
                else:
                    passes += 1
        pprint.pprint(results)
        print 'servers tested: %d' % (len(servers),)
        print 'tests passed:   %d' % (passes,)
        print 'tests failed:   %d' % (failures,)
        print 'SUCCESS' if failures == 0 else 'FAIL'
        assert(failures == 0)
        
    def test_server(self, server_id, test_web_server=True, test_vpn=True, test_ssh=True):
        if not server_id in self.__servers:
            print 'Server "%s" not found' % (server_id,)
        elif self.__servers[server_id].propagation_channel_id == None:
            print 'Server "%s" does not have a propagation channel id' % (server_id,)
        else:
            servers = [self.__servers[server_id]]
            self.__test_servers(servers, test_web_server, test_vpn, test_ssh)

    def test_host(self, host_id, test_web_server=True, test_vpn=True, test_ssh=True):
        if not host_id in self.__hosts:
            print 'Host "%s" not found' % (host_id,)
        else:
            servers = [server for server in self.__servers.itervalues() if server.host_id == host_id and server.propagation_channel_id != None]
            self.__test_servers(servers, test_web_server, test_vpn, test_ssh)

    def test_propagation_channel(self, propagation_channel_name, test_web_server=True, test_vpn=True, test_ssh=True):
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)
        servers = [server for server in self.__servers.itervalues() if server.propagation_channel_id == propagation_channel.id]
        self.__test_servers(servers, test_web_server, test_vpn, test_ssh)

    def test_sponsor(self, sponsor_name, test_web_server=True, test_vpn=True, test_ssh=True):
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        propagation_channel_ids = set()
        for campaign in sponsor.campaigns:
            propagation_channel_ids.add(campaign.propagation_channel_id)
        servers = [server for server in self.__servers.itervalues()
                   if server.propagation_channel_id in propagation_channel_ids]
        self.__test_servers(servers, test_web_server, test_vpn, test_ssh)
                    
    def test_servers(self, test_web_server=True, test_vpn=True, test_ssh=True):
        servers = [server for server in self.__servers.itervalues() if server.propagation_channel_id != None]
        self.__test_servers(servers, test_web_server, test_vpn, test_ssh)

    def save(self):
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
    psinet.save()


def edit():
    # Lock an existing network object, interact with it, then save changes
    print 'loading...'
    psinet = PsiphonNetwork.load()
    psinet.show_status()
    import code
    try:
        code.interact(
                'Psiphon 3 Console\n'+
                '-----------------\n'+
                'Interact with the \'psinet\' object...\n', local=locals())
    except SystemExit as e:
        pass
    psinet.release()


if __name__ == "__main__":
    edit()
