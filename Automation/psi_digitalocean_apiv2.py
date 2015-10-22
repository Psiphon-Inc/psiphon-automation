#!/usr/bin/python
#
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
#

import collections
import random
import string
import time
import optparse
import os
import sys

import psi_utils
import psi_ssh

import digitalocean_v2.digitalocean as digitalocean


def refresh_credentials(digitalocean_account, ip_address, new_root_password, new_stats_password):
    """
        Sets a new unique password on the droplet and removes the old ssh_host key.
        
        digitalocean_account    :   Digitalocean account details
        ip_address              :   droplet.ip_address
        new_root_password       :   new root password to set
        new_stats_password      :   new stats password to set
    """    
    # Note: using auto-add-policy for host's SSH public key here since we can't get it through the API.
    # There's a risk of man-in-the-middle.
    ssh = psi_ssh.make_ssh_session(ip_address, digitalocean_account.base_ssh_port, 'root', None, None, digitalocean_account.base_rsa_private_key)
    ssh.exec_command('echo "root:%s" | chpasswd' % (new_root_password,))
    ssh.exec_command('echo "%s:%s" | chpasswd' % (digitalocean_account.base_stats_username, new_stats_password))
    ssh.exec_command('rm /etc/ssh/ssh_host_*')
    ssh.exec_command('rm -rf /root/.ssh')
    ssh.exec_command('dpkg-reconfigure openssh-server')
    return ssh.exec_command('cat /etc/ssh/ssh_host_rsa_key.pub')


def update_system_packages(digitalocean_account, ip_address):
    """
        Updates system packages using apt.  This should only be used when
        updating the base image.
        
        digitalocean_account    :   DigitalOcean account details
        ip_address              :   droplet.ip_address
    """
    ssh = psi_ssh.make_ssh_session(ip_address, digitalocean_account.base_ssh_port, 'root', None, None, digitalocean_account.base_rsa_private_key)
    ssh.exec_command('export DEBIAN_FRONTEND=noninteractive && aptitude update -q && aptitude safe-upgrade -y -o Dpkg::Options::="--force-confdef"')
    ssh.close()


def upgrade_debian_distro(digitalocean_account, ip_address, old_version, new_version):
    '''upgrade_debian_distro is used to perform a distribution upgrade on a host.
    
    '''
    ssh = psi_ssh.make_ssh_session(ip_address, 
                                   digitalocean_account.base_ssh_port, 
                                   'root', 
                                   None, 
                                   None, 
                                   digitalocean_account.base_rsa_private_key)
    ssh.exec_command("cp /etc/apt/sources.list{,.old}")
    ssh.exec_command("sed -i 's/%s/%s/g' /etc/apt/sources.list" % (old_version, new_version))
    ssh.exec_command("sed -i 's/%s/%s/g' /etc/apt/sources.list" % (old_version, new_version))
    ssh.exec_command('export DEBIAN_FRONTEND=noninteractive && apt-get update -q && apt-get dist-upgrade -y -f -o Dpkg::Options::="--force-confdef"')
    ssh.exec_command('apt-get update && apt-get autoremove -y -f')
    ssh.exec_command('shutdown -r now')
    ssh.close()


