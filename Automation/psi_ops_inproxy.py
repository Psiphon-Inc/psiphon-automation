#!/usr/bin/python
#
# Copyright (c) 2024, Psiphon Inc.
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

import json
import os
import textwrap

import psi_ops_deploy
import psi_ops_inproxy_tools
import psi_ssh


INPROXY_DIRECTORY_NAME = '/opt/psiphon/inproxy'
INPROXY_CONFIG_FILE_NAME = '/opt/psiphon/inproxy/psiphon-inproxy.config'
INPROXY_SERVER_LIST_FILE_NAME = '/opt/psiphon/inproxy/serverlist'
INPROXY_TEMP_BINARY_FILE_NAME = '/opt/psiphon/inproxy/psiphon-inproxy.tmp'
INPROXY_BINARY_FILE_NAME = '/opt/psiphon/inproxy/psiphon-inproxy'
INPROXY_WORKING_DIRECTORY_NAME = '/var/lib/psiphon'


def setup_host(host, propagation_channel_id, sponsor_id, serverlist, ssh_ip_address_whitelist):
    host.is_inproxy=True
    if not host.inproxy_proxy_session_private_key:
        host.inproxy_proxy_session_private_key, host.inproxy_proxy_public_key = psi_ops_inproxy_tools.generate_inproxy_key_pair()
    
    install_firewall_rules(host, ssh_ip_address_whitelist)
    deploy_implementation(host, propagation_channel_id, sponsor_id, serverlist)


def deploy_implementation(host, propagation_channel_id, sponsor_id, serverlist):

    print('deploy inproxy implementation to host %s...' % (host.id,))

    ssh = psi_ssh.SSH(
                    host.ip_address, host.ssh_port,
                    host.ssh_username, host.ssh_password,
                    host.ssh_host_key)

    try:
        # Upload binary (to temp location) and config
        ssh.exec_command('mkdir -p %s' % (INPROXY_DIRECTORY_NAME,))
        psi_ops_deploy.put_file_with_content(
            ssh,
            make_inproxy_config(host, propagation_channel_id, sponsor_id),
            INPROXY_CONFIG_FILE_NAME)
        psi_ops_deploy.put_file_with_content(
            ssh,
            serverlist,
            INPROXY_SERVER_LIST_FILE_NAME)
        ssh.put_file(os.path.join(os.path.abspath('..'), 'Server', 'inproxy', 'psiphon-inproxy'),
            INPROXY_TEMP_BINARY_FILE_NAME)

        # Set up systemd unit file
        ssh.exec_command('id -u psiphon &>/dev/null || useradd -s /usr/sbin/nologin psiphon')
        ssh.exec_command('mkdir -p %s' % (INPROXY_WORKING_DIRECTORY_NAME,))
        ssh.exec_command('chown psiphon:psiphon %s' % (INPROXY_WORKING_DIRECTORY_NAME,))
        psi_ops_deploy.put_file_with_content(
            ssh,
            make_systemd_unit_file(),
            '/etc/systemd/system/psiphon-inproxy.service')
        ssh.exec_command('systemctl daemon-reload')

        # Move binary and restart inproxy
        ssh.exec_command('systemctl stop psiphon-inproxy')
        ssh.exec_command('mv %s %s' % (INPROXY_TEMP_BINARY_FILE_NAME, INPROXY_BINARY_FILE_NAME,))
        ssh.exec_command('chmod +x %s' % (INPROXY_BINARY_FILE_NAME,))
        ssh.exec_command('systemctl enable psiphon-inproxy')
        ssh.exec_command('systemctl start psiphon-inproxy')
        
    finally:
        ssh.close()


def make_inproxy_config(host, propagation_channel_id, sponsor_id):
    config = {}
    config['PropagationChannelID'] = propagation_channel_id
    config['SponsorID'] = sponsor_id
    config['EmitDiagnosticNotices'] = True
    config['DisableTunnels'] = True
    config['InproxyEnableProxy'] = True
    config['InproxyMaxClients'] = 200
    config['InproxyProxySessionPrivateKey'] = host.inproxy_proxy_session_private_key
    config['InproxyDisableSTUN'] = True
    config['UseNoticeFiles'] = {'RotatingFileSize' : 1000000000, 'RotatingSyncFrequency' : 10000}
    return json.dumps(config)


