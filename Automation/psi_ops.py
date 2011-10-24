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
import cPickle
import time
import datetime
import pprint
import json
import collections
import textwrap
import itertools

import psi_linode
import psi_utils
import psi_templates
import psi_ops_cms
import psi_ops_s3
import psi_ops_twitter
import psi_ops_install
import psi_ops_deploy
import psi_ops_build

try:
    import GeoIP
except ImportError:
    pass


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
    'id, name, banner, home_pages, campaigns')

SponsorHomePage = psi_utils.recordtype(
    'SponsorHomePage',
    'region, url')

SponsorCampaign = psi_utils.recordtype(
    'SponsorCampaign',
    'propagation_channel_id, propagation_mechanism_type, account, s3_bucket_name')

Host = psi_utils.recordtype(
    'Host',
    'id, provider_id, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key, '+
    'stats_ssh_username, stats_ssh_password')

Server = psi_utils.recordtype(
    'Server',
    'id, host_id, ip_address, egress_ip_address, '+
    'propagation_channel_id, is_embedded, discovery_date_range, '+
    'web_server_port, web_server_secret, web_server_certificate, web_server_private_key, '+
    'ssh_port, ssh_username, ssh_password, ssh_host_key',
    default=None)

ClientVersion = psi_utils.recordtype(
    'ClientVersion',
    'version, description')

AwsAccount = psi_utils.recordtype(
    'AwsAcount',
    'access_id, secret_key')

LinodeAccount = psi_utils.recordtype(
    'LinodeAccount',
    'api_key, base_id, base_ip_address, base_ssh_port, '+
    'base_root_password, base_stats_username, base_host_public_key, '+
    'base_known_hosts_entry, base_rsa_private_key, base_rsa_public_key, '+
    'base_tarball_path')

EmailServerAccount = psi_utils.recordtype(
    'EmailServerAccount',
    'ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key')

StatsServerAccount = psi_utils.recordtype(
    'StatsServerAccount',
    'ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key')