def update_kernel(digitalocean_account, do_mgr, droplet):
    """
        This updates the kernel to use the same one as provided in the apt
        system packages.
        
        digitalocean_account    :   DigitalOcean account information
        do_mgr                  :   digitalocean.Manager
        droplet                 :   droplet details.  Gathered from droplet.load()
        
        returns:
            droplet             :   droplet details.
    """
    current_kernel_name = None
    ssh = psi_ssh.make_ssh_session(droplet.ip_address, digitalocean_account.base_ssh_port, 
                                   'root', None, None, digitalocean_account.base_rsa_private_key)
    droplet_kernel_pkg = ssh.exec_command('aptitude show linux-image-`uname -r`').split('\n')
    droplet_uname = ssh.exec_command('uname -r').strip()
    if len(droplet_kernel_pkg) > 0:
        for line in droplet_kernel_pkg:
            if 'State: installed' in line:
                print line
            if 'Version: ' in line:
                print line
                current_kernel_name = line.split(': ')[1].split('+')[0]
                break

    if not current_kernel_name:
        raise Exception('Current Kernel version is not found')
    
    droplet_kernels = droplet.get_kernel_available()
    new_kernel = None
    
    if current_kernel_name not in droplet.kernel['name']:
        for kernel in droplet_kernels:
            if current_kernel_name in kernel.name and droplet_uname == kernel.version:
                print 'Kernel found.  ID: %s, Name: %s' % (kernel.id, kernel.name)
                new_kernel = kernel
                break

    if new_kernel:
        print 'Change to use new kernel.  ID: %s' % (new_kernel.id)
        result = droplet.change_kernel(new_kernel)
        if not wait_on_action(do_mgr, droplet, result['action']['id'], 30, 'change_kernel', 'completed'):
            raise Exception('Event did not complate on time')
        droplet = droplet.load()
        result = droplet.power_cycle()
        print result
        if not wait_on_action(do_mgr, droplet, result['action']['id'], 30, 'power_cycle', 'completed'):
            raise Exception('Event did not complete in time')
        droplet = droplet.load()
        if droplet.status != 'active':
            result = droplet.power_on()
            if not wait_on_action(do_mgr, droplet, result['action']['id'], 30, 'power_on', 'completed'):
                raise Exception('Event did not complete in time')
            droplet = droplet.load()

    return droplet


def get_datacenter_region(region):
    """
        This is used to manually identify and set the country region where
        a droplet was created.
        
        return:
            2-digit country code
    """
    '''
        nyc1 New York 1
        ams1 Amsterdam 1
        sfo1 San Francisco
        nyc2 New York 2
        ams2 Amsterdam 2
        sgp1 Singapore 1
        lon1 London 1
        nyc3 New York 3
        ams3 Amsterdam 3
        fra1 Frankfurt 1
        tor1 Toronto 1
    '''
    if 'nyc' in region:
        return 'US'
    if 'sfo' in region:
        return 'US'
    if 'ams' in region:
        return 'NL'
    if 'sgp' in region:
        return 'SG'
    if 'lon' in region:
        return 'GB'
    if 'fra' in region:
        return 'DE'
    if 'tor' in region:
        return 'CA'
    return ''


def wait_on_action(do_mgr, droplet, action_id=None, interval=10, 
                   action_type='create', action_status='completed'):
    """
        Check an action periodically and wait for it to complete.
        
        do_mgr          :   digitalocean.Manager
        droplet         :   digitalocean.Droplet details
        action_id       :   Action ID to check against
        interval        :   Time to wait before (re-)checking an action.
        action_type     :   Action type to watch for. i.e. 'create'
        action_status   :   Action status to wait for i.e. 'completed'
        
        returns:
            Boolean value.  True if action completed successfully.
    """
    try:        
        for attempt in range(10):
            if not action_id:
                if not droplet:
                    raise Exception('Droplet not defined')
                
                droplet_actions = droplet.get_actions()
                if len(droplet_actions) < 1:
                    time.sleep(int(interval))
                    continue
                for action in droplet_actions:
                    if action.type == action_type and action.status == action_status:
                        return True
            else:
                if not do_mgr:
                    raise Exception('DigitalOcean Manager object required')
                action = do_mgr.get_action(action_id)
                if action.type == action_type and action.status == action_status:
                    return True
            print '%s. %s - %s not found - trying again in %ss' % (str(attempt), action_type, action_status, interval)
            time.sleep(int(interval))
    except Exception as e:
        raise e
    
    return False