def make_systemd_unit_file():
    return textwrap.dedent('''
        [Unit]
        Description=Psiphon Inproxy
        
        # Wait until network start
        Wants=network-online.target
        After=network.target network-online.target

        [Service]
        # Use the default service type
        Type=simple
        User=psiphon

        # Allow up to 'TimeoutStartSec' seconds to report as started prior
        # to marking the service as failed. Setting to 0 allows unlimited time
        TimeoutStartSec=30

        # Restart automatically on failure
        Restart=always

        # Use the sourced environment variables to launch the container
        WorkingDirectory={inproxy_working_dir}
        ExecStart={inproxy_binary} -config {inproxy_config} -serverList {server_list}

        # Execute these commands when stopping the service
        ExecStop=/bin/kill -s SIGTERM $MAINPID

        [Install]
        # "multi-user.target" refers to the system being at runlevel 3
        WantedBy=multi-user.target
    '''.format(
        inproxy_working_dir = INPROXY_WORKING_DIRECTORY_NAME,
        inproxy_binary = INPROXY_BINARY_FILE_NAME,
        inproxy_config = INPROXY_CONFIG_FILE_NAME,
        server_list = INPROXY_SERVER_LIST_FILE_NAME))


def install_firewall_rules(host, ssh_ip_address_whitelist):

    if ssh_ip_address_whitelist:
        management_port_rules = [
            '-A INPUT -s {whitelist_ip_address} -p tcp -m state --state NEW -m tcp --dport {management_port} -j ACCEPT'.format(
                whitelist_ip_address=whitelist_ip, management_port=host.ssh_port)
            for whitelist_ip in ssh_ip_address_whitelist]
    else:
        management_port_rules = [
            '-A INPUT -p tcp -m state --state NEW -m tcp --dport {management_port} -j ACCEPT'.format(management_port=host.ssh_port)
        ]
        
    filter_input_rules = [
        '-A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT',
        '-A INPUT -s 127.0.0.0/8 ! -i lo -j DROP',
        '-A INPUT -d 127.0.0.0/8 ! -i lo -j DROP',
    ] + management_port_rules + [
        '-A INPUT -p tcp -j REJECT --reject-with tcp-reset',
        '-A INPUT -p udp -m udp --dport 68 -j DROP',
        '-A INPUT -p udp -j ACCEPT',
        '-A INPUT -j DROP'
    ]
    
    filter_output_rules = [
        '-A OUTPUT -s 127.0.0.0/8 ! -o lo -j DROP',
        '-A OUTPUT -d 127.0.0.0/8 ! -o lo -j DROP',
        '-A OUTPUT -j ACCEPT'
    ]
    
    iptables_rules_path = '/etc/iptables.rules'
    iptables_rules_contents = textwrap.dedent('''
        *filter
        {filter_input}
        {filter_output}
        COMMIT
        ''').format(
            filter_input='\n'.join(filter_input_rules),
            filter_output='\n'.join(filter_output_rules))
            
    if_up_script_path = '/etc/network/if-up.d/firewall'
    if_up_script_contents = textwrap.dedent('''
            #!/bin/sh

            iptables-restore < {iptables_rules_path}
            systemctl list-jobs | grep -q network.target || systemctl restart fail2ban.service
            ''').format(iptables_rules_path=iptables_rules_path).strip()
                
    ssh = psi_ssh.SSH(
            host.ip_address, host.ssh_port,
            host.ssh_username, host.ssh_password,
            host.ssh_host_key)

    try:
        ssh.exec_command('echo "{iptables_rules_contents}" > {iptables_rules_path}'.format(
            iptables_rules_contents=iptables_rules_contents, iptables_rules_path=iptables_rules_path))
        ssh.exec_command('echo "{if_up_script_contents}" > {if_up_script_path}'.format(
            if_up_script_contents=if_up_script_contents, if_up_script_path=if_up_script_path))
        ssh.exec_command('chmod +x {if_up_script_path}'.format(if_up_script_path=if_up_script_path))
        ssh.exec_command(if_up_script_path)
    
    finally:
        ssh.close()