class PsiphonNetwork(psi_ops_cms.PersistentObject):

    def __init__(self):
        super(PsiphonNetwork, self).__init__()
        self.__version = '1.0'
        self.__sponsors = {}
        self.__propagation_mechanisms = {
            'twitter' : PropagationMechanism('twitter'),
            'email-autoresponder' : PropagationMechanism('email-autoresponder'),
            'download-widget' : PropagationMechanism('download-widget')
        }
        self.__propagation_channels = {}
        self.__hosts = {}
        self.__servers = {}
        self.__client_versions = []
        self.__email_server_account = None
        self.__stats_server_account = None
        self.__aws_account = None
        self.__linode_account = None
        self.__deploy_implementation_required_for_hosts = set()
        self.__deploy_data_required_for_all = False
        self.__deploy_builds_required_for_campaigns = set()
        self.__deploy_stats_config_required = False
        self.__deploy_email_push_required = False

    def show_status(self, verbose=False):
        # NOTE: verbose mode prints credentials to stdout
        print textwrap.dedent('''
            Sponsors:            %d
            Channels:            %d
            Twitter Campaigns:   %d
            Email Campaigns:     %d
            Hosts:               %d
            Servers:             %d
            Email Server:        %s
            Stats Server:        %s
            Client Version:      %s %s
            AWS Account:         %s
            Linode Account:      %s
            Deploys Pending:     Host Implementations    %d                              
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
                'Configured' if self.__aws_account else 'None',
                'Configured' if self.__linode_account else 'None',
                len(self.__deploy_implementation_required_for_hosts),
                'Yes' if self.__deploy_data_required_for_all else 'No',
                len(self.__deploy_builds_required_for_campaigns),
                'Yes' if self.__deploy_stats_config_required else 'No',
                'Yes' if self.__deploy_email_push_required else 'No')
        if verbose:
            def print_object(obj):
                if not obj:
                    return
                # TODO: nicer printing of recordtype objects
                pprint.PrettyPrinter().pprint(obj)
                for log_time, log_message in obj.get_logs():
                    print log_time.isoformat(), log_message
                print '\n'
            map(print_object,
                itertools.chain(
                    self.__sponsors.itervalues(),
                    self.__propagation_channels.itervalues(),
                    self.__hosts.itervalues(),
                    self.__servers.itervalues(),
                    self.__client_versions,
                    [self.__email_server_account,
                     self.__stats_server_account,
                     self.__aws_account,
                     self.__linode_account]))
                
    def __generate_id(self):
        count = 16
        chars = '0123456789ABCDEF'
        return ''.join([chars[ord(os.urandom(1))%len(chars)] for i in range(count)])

    def __get_propagation_channel_by_name(self, name):
        return filter(lambda x:x.name == name,
                      self.__propagation_channels.itervalues())[0]

    def add_propagation_channel(self, name, propagation_mechanism_types):
        id = self.__generate_id()
        for type in propagation_mechanism_types: assert(type in self.__propagation_mechanisms)
        propagation_channel = PropagationChannel(id, name, propagation_mechanism_types)
        assert(not filter(lambda x:x.name == name, self.__propagation_channels.itervalues()))
        self.__propagation_channels[id] = propagation_channel

    def __get_sponsor_by_name(self, name):
        return filter(lambda x:x.name == name,
                      self.__sponsors.itervalues())[0]

    def add_sponsor(self, name):
        id = self.__generate_id()
        sponsor = Sponsor(id, name, None, collections.defaultdict(list), [])
        assert(not filter(lambda x:x.name == name, self.__sponsors.itervalues()))
        self.__sponsors[id] = sponsor

    def set_sponsor_banner(self, name, banner_filename):
        with open(banner_filename, 'rb') as file:
            banner = file.read()
        sponsor = self.__get_sponsor_by_name(name)
        sponsor.banner = banner
        sponsor.log('set banner')
        for campaign in sponsor.campaigns:
            self.__deploy_builds_required_for_campaigns.set(
                (sponsor.id, campaign.propagation_channel_id))
            campaign.log('marked for build and publish (new banner)')

    def add_sponsor_email_campaign(self, sponsor_name,
                                   propagation_channel_name,
                                   email_account):
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
                    (sponsor.id, campaign.propagation_channel_id))
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
            sponsor.log('add twitter campaign %s' % (email_account,))
            self.__deploy_builds_required_for_campaigns.add(
                    (sponsor.id, campaign.propagation_channel_id))
            campaign.log('marked for build and publish (new campaign)')

    def set_sponsor_home_page(self, sponsor_name, region, url):
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        home_page = SponsorHomePage(region, url)
        if home_page not in sponsor.home_pages[region]:
            sponsor.home_pages[region].append(home_page)
            sponsor.log('set home page %s for %s' % (url, region if region else 'All'))
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')
    
    def remove_sponsor_home_page(self, sponsor_name, region, url):
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        home_page = SponsorHomePage(region, url)
        if home_page in sponsor.home_pages[region]:
            sponsor.home_pages[region].remove(home_page)
            sponsor.log('deleted home page %s for %s' % (url, region))
            self.__deploy_data_required_for_all = True
            sponsor.log('marked all hosts for data deployment')

    def get_server_by_ip_address(self, ip_address):
        return filter(lambda x:x.ip_address == ip_address, self.__servers)

    def add_server(self, propagation_channel_name, discovery_date_range):
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)

        # Embedded servers (aka "propagation servers") are embedded in client
        # builds, where as discovery servers are only revealed when clients
        # connect to a server.
        is_embedded_server = (discovery_date_range is None)

        print 'starting Linode process (~5 minutes)...'

        # Create a new cloud VPS
        linode_info = psi_linode.launch_new_server(self.__linode_account)
        host = Host(*linode_info)

        server = Server(
                    None,
                    host.id,
                    host.ip_address,
                    host.ip_address,
                    propagation_channel.id,
                    is_embedded_server,
                    discovery_date_range)

        # Install Psiphon 3 and generate configuration values
        # Here, we're assuming one server/IP address per host
        existing_server_ids = [server.id for server in self.__servers]
        psi_ops_install.install_host(host, [server], existing_server_ids)
        host.log('install')

        # Deploy will upload web server source database data and client builds
        # (Only deploying for the new host, not broadcasting info yet...)
        psi_ops_deploy.deploy_implementation(host)
        psi_ops_deploy.deploy_data(
                            host,
                            self.__compartmentalize_data_for_host(host.id))
        host.log('initial deployment')

        # Update database

        # Add new server (we also add a host; here, the host and server are
        # one-to-one, but legacy networks have many servers per host and we
        # retain support for this in the data model and general functionality)
        assert(host.id not in self.__hosts)
        self.__hosts[host.id] = host
        assert(server.id not in self.__servers)
        self.__servers[server.id] = server

        # If it's a propagation server, stop embedding the old one (it's still
        # active, but not embedded in builds or discovered)
        if is_embedded_server:
            for server in self.__servers.itervalues():
                if (server.propagation_channel_id == propagation_channel.id and
                    server.is_embedded):
                    server.is_embedded = False
                    server.log('unembedded')

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
                                (sponsor.id, campaign.propagation_channel_id))
                        campaign.log('marked for build and publish (new embedded server)')

        # This deploy will broadcast server info, propagate builds, and update
        # the stats and email server
        self.deploy()

    def build_and_test(self, propagation_channel_id, sponsor_id, test=False):
        sponsor = self.__sponsors[sponsor_id]
        version = self.__client_versions[-1].version
        encoded_server_list, expected_egress_ip_addresses = \
                    self.__get_encoded_server_list(propagation_channel_id)
        
        # A sponsor may use the same propagation channel for multiple
        # campaigns; we need only build and upload the client once.
        return psi_ops_build.build(
                        propagation_channel_id,
                        sponsor_id,
                        sponsor.banner,
                        encoded_server_list,
                        expected_egress_ip_addresses,
                        version,
                        test)

    def deploy(self):

        # Ensure new server configuration is saved to CMS before deploying new
        # server info to the network

        # TODO: add need-save flag
        self.save()

        # Deploy as required:
        #
        # - Implementation to flagged hosts
        # - Data to all hosts
        # - Builds for required channels and sponsors
        # - Email and stats server config
        #
        # NOTE: Order is important. Hosts get new implementation before
        # new data, in case schema has changed; deploy new data before
        # propagating builds so servers are prepared for clients

        # Host implementation

        for host_id in self.__deploy_implementation_required_for_hosts:
            host = __self.hosts[host_id]
            psi_ops_deploy.deploy_implementation(host)
            host.log('deploy implementation')
        self.__deploy_implementation_required_for_hosts.clear()

        # Host data

        if self.__deploy_data_required_for_all:
            for host in __self.hosts.itervalues():
                psi_ops_deploy.deploy_host(
                                    host,
                                    self.__compartmentalize_data_for_host(host.id))
                host.log('deploy data')
        self.__deploy_data_required_for_all = False

        # Build and publish

        build_filenames = {}
        for target in self.__deploy_builds_required_for_campaigns:

            # Build and upload to hosts
                
            if target not in build_filenames:
                
                # A sponsor may use the same propagation channel for multiple
                # campaigns; we need only build and upload the client once.
                propagation_channel_id, sponsor_id = target
                build_filenames[target] =  build_and_test(propagation_channel_id, sponsor_id)

                # Upload client builds
                # We only upload the builds for Propagation Channel IDs that need to be known for the host.
                # UPDATE: Now we copy all builds.  We know that this breaks compartmentalization.
                # However, we do not want to prevent an upgrade in the case where a user has
                # downloaded from multiple propagation channels, and might therefore be connecting
                # to a server from one propagation channel using a build from a different one.
                for host in self.__hosts:
                    psi_ops_deploy.deploy_build(host, build_filename)
            build_filename = build_filenames[target]

            # Publish to propagation mechanisms

            sponsor_id, propagation_channel_id = target
            sponsor = self.__sponsors[sponsor_id]
            campaign = filter(lambda x:x.propagation_channel_id == propagation_channel_id, sponsor.campaigns)[0]
            s3_bucket_name = psi_s3.publish_s3_bucket(self.__aws_account, build_filename)
            campaign.log('published s3 bucket %s', (s3_bucket_name,))
            if campaign.propagation_mechanism_type == 'twitter':
                message = psi_templates.get_tweet_message(s3_bucket_name)
                psi_twitter.tweet(campaign.account, message)
                campaign.log('tweeted')
            elif campaign.propagation_mechanism_type == 'email-autoresponder':
                campaign.s3_bucket_name = s3_bucket_name
                if not self.__deploy_email_push_required:
                    self.__deploy_email_push_required = True
                    campaign.log('email push scheduled')

        self.__deploy_builds_required_for_campaigns.clear()

        # Email and stats server configs

        if self.__deploy_stats_config_required:
            self.push_stats_config()
            self.__deploy_stats_config_required = False

        if self.__email_push_required:
            self.push_email()
            self.__email_push_required = False

        # Ensure deploy flags and new propagation info (S3 bucket names)
        # are stored to CMS

        self.save()

    def push_stats_config(self):
        with tempfile.NamedTemporaryFile() as file:
            file.write(json.dumps(emails))
            ssh = psi_ssh.SSH(*self.__stats_server_account)
            ssh.put_file(temp_file.name, STATS_SERVER_CONFIG_FILE_PATH)
            self.__stats_server_account.log('pushed')

    def push_email_config(self):
        # Generate the email server config file, which is a JSON format
        # mapping every request email to a response body containing
        # download links.
        # Currently, we generate the entire config file for any change.
        
        emails = []
        for sponsor in self.__sponsors.itervalues():
            for campaign in sponsor.campaigns:
                if campaign.propagation_mechanism_type == 'email-autoresponder':
                    subject, body = psi_templates.get_email_content(
                                        campaign.s3_bucket_name)
                    campaign.log('configuring email')
                    emails.append(
                        campaign.account.email_address, subject, body)

        with tempfile.NamedTemporaryFile() as file:
            file.write(json.dumps(emails))
            ssh = psi_ssh.SSH(*self.__email_server_account)
            ssh.put_file(temp_file.name, EMAIL_SERVER_CONFIG_FILE_PATH)
            self.__email_server_account.log('pushed')

    def add_server_version(self):
        # Marks all hosts for re-deployment of server implementation
        for host in self.__hosts:
            self.__deploy_implementation_required_for_hosts.add(host.id)
            host.log('marked for implementation deployment')

    def add_client_version(self, description):
        # Records the new version number to trigger upgrades
        next_version = 1
        if len(self.__client_versions) > 0:
            next_version = int(self.__client_versions[-1].version)+1
        client_version = Client(str(next_version), description)
        self.__client_versions.add(client_version)
        # Mark deploy flag to rebuild and upload all clients
        for sponsor in self.__sponsors.itervalues():
            for campaign in sponsor.campaigns:
                self.__deploy_builds_required_for_campaigns.add(
                        (sponsor.id, campaign.propagation_channel_id))
                campaign.log('marked for build and publish (upgraded client)')

    def set_aws_account(self, access_id, secret_key):
        self.__aws_account = AwsAccount(access_id, secret_key)
        self.__aws_account.log('set to %s' % (access_id,))

    def set_linode_account(self, api_key, base_id, base_ip_address, base_ssh_port,
                           base_root_password, base_stats_username, base_host_public_key,
                           base_known_hosts_entry, base_rsa_private_key, base_rsa_public_key,
                           base_tarball_path):
        self.__linode_account = LinodeAccount(api_key, base_id, base_ip_address, base_ssh_port,
                           base_root_password, base_stats_username, base_host_public_key,
                           base_known_hosts_entry, base_rsa_private_key, base_rsa_public_key,
                           base_tarball_path)
        self.__linode_account.log('set to %s' % (api_key,))

    def set_email_server_account(self, ip_address, ssh_port,
                                 ssh_username, ssh_password, ssh_host_key):
        self.__email_server_account.ip_address = ip_address
        self.__email_server_account.ssh_port = ssh_port
        self.__email_server_account.ssh_username = ssh_username
        self.__email_server_account.ssh_password = ssh_password
        self.__email_server_account.ssh_host_key = ssh_host_key
        self.__email_server_account.log('set to %s' % (ip_address,))

    def set_stats_server_account(self, ip_address, ssh_port,
                                 ssh_username, ssh_password, ssh_host_key):
        self.__stats_server_account.ip_address = ip_address
        self.__stats_server_account.ssh_port = ssh_port
        self.__stats_server_account.ssh_username = ssh_username
        self.__stats_server_account.ssh_password = ssh_password
        self.__stats_server_account.ssh_host_key = ssh_host_key
        self.__stats_server_account.log('set to %s' % (ip_address,))

    def __get_encoded_server_entry(self, server):
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
                           not server.discovery_date_range]
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
                return []
            bucket = struct.unpack('!L',socket.inet_aton(client_ip_address))[0] % bucket_count
            servers = [servers[bucket]]
        # optional logger (used by server to log each server IP address disclosed)
        if event_logger:
            for server in servers:
                event_logger(server.ip_address)
        return ([server.egress_ip_address for server in servers],
                [get_encoded_server_entry(server) for server in servers])
        
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
        sponsor_home_pages = [home_page.url for home_page in sponsor.home_pages[region].itervalues()]
        # case: lookup failed or no corresponding region home page found --> use default
        if not sponsor_home_pages:
            sponsor_home_pages = [home_page.url for home_page in sponsor.home_pages[None].itervalues()]
        return sponsor_home_pages
    
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
        for encoded_server_entry in self.__get_encoded_server_list(
                                                propagation_channel_id,
                                                client_ip_address,
                                                event_logger=event_logger):
            output.append('Server: %s' % (encoded_server_entry,))
    
        # VPN relay protocol info
        # Note: this is added in the handshake handler in psi_web
        # output.append(psi_psk.set_psk(self.server_ip_address))
    
        # SSH relay protocol info
        server = filter(lambda x : x.ip_address == server_ip_address, self.__servers)[0]
        if server.ssh_host_key:
            output.append('SSHPort: %s' % (server.ssh_port,))
            output.append('SSHUsername: %s' % (server.ssh_username,))
            output.append('SSHPassword: %s' % (server.ssh_password,))
            key_type, host_key = server.ssh_host_key.split(' ')
            assert(key_type == 'ssh-rsa')
            output.append('SSHHostKey: %s' % (host_key,))
        return output
    
    def embed(self, propagation_channel_id):
        return get_encoded_server_list(propagation_channel_id)
    
    # TODO...
    #def get_egress_ip_address_for_server(server):
    #    # egress IP address is host's IP address
    #    hosts = get_hosts()
    #    return filter(lambda x : x.Host_ID == server.Host_ID, hosts)[0].IP_Address
    
    def __compartmentalize_data_for_host(self, host_id, discovery_date=datetime.datetime.now()):
        # Create a compartmentalized database with only the information needed by a particular host
        # - propagation channels includes only channel IDs that may connect to servers on this host
        # - servers data includes only servers for propagation channel IDs in filtered propagation channel sheet
        #   (which is more than just servers on this host, due to cross-host discovery)
        #   also, omit non-propagation servers not on this host whose discovery time period has elapsed
        #   also, omit propagation servers not on this host
        #   (not on this host --> because servers on this host still need to run, even if not discoverable)
        # - send home pages for all sponsors, but omit names, banners, campaigns
        # - send versions info for upgrades

        copy = PsiphonNetwork()

        servers_on_host = filter(lambda x : x.host_id == host_id, self.__servers)
        # Servers with blank propagation channels are inactive
        discovery_propagation_channel_ids_for_host = set([server.propagation_channel_id
                                                          for server in servers_on_host
                                                          if server.propagation_channel_id])

        for id in discovery_propagation_channel_ids_for_host:
            propagation_channel = self.__propagation_channels[id]
            copy.__propagation_channels[propagation_channel.id] = PropagationChannel(
                                                                    propagation_channel.id,
                                                                    None, # Omit name
                                                                    None) # Omit mechanism type

        for server in self.__servers.itervalues():
            if (server.propagation_channel_id in discovery_propagation_channel_ids_on_host and
                    not(server.discovery_date_range and server.host_id != host_id and server.discovery_date_range[1] <= discovery_date) and
                    not(server.is_embedded and server.host_id != host_id)):
                copy.__servers[server.id] = Server(
                                                server.id,
                                                None, # Omit host_id
                                                server.ip_address,
                                                server.propagation_channel_id,
                                                server.discovery_date_range,
                                                server.web_server_port,
                                                server.web_server_secret,
                                                server.web_server_certificate,
                                                server.web_server_private_key,
                                                server.ssh_port,
                                                server.ssh_username,
                                                server.ssh_password,
                                                server.ssh_host_key)
    
        for sponsor in self.__sponsors.itervalues():
            copy_sponsor = Sponsor(
                                sponsor.id,
                                None, # Omit name
                                None, # Omit banner
                                collections.defaultdict(list),
                                None) # Omit campaigns
            for region, home_pages in sponsor.home_pages.iteritems():
                # Completely copy all home pages
                copy_sponsor.home_pages[region].extend(home_pages)
            copy.__sponsors[copy_sponsor.id] = copy_sponsor

        for client_version in self.__client_versions:
            copy.__client_versions.append(Version(
                                            client_version.version,
                                            None)) # Omit description

        return cPickle.dumps(copy)

    def __compartmentalize_data_for_stats_server(self):
        # The stats server needs to be able to connect to all hosts and needs
        # the information to replace server IPs with server IDs, sponsor IDs
        # with names and propagation IDs with names
        
        copy = PsiphonNetwork()
    
        for host in self.__hosts.itervalues():
            copy.__hosts[copy_host.id] = Host(
                                            host.id,
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
            copy.__propagation_channels[copy_propagation_channel.id] = Sponsor(
                                        propagation_channel.id,
                                        propagation_channel.name)
                                        # Omit mechanism info

        for sponsor in self.__sponsors.itervalues():
            copy.__sponsors[copy_sponsor.id] = Sponsor(
                                        sponsor.id,
                                        sponsor.name)
                                        # Omit banner, home pages, campaigns

        return cPickle.dumps(copy)


def unit_test():
    psinet = PsiphonNetwork()
    psinet.add_propagation_channel('email-channel', ['email-autoresponder'])
    psinet.add_sponsor('sponsor1')
    psinet.set_sponsor_home_page('sponsor1', 'CA', 'http://psiphon.ca')
    psinet.add_sponsor_email_campaign('sponsor1', 'email-channel', 'get@psiphon.ca')
    psinet.show_status(verbose=True)


def create():
    # Create a new network object and persist it
    psinet = PsiphonNetwork()
    psinet.save()


def edit():
    # Lock an existing network object, interact with it, then save changes
    print 'loading...'
    psinet = PsiphonNetwork.load()
    import code
    try:
        code.InteractiveConsole(locals=locals()).interact(
                'Psiphon 3 Console\n'+
                '-----------------\n'+
                'Interact with the \'psinet\' object...\n')
    except SystemExit as e:
        pass
    print 'saving...'
    psinet.save()
    psinet.release()


if __name__ == "__main__":
    edit()
