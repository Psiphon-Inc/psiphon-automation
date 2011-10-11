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
import pprint
import json
import psi_utils
import psi_cms
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
    'propagation_channel_id, propagation_mechanism_type, account, s3_bucket_root_url')

Host = psi_utils.record_type(
    'Host',
    'id, hostname, ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key')

Server = psi_utils.record_type(
    'Server',
    'id, host_id, ip_address, propagation_channel_id, discovery_date_range, '+
    'web_server_port, web_server_secret, web_server_certificate, web_server_private_key, '+
    'ssh_port, ssh_username, ssh_password, ssh_host_key')

ClientVersion = psi_utils.record_type(
    'ClientVersion',
    'client_version, description')

AwsAccount = psi_utils.record_type(
    'AwsAcount',
    'access_id, secret_key')

LinodeAccount = psi_utils.record_type(
    'LinodeAccount',
    'api_key')

EmailServerAccount = psi_utils.record_type(
    'EmailServerAccount',
    'ip_address, ssh_port, ssh_username, ssh_password, ssh_host_key')


class PsiphonNetwork(psi_cms.PersistentObject):

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
        self.client_versions = {}
        self.email_server_account = None
        self.aws_account = None
        self.linode_account = None
        self.server_deploy_required = False
        self.email_push_required = False

    def __del__(self):
        # TODO: prompt -- deploy_req, email_req, save_required
        pass

    def list_status(self):
        # TODO: output counts, requireds
        pass

    def add_propagation_channel(self, name, propagation_mechanism_types):
        id = self.__generate_id()
        for type in propagation_mechanism_types: assert(type in self.propagation_mechanisms)
        propagation_channel = PropagationChannel(id, name, propagation_mechanism_types)
        assert(name not in self.propagation_channels)
        self.propagation_channels[name] = propagation_channel

    def list_propagation_channels(self):
        for propagation_channel in self.propagation_channels:
            self.list_propagation_channel(propagation_channel.name)

    def list_propagation_channel(self, name):
        # TODO: custom print, associated server details
        pprint.PrettyPrinter.pprint(self.propagation_channels[name])

    def list_sponsors(self):
        for sponsor in self.sponsors:
            self.list_sponsor(sponsor.name)

    def list_sponsor(self, name):
        # TODO: custom print, campaign mechanisms
        pprint.PrettyPrinter.pprint(self.sponsors[name])

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
        # TODO: assert(email_account not in ...)
        campaign = SponsorCampaign(propagation_channel.id,
                                   propagation_mechanism_type,
                                   EmailPropagationAccount(email_account),
                                   '')
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
        host = Host(*psi_linode.launch_new_server(self.linode_account))

        # Install Psiphon 3 and generate configuration values
        server_config = psi_install.install(host.ip_address,
                                            host.ssh_port,
                                            host.ssh_username,
                                            host.ssh_password,
                                            host.ssh_host_key)

        # Update database
        
        # TODO: FFFF-out
        
        assert(host.hostname not in self.hosts)
        self.hosts[hostname] = host
        server = Server(server_config[0],
                        host.id,
                        host.ip_address,
                        propagation_channel.id,
                        discovery_date_range,
                        *server_config[1:])
        assert(server.id not in self.servers)
        self.servers[server.id] = servers

        self.server_deploy_required = True

        # Ensure new configuration is saved to CMS before deploying new
        # server info to the network
        self.save()

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
                    s3_bucket_root_url = psi_s3.publish_s3_bucket(build_filename)
                    campaign.log('published s3 bucket %s', (s3_bucket_root_url,))
                    if campaign.propagation_mechanism_type == 'twitter':
                        message = psi_templates.get_tweet_message(s3_bucket_root_url)
                        psi_twitter.tweet(campaign.account, message)
                        campaign.log('tweeted')
                    elif campaign.propagation_mechanism_type == 'email-autoresponder':
                        campaign.s3_bucket_root_url = s3_bucket_root_url
                        if not self.email_push_required:
                            self.email_push_required = True
                            campaign.log('email push scheduled')
                    else:
                        print bucket_url
        propagation_channel.log('propagated')

        # TODO: self.save()...?

        # Push an updated email config
        if self.email_push_required:
            self.push_email()

    def list_servers(self):
        for server in self.servers:
            self.list_server(server.id)

    def list_server(self, id):
        # TODO: custom print, campaign mechanisms
        pprint.PrettyPrinter.pprint(self.servers[id])

    def test_servers(self, test_connections=False):
        for server in self.servers:
            self.test_server(server.id, test_connections)

    def test_server(self, id, test_connections=False):
        # TODO: psi_test
        pass

    def deploy_servers(self):
        # ...pass database subset into deploy
        # ...server.log('deployed')
        for server in self.servers:
            self.deploy_server(server.id)

    def deploy_server(self, id):
        # TODO: psi_deploy
        pass

    def push_email(self):
        # Generate the email server config file, which is a JSON format
        # mapping every request email to a response body containing
        # download links.
        # Currently, we generate the entire config file for any change.
        
        emails = []
        for sponsor in self.sponsors:
            for campaign in sponsor.campaigns:
                if campaign.propagation_mechanism_type == 'email-autoresponder':
                    subject, body = psi_templates.get_email_content(
                                        campaign.s3_bucket_root_url)
                    emails.append(
                        campaign.account.email_address, subject, body)

        with tempfile.NamedTemporaryFile() as file:
            file.write(json.dumps(emails))
            ssh = psi_ssh.SSH(*self.email_server_account)
            ssh.put_file(temp_file.name, EMAIL_SERVER_CONFIG_FILE_PATH)
            self.email_server_account.log('pushed')

        self.email_push_required = False
        # TODO: self.save()...?

    def add_version(self, description):
        next_version = 1
        if len(self.client_versions) > 0:
            next_version = int(self.client_versions[-1].client_version)+1
        client_version = Client(str(next_version), description)
        self.client_versions.add(client_version)
        print 'latest version: %d' % (next_version,)

    def set_email_server_account(self, ip_address, ssh_port,
                                 ssh_username, ssh_password, ssh_host_key):
        self.email_server_account.ip_address = ip_address
        self.email_server_account.ssh_port = ssh_port
        self.email_server_account.ssh_username = ssh_username
        self.email_server_account.ssh_password = ssh_password
        self.email_server_account.ssh_host_key = ssh_host_key
        self.email_server_account.log('changed to %s' % (ip_address,))

    def set_aws_account(self, access_id, secret_key):
        self.aws_account.access_id = access_id
        self.aws_account.secret_key = secret_key
        self.aws_account.log('changed to %s' % (access_id,))

    def set_linode_account(self, api_key):
        self.linode_account.api_key = api_key
        self.linode_account.log('changed to %s' % (api_key,))


if __name__ == "__main__":
    test()
