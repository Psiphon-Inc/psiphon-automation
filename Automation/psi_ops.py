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

import cPickle
import time
import psi_utils
import psi_templates
import psi_s3
import psi_twitter


PropagationChannel = psi_utils.recordtype(
    'PropagationChannel',
    'id, name, propagation_mechanism_types')

PropagationMechanism = psi_utils.recordtype(
    'PropagationMechanism',
    'type')

TwitterPropagationAccount = psi_utils.record_type(
    'TwitterPropagationAccount',
    'name, consumer_key, consumer_secret, access_token_key, access_token_secret')

EmailPropagationAccount = psi_utils.record_type(
    'EmailPropagationAccount',
    'email_address')

Sponsor = psi_utils.record_type(
    'Sponsor',
    'id, name, banner, home_pages, campaigns')

SponsorHomePage = psi_utils.record_type(
    'SponsorHomePage',
    'region, url')

SponsorCampaign = psi_utils.record_type(
    'SponsorCampaign',
    'propagation_channel_id, propagation_mechanism_type, account')

Host = psi_utils.record_type(
    'Host',
    'id, hostname, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key')

Server = psi_utils.record_type(
    'Server',
    'id, host_id, ip_address, propagation_channel_id, discovery_date_range, '+
    'web_server_port, web_server_secret, web_server_certificate, web_server_private_key, '+
    'ssh_port, ssh_username, ssh_password, ssh_host_key')

Version = psi_utils.record_type(
    'Version',
    'client_version, description')

AwsAccount = psi_utils.record_type(
    'AwsAcount',
    'id, access_id, secret_key')

LinodeAccount = psi_utils.record_type(
    'LinodeAccount',
    'id, api_key')

EmailServerAccount = psi_utils.record_type(
    'EmailServerAccount',
    'ssh_port, ssh_username, ssh_password, ssh_host_key')


class PsiphonNetwork(psi_utils.PersistentObject):

    def __init__(self):
        self.version = '1.0'
        self.propagation_mechanisms = {
            'twitter' : PropagationMechanism('twitter'),
            'email-autoresponder' : PropagationMechanism('email-autoresponder')
        }
        self.propagation_channels = {}
        self.sponsors = {}
        self.hosts = {}
        self.servers = {}
        self.versions = {}
        self.email_server_account = None
        self.aws_account = None
        self.linode_account = None
        self.server_deploy_required = False
        self.email_push_required = False

    def list_status(self):
        # output counts, requireds
        pass

    def add_propagation_channel(self, name, propagation_mechanism_types):
        id = self.__generate_id()
        for type in propagation_mechanism_types: assert(type in self.propagation_mechanisms)
        propagation_channel = PropagationChannel(id, name, propagation_mechanism_types)
        assert(name not in self.propagation_channels)
        self.propagation_channels[name] = propagation_channel

    def list_propagation_channels(self):
        for propagation_channel in self.propagation_channels:
            self.list_propagation_channel(propagation_channel)

    def list_propagation_channel(self, name):
        # TODO: pretty print, print node details
        print self.propagation_channels[name]

    def list_sponsors(self):
        for sponsor in self.sponsors:
            self.list_sponsor(sponsor)

    def list_sponsor(self, name):
        #...incl campagain mechanisms, logs
        pass

    def add_sponsor(self, name):
        id = self.__generate_id()
        sponsor = Sponsor(id, name)
        assert(name not in self.sponsors)
        self.sponsors[name] = sponsor

    def set_sponsor_banner(self, name, banner_filename):
        with open(banner_filename, 'rb') as file:
            banner = file.read()
        sponsor = self.sponsors[name]
        sponsor.banner = banner
        sponsor.log('set banner')

    def add_sponsor_email_campaign(self, sponsor_name,
                                   propagation_channel_name,
                                   email_account):
        sponsor = self.sponsors[sponsor_name]
        propagation_channel = self.propagation_channels[propagation_channel_name]
        propagation_mechanism_type = 'email-autoresponder'
        assert(propagation_mechanism_type in propagation_channel.propagation_mechanism_types)
        #assert(email_account not in ...)
        campaign = SponsorCampaign(propagation_channel.id,
                                   propagation_mechanism_type,
                                   EmailPropagationAccount(email_account))
        sponsor.campaigns.append(campaign)
        sponsor.log('add email campaign %s' % (email_account,))
        self.server_deploy_required = True

    def add_sponsor_twiter_campaign(self, sponsor_name,
                                    propagation_channel_name,
                                    _):
        pass

    def set_sponsor_home_page(self, sponsor_name, region, url):
        # ...
        self.server_deploy_required = True
    
    def remove_sponsor_home_page(self, sponsor_name, region):
        # ...
        self.server_deploy_required = True

    def add_server(self, propagation_channel_name, discovery_date_range):
        propagation_channel = self.propagation_channels[propagation_channel_name]

        # Create a new cloud VPS
        host = Host(*psi_linode.deploy_server())
        host.log('created')

        # Install Psiphon 3 and generate configuration values
        server_config = psi_install.install(host.ip_address,
                                            host.ssh_port,
                                            host.ssh_username,
                                            host.ssh_password,
                                            host.ssh_host_key)

        # Update database
        assert(host.hostname not in self.hosts)
        self.hosts[hostname] = host
        server = Server(server_config[0],
                        host.id,
                        host.ip_address,
                        propagation_channel.id,
                        discovery_date_range,
                        *server_config[1:])
        server.log('created')
        assert(server.id not in self.servers)
        self.servers[server.id] = servers

        self.server_deploy_required = True

        # Do the server deploy before we propagate
        self.deploy_servers()

        # Unless the node is not reserved for discovery, release it through
        # the campaigns associated with the propagation channel
        for sponsor in self.sponsors:
            build_filename = None
            for campaign in sponsor.campaigns:
                if campaign.propagation_channel_id == propagation_channel.id:
                    if build_filename == None:
                        build_filename = psi_build.build(sponsor.id, propagation_channel.id)
                    bucket_root_url = psi_s3.publish_s3_bucket(build_filename)
                    campaign.log('published s3 bucket %s', (bucket_root_url,))
                    if campaign.propagation_mechanism_type == 'twitter':
                        message = psi_templates.get_tweet_message(bucket_root_url)
                        psi_twitter.tweet(campaign.account, message)
                        campaign.log('tweeted')
                    elif campaign.propagation_mechanism_type == 'email-autoresponder':
                        self.email_push_required = True
                        campaign.log('email push scheduled')
                    else:
                        print bucket_url
        propagation_channel.log('propagated')

        # Push an updated email config
        if self.email_push_required:
            self.push_email()

    def list_servers(self):
        pass

    def test_servers(self, test_connections=False):
        pass

    def deploy_servers(self):
        # ...pass database subset into deploy
        # ...server.log('deployed')
        pass

    def push_email(self):
        # generate config
        # push to email server
        # email_server.log('pushed')
        pass

    def add_version(self):
        pass

    def set_email_server_account(self):
        pass

    def set_aws_account(self):
        pass

    def set_linode_account(self):
        pass


if __name__ == "__main__":
    test()