def transfer_image_to_region(do_mgr, droplet, image_id, regions=list()):
    """
        Copy an image to a specific region.  If no regions are specified then
        copy to all.  This is required when updating the base image.
        
        do_mgr      :   digitalocean.Manager
        droplet     :   digitalocean.Droplet used to check status
        image_id    :   digitalocean.Image ID to transfer
        regions     :   (list) regions to transfer image to.
        
        returns failed_transfers : (list) of failed transfers
    """
    try:
        if not (do_mgr or image_id):
            raise
        
        image = do_mgr.get_image(image_id)
        droplet_regions = do_mgr.get_all_regions()
        common_regions = [r.slug for r in droplet_regions if r.available]
        if len(regions) == 0:
            # transfer to all!
            regions = [r for r in common_regions if r not in image.regions]
        else:
            regions = [r for r in common_regions if r in regions]
        
        transfer_results = dict()
        for r in regions:
            transfer_results[r] = image.transfer(r)
        
        failed_transfers = list()
        for location in transfer_results:
            if not wait_on_action(do_mgr, droplet, transfer_results[location]['action']['id'], 
                                  300, 'transfer', 'completed'):
                failed_transfers.append(location)
        
        return failed_transfers
    except Exception as e:
        raise e


def prepare_new_server(digitalocean_account, droplet, psinet):
    """
        Set up a new server.  This takes the newly launched droplet and prepares
        it to be a new Psiphon server.
        
        digitalocean_account    :   DigitalOcean account details
        droplet                 :   newly created digitalocean.Droplet.
        psinet                  :   instance of psinet.
        
        returns:
            Boolean value.  True if all tasks completed successfully.
    """
    try:
        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()
        region = get_datacenter_region(droplet.region['slug'])
        datacenter_name = 'Digital Ocean ' + droplet.region['name']
        
        new_droplet_public_key = refresh_credentials(digitalocean_account, 
                                                     droplet.ip_address, 
                                                     new_root_password, 
                                                     new_stats_password)

        assert(new_droplet_public_key)
        
        host = psinet.get_host_object(
                    droplet.name, None, droplet.id, droplet.ip_address, 
                    digitalocean_account.base_ssh_port, 'root', new_root_password, 
                    ' '.join(new_droplet_public_key.split(' ')[:2]),
                    digitalocean_account.base_stats_username, new_stats_password,
                    datacenter_name, region, None, None, None, None, None, None)
        
        ssh_port = '22'
        ossh_port = random.choice(['280', '591', '901'])
        capabilities = {'handshake': True, 'FRONTED-MEEK': False, 'UNFRONTED-MEEK': False, 
                        'SSH': True, 'OSSH': True, 'VPN': True}
        
        server = psinet.get_server_object(
                    None, droplet.name, droplet.ip_address, 
                    droplet.ip_address, droplet.ip_address, psinet.get_propagation_channel_by_name('Testing').id,
                    False, False, None, capabilities, str(random.randrange(8000, 9000)), None, None, None,
                    ssh_port, None, None, None, ossh_port, None, None)
        return (host, server)
    except Exception as e:
        raise e
    
    return (False, False)


def remove_server(digitalocean_account, droplet_id):
    """
        Destroys a digitalocean droplet.
        **NOTE** : This does not remove the droplet from psinet.
        
        digitalocean_account    :   DigitalOcean account information
        droplet_id              :   ID of droplet to destroy
    """
    try:
        do_mgr = digitalocean.Manager(token=digitalocean_account.oauth_token)
        droplet = do_mgr.get_droplet(droplet_id)
        result = droplet.destroy()
        if not result:
            raise Exception('Could not destroy droplet: %s' % str(droplet_id))
    except Exception as e:
        # Don't raise the exception if the server has already been removed
        if "The resource you were accessing could not be found." not in str(e):
            raise e


def update_base_image(psinet):
    """
        Sets some specific settings for updating the base image.
    """
    do_mgr = digitalocean.Manager(token=psinet._PsiphonNetwork__digitalocean_account.oauth_token)
    
    droplet = make_base_droplet(psinet, psinet._PsiphonNetwork__digitalocean_account)
    
    update_system_packages(psinet._PsiphonNetwork__digitalocean_account, 
                           droplet.ip_address)
    
    droplet = droplet.load()
    droplet = update_kernel(psinet._PsiphonNetwork__digitalocean_account, do_mgr, droplet)    
    
    droplet = take_droplet_snapshot(do_mgr, droplet)
    
    (host, server) = make_psiphon_server(psinet, psinet._PsiphonNetwork__digitalocean_account, droplet)
    if host and server:
        failures = transfer_image_to_region(do_mgr, droplet, droplet.snapshot_ids[-1])
    
    if len(failures) != 0:
        print 'There were %s' % len(failures)
    else:
        if psinet.is_locked:
            set_new_base_image(psinet, psinet._PsiphonNetwork__digitalocean_account, droplet)


