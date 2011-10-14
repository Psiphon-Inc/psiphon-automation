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
import psi_utils
import psi_cms
import psi_templates
import psi_s3
import psi_twitter

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
    'propagation_channel_id, propagation_mechanism_type, account, s3_bucket_root_url')

Host = psi_utils.recordtype(
    'Host',
    'id, hostname, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key, '+
    'stats_ssh_username, stats_ssh_password')

Server = psi_utils.recordtype(
    'Server',
    'id, host_id, ip_address, propagation_channel_id, discovery_date_range, '+
    'web_server_port, web_server_secret, web_server_certificate, web_server_private_key, '+
    'ssh_port, ssh_username, ssh_password, ssh_host_key')

ClientVersion = psi_utils.recordtype(
    'ClientVersion',
    'version, description')

AwsAccount = psi_utils.recordtype(
    'AwsAcount',
    'access_id, secret_key')

LinodeAccount = psi_utils.recordtype(
    'LinodeAccount',
    'api_key')

EmailServerAccount = psi_utils.recordtype(
    'EmailServerAccount',
    'ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key')

StatsServerAccount = psi_utils.recordtype(
    'StatsServerAccount',
    'ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key')


class PsiphonNetwork(psi_cms.PersistentObject):

    def __init__(self):
        self.temp = LinodeAccount('key')
        self.__version = '1.0'
        self.__propagation_mechanisms = {
            'twitter' : PropagationMechanism('twitter'),
            'email-autoresponder' : PropagationMechanism('email-autoresponder'),
            'download-widget' : PropagationMechanism('download-widget')
        }
        self.__propagation_channels = {}
        self.__sponsors = {}
        self.__hosts = {}
        self.__servers = {}
        self.__client_versions = []
        self.__email_server_account = None
        self.__aws_account = None
        self.__linode_account = None
        self.__server_deploy_required = False
        self.__email_push_required = False

    def __del__(self):
        # TODO: prompt -- deploy_req, email_req, save_required
        pass

    def list_status(self):
        # TODO: output counts, requireds
        pass

    def __generate_id(self):
        count = 16
        chars = '0123456789ABCDEF'
        return ''.join([chars[ord(os.urandom(1))%len(chars)] for i in range(count)])

    def list_propagation_channels(self):
        for propagation_channel in self.propagation_channels:
            self.list_propagation_channel(propagation_channel.name)

    def list_propagation_channel(self, name):
        # TODO: custom print, associated server details
        pprint.PrettyPrinter.pprint(slef.__get_propagation_channel_by_name(name))

    def __get_propagation_channel_by_name(self, name):
        propagation_channel = filter(lambda x:x.name == name,
                                     self.__propagation_channels.itervalues())[0]

    def add_propagation_channel(self, name, propagation_mechanism_types):
        id = self.__generate_id()
        for type in propagation_mechanism_types: assert(type in self.__propagation_mechanisms)
        propagation_channel = PropagationChannel(id, name, propagation_mechanism_types)
        assert(not filter(lambda x:x.name == name, self.__propagation_channels.itervalues()))
        self.__propagation_channels[id] = propagation_channel

    def list_sponsors(self):
        for sponsor in self.__sponsors:
            self.list_sponsor(sponsor.name)

    def list_sponsor(self, name):
        # TODO: custom print, campaign mechanisms
        pprint.PrettyPrinter.pprint(self.__get_sponsor_by_name(name))

    def __get_sponsor_by_name(self, name):
        sponsor = filter(lambda x:x.name == name,
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
                                   EmailPropagationAccount(email_account))
        if campaign not in sponsor.campaigns:
            sponsor.campaigns.append(campaign)
            sponsor.log('add email campaign %s' % (email_account,))
            self.__server_deploy_required = True

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
                                        twitter_account_access_token_secret))
        if campaign not in sponsor.campaigns:
            sponsor.campaigns.append(campaign)
            sponsor.log('add email campaign %s' % (email_account,))
            self.__server_deploy_required = True

    def set_sponsor_home_page(self, sponsor_name, region, url):
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        home_page = SponsorHomePage(region, url)
        if home_page not in sponsor.home_pages[region]:
            sponsor.home_pages[region].append(home_page)
            sponsor.log('set home page %s for %s', (url, region))
            self.__server_deploy_required = True
    
    def remove_sponsor_home_page(self, sponsor_name, region, url):
        sponsor = self.__get_sponsor_by_name(sponsor_name)
        home_page = SponsorHomePage(region, url)
        if home_page in sponsor.home_pages[region]:
            sponsor.home_pages[region].remove(home_page)
            sponsor.log('deleted home page %s for %s', (url, region))
            self.__server_deploy_required = True

    def add_server(self, propagation_channel_name, discovery_date_range):
        propagation_channel = self.__get_propagation_channel_by_name(propagation_channel_name)

        is_propagation_server = (discovery_date_range is None)

        # Create a new cloud VPS
        host = Host(*psi_linode.launch_new_server(self.__linode_account))

        # Install Psiphon 3 and generate configuration values
        server_config = psi_install.install(host.ip_address,
                                            host.ssh_port,
                                            host.ssh_username,
                                            host.ssh_password,
                                            host.ssh_host_key)

        # Update database

        # Add new server (we also add a host; here, the host and server are
        # one-to-one, but legacy networks have many servers per host and we
        # retain support for this in the data model and general functionality)
        assert(host.hostname not in self.__hosts)
        self.__hosts[hostname] = host
        server = Server(server_config[0],
                        host.id,
                        host.ip_address,
                        propagation_channel.id,
                        discovery_date_range,
                        *server_config[1:])
        assert(server.id not in self.__servers)
        self.__servers[server.id] = servers

        # If it's a propagation server, FFFF-out old one (it's still run, but
        # not embedded in builds or discovered)
        if is_propagation_server:
            for server in self.__servers.itervalues():
                if (server.propagation_channel_id == propagation_channel.id and
                    server.discovery_date_range is None):
                    server.propagation_channel_id = 'FFFFFFFF'
                    server.log('FFFF\'d out')

        self.__server_deploy_required = True

        # Ensure new configuration is saved to CMS before deploying new
        # server info to the network
        self.save()

        # Do the server deploy before we propagate
        self.deploy_servers()

        # Unless the node is reserved for discovery, release it through
        # the campaigns associated with the propagation channel
        # TODO: recover from partially complete state...
        if is_propagation_server:
            for sponsor in self.__sponsors.itervalues():
                build_filename = None
                for campaign in sponsor.campaigns:
                    if campaign.propagation_channel_id == propagation_channel.id:
                        if build_filename == None:
                            build_filename = psi_build.build(sponsor.id, propagation_channel.id)
                        s3_bucket_root_url = psi_s3.publish_s3_bucket(build_filename)
                        campaign.log('published s3 bucket %s', (s3_bucket_root_url,))
                        if campaign.propagation_mechanism_type == 'twitter':
                            message = psi_templates.get_tweet_message(s3_bucket_root_url)
                            psi_twitter.tweet(campaign.account, message)
                            campaign.log('tweeted')
                        elif campaign.propagation_mechanism_type == 'email-autoresponder':
                            campaign.s3_bucket_root_url = s3_bucket_root_url
                            if not self.__email_push_required:
                                self.__email_push_required = True
                                campaign.log('email push scheduled')
                        else:
                            print bucket_url
            propagation_channel.log('propagated')

        # TODO: self.save()...?

        # Push an updated email config
        if self.__email_push_required:
            self.push_email()

    def list_servers(self):
        for server in self.__servers.itervalues():
            self.list_server(server.id)

    def list_server(self, id):
        # TODO: custom print, campaign mechanisms
        pprint.PrettyPrinter.pprint(self.__servers[id])

    def test_servers(self, test_connections=False):
        for server in self.__servers.itervalues():
            self.test_server(server.id, test_connections)

    def test_server(self, id, test_connections=False):
        # TODO: psi_test
        pass

    def deploy_servers(self):
        for server in self.__servers.itervalues():
            self.deploy_server(server.id)
        # TODO:
        # ...make stats server subset db
        # ...push to stats server

    def deploy_server(self, id):
        # TODO: psi_deploy
        # ...pass database subset into deploy
        # ...server.log('deployed')
        pass

    def push_email(self):
        # Generate the email server config file, which is a JSON format
        # mapping every request email to a response body containing
        # download links.
        # Currently, we generate the entire config file for any change.
        
        emails = []
        for sponsor in self.__sponsors.itervalues():
            for campaign in sponsor.campaigns:
                if campaign.propagation_mechanism_type == 'email-autoresponder':
                    subject, body = psi_templates.get_email_content(
                                        campaign.s3_bucket_root_url)
                    emails.append(
                        campaign.account.email_address, subject, body)

        with tempfile.NamedTemporaryFile() as file:
            file.write(json.dumps(emails))
            ssh = psi_ssh.SSH(*self.__email_server_account)
            ssh.put_file(temp_file.name, EMAIL_SERVER_CONFIG_FILE_PATH)
            self.__email_server_account.log('pushed')

        self.__email_push_required = False
        # TODO: self.save()...?

    def add_version(self, description):
        next_version = 1
        if len(self.__client_versions) > 0:
            next_version = int(self.__client_versions[-1].version)+1
        client_version = Client(str(next_version), description)
        self.__client_versions.add(client_version)
        print 'latest version: %d' % (next_version,)


    def set_aws_account(self, access_id, secret_key):
        self.__aws_account.access_id = access_id
        self.__aws_account.secret_key = secret_key
        self.__aws_account.log('set to %s' % (access_id,))

    def set_linode_account(self, api_key):
        self.__linode_account.api_key = api_key
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
        return [get_encoded_server_entry(server) for server in servers]
        
    def __get_region(self, client_ip_address):
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
            region = self.__get_region(client_ip_address)
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
    
    def __get_discovery_propagation_channel_ids_for_host(self, host_id,
                                                         discovery_date=datetime.datetime.now()):
        servers_on_host = filter(lambda x : x.host_id == host_id, self.__servers)
        # Servers with blank propagation channels are inactive
        return set([server.propagation_channel_id for server in servers_on_host if server.propagation_channel_id])
    
    # TODO...
    #def get_egress_ip_address_for_server(server):
    #    # egress IP address is host's IP address
    #    hosts = get_hosts()
    #    return filter(lambda x : x.Host_ID == server.Host_ID, hosts)[0].IP_Address
    
    def compartmentalize_data_for_host(self, host_id, filename,
                                       discovery_date=datetime.datetime.now()):
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

        for id in self.__get_discovery_propagation_channel_ids_for_host(host_id):
            propagation_channel = self.__propagation_channels[id]
            copy.propagation_channels[propagation_channel.id] = PropagationChannel(
                                                                    propagation_channel.id,
                                                                    None, # Omit name
                                                                    None) # Omit mechanism type

        for server in self.__servers:
            if (server.Discovery_Propagation_Channel_ID in discovery_propagation_channel_ids_on_host and
                    not(server.Discovery_Time_Start and server.Host_ID != host_id and server.Discovery_Time_End <= discovery_date) and
                    not(server.Discovery_Time_Start is None and server.Host_ID != host_id)):
                copy.servers[server.id] = Server(
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
    
        for sponsor in self.__sponsors:
            copy_sponsor = Sponsor(
                                sponsor.id,
                                None, # Omit name
                                None, # Omit banner
                                collections.defaultdict(list),
                                None) # Omit campaigns
            for region, home_pages in sponsor.home_pages:
                # Completely copy all home pages
                copy_sponsor.home_pages[region].extend(home_pages)
            copy.sponsors[copy_sponsor.id] = copy_sponsor

        for client_version in self.__client_versions:
            copy.client_versions.append(Version(
                                            client_version.version,
                                            None)) # Omit description
    
        return cPickle.dumps(copy)

    def compartmentalize_data_for_stats_server(self):
        # The stats server needs to be able to connect to all hosts and needs
        # the information to replace server IPs with server IDs, sponsor IDs
        # with names and propagation IDs with names
        
        copy = PsiphonNetwork()
    
        for host in self.__hosts:
            copy.hosts[copy_host.id] = Host(
                                        host.id,
                                        host.ip_address,
                                        host.ssh_port,
                                        '', # Omit: root ssh username
                                        '', # Omit: root ssh password
                                        host.ssh_host_key,
                                        host.stats_ssh_username,
                                        host.stats_ssh_password)

        for server in self.__servers:
            copy.servers[server.id] = Server(
                                        server.id,
                                        server.host_id,
                                        server.ip_address)
                                        # Omit: propagation, web server, ssh info
    
        for propagation_channel in self.__propagation_channels:
            copy.propagation_channels[copy_propagation_channel.id] = Sponsor(
                                        propagation_channel.id,
                                        propagation_channel.name)
                                        # Omit mechanism info

        for sponsor in self.__sponsors:
            copy.sponsors[copy_sponsor.id] = Sponsor(
                                        sponsor.id,
                                        sponsor.name)
                                        # Omit banner, home pages, campaigns

        return cPickle.dumps(copy)


def test():
    psinet = PsiphonNetwork()
    psinet.add_propagation_channel('email-channel', ['email-autoresponder'])
    psinet.add_sponsor('sponsor1')
    psinet.list_sponsors()
    psinet.set_sponsor_home_page('sponsor1', 'CA', 'http://psiphon.ca')
    psinet.add_sponsor_email_campaign('sponsor1', 'email-channel', 'get@psiphon.ca')
    psinet.list_sponsors()
    print cPickle.dumps(psinet)


if __name__ == "__main__":
    test()