def set_new_base_image(psinet, digitalocean_account, droplet):
    do_mgr = digitalocean.Manager(token=digitalocean_account.oauth_token)
    base_image = do_mgr.get_image(digitalocean_account.base_id)
    base_image.rename(base_image.name + '_bak')
    image = do_mgr.get_image(droplet.snapshot_ids[0])
    digitalocean_account.base_id = image.id
    psinet.save()
    droplet.destroy()


def make_base_droplet(psinet, digitalocean_account):
    """
        Updates the base image.  This includes installing new system packages
        via apt and setting the droplet kernel.
        
        psinet                  :   instance of psinet
        digitalocean_account    :   DigitalOcean account information
        droplet_id              :   digitalocean.Droplet.id to use
        droplet_name            :   (String) to use as droplet name.
        droplet_size            :   (Int) code that denotes the droplet size to use.
                                    Images created with a smaller size can scale
                                    up, but larger sized instances cannot scale down.
        test                    :   (Boolean) value to test the new image
    """
    droplet = None
    try:
        if not digitalocean_account:
            raise Exception('DigitalOcean account must be provided')

        Droplet = collections.namedtuple('Droplet', ['name', 'region', 'image', 
                                                     'size', 'backups'])

        do_mgr = digitalocean.Manager(token=digitalocean_account.oauth_token)
        base_image = do_mgr.get_image(digitalocean_account.base_id)

        Droplet.image = base_image.id
        Droplet.name = base_image.name
        Droplet.size = digitalocean_account.base_size_slug
        Droplet.region = base_image.regions[0] if len(base_image.regions) > 0 else 'nyc1'

        sshkeys = do_mgr.get_all_sshkeys()
        # treat sshkey id as unique
        if not unicode(digitalocean_account.ssh_key_template_id) in [unicode(k.id) for k in sshkeys]:
            raise 'No SSHKey found'

        droplet = digitalocean.Droplet(token=digitalocean_account.oauth_token,
                                       name=Droplet.name,
                                       region=Droplet.region,
                                       image=Droplet.image,
                                       size=Droplet.size,
                                       ssh_keys=[int(digitalocean_account.ssh_key_template_id)],
                                       backups=False)

        droplet.create()

        if not wait_on_action(do_mgr, droplet, action_id=None, interval=30, 
                              action_type='create', action_status='completed'):
            raise Exception('Event did not complete in time')

        droplet = do_mgr.get_droplet(droplet.id)
        if droplet.status != 'active':
            result = droplet.power_on()
            if not wait_on_action(do_mgr, droplet, result['action']['id'], 30, 'power_on', 'completed'):
                raise Exception('Event did not complete in time')
        
        droplet = droplet.load()

    except Exception as e:
        print type(e), str(e)
    
    return droplet


def take_droplet_snapshot(do_mgr, droplet):
    if droplet.status == 'active':
        result = droplet.shutdown()
        if not wait_on_action(do_mgr, droplet, result['action']['id'], 30, 'shutdown', 'completed'):
            raise Exception('Event did not complete in time')
        
        droplet = droplet.load()
    
    if droplet.status == 'off':
        result = droplet.take_snapshot('psiphon3-template-snapshot')
        if not wait_on_action(do_mgr, droplet, result['action']['id'], 120, 'snapshot', 'completed'):
            raise Exception('Snapshot took too long to create')
        
        droplet = droplet.load()

    if len(droplet.snapshot_ids) < 1:
        raise Exception('No snapshot found for image')
    
    return droplet


def make_psiphon_server(psinet, digitalocean_account, droplet):
    host = None
    server = None
    try:
        (host, server) = prepare_new_server(digitalocean_account, droplet, psinet)
        if host and server:
            psinet.setup_server(host, [server])
        else:
            raise Exception('Error creating server. Remove droplet: %s' % droplet.name)
    except Exception as e:
        print type(e), str(e)
    
    return (host, server)


def transfer_server(digitalocean_account, droplet):
    do_mgr = digitalocean.Manager(token=digitalocean_account.oauth_token)
    # transfer image
    failures = transfer_image_to_region(do_mgr, droplet, droplet.snapshot_ids[0])
    if len(failures) > 0:
        print "Failed to transfer image to regions: %s" % (failures)

    return failures


def launch_new_server(digitalocean_account, _):
    """
        Launches a new droplet and configures it to be a Psiphon server.
        This is called from psi_ops.py
        
        digitalocean_account    :   DigitalOcean account information
        
        returns:
            instance of a psinet server
    """
    try:
        Droplet = collections.namedtuple('Droplet', ['name', 'region', 'image', 
                                                     'size', 'backups'])

        new_root_password = psi_utils.generate_password()
        new_stats_password = psi_utils.generate_password()

        do_mgr = digitalocean.Manager(token=digitalocean_account.oauth_token)

        # Get the base image
        base_image = do_mgr.get_image(digitalocean_account.base_id)
        if not base_image:
            raise Exception("Base image with ID: %s is not found" % (digitalocean_account.base_id))
        Droplet.image = base_image.id

        Droplet.name = str('do-' + 
                           ''.join(random.choice(string.ascii_lowercase) for x in range(8)))

        # Set the default size
        droplet_sizes = do_mgr.get_all_sizes()
        if not unicode(digitalocean_account.base_size_slug) in [unicode(s.slug) for s in droplet_sizes]:
            raise 'Size slug not found'

        Droplet.size = '2gb'

        droplet_regions = do_mgr.get_all_regions()
        common_regions = list(set([r.slug for r in droplet_regions if r.available])
                              .intersection(base_image.regions))

        Droplet.region = random.choice(common_regions)

        sshkeys = do_mgr.get_all_sshkeys()
        # treat sshkey id as unique
        if not unicode(digitalocean_account.ssh_key_template_id) in [unicode(k.id) for k in sshkeys]:
            raise 'No SSHKey found'

        droplet = digitalocean.Droplet(token=digitalocean_account.oauth_token,
                                       name=Droplet.name,
                                       region=Droplet.region,
                                       image=Droplet.image,
                                       size=Droplet.size,
                                       ssh_keys=[int(digitalocean_account.ssh_key_template_id)],
                                       backups=False)

        droplet.create()
        if not wait_on_action(do_mgr, droplet, None, 30, 'create', 'completed'):
            raise Exception('Event did not complete in time')

        droplet = do_mgr.get_droplet(droplet.id)
        
        region = get_datacenter_region(droplet.region['slug'])
        datacenter_name = 'Digital Ocean ' + droplet.region['name']
        
        new_droplet_public_key = refresh_credentials(digitalocean_account, 
                                                     droplet.ip_address, 
                                                     new_root_password, 
                                                     new_stats_password)
        assert(new_droplet_public_key)
    
    except Exception as e:
        print type(e), str(e)
        if droplet is not None:
            droplet.destroy()
        else:
            print type(e), "No droplet to be destroyed: ", str(droplet)
        raise
    
    return (droplet.name, None, droplet.id, droplet.ip_address, 
            digitalocean_account.base_ssh_port, 'root', new_root_password, 
            ' '.join(new_droplet_public_key.split(' ')[:2]),
            digitalocean_account.base_stats_username, new_stats_password,
            datacenter_name, region, None, None, None, None, None, None)

if __name__ == "__main__":
    parser = optparse.OptionParser('usage: %prog [options]')
    parser.add_option('-u', "--update-image", dest="update", action="store_true",
                      help="Update the base image")
    
    (options, _) = parser.parse_args()
    if options.update:
        prep_for_image_update()
