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

import digitalocean

def refresh_credentials(digitalocean_account, ip_address, new_root_password, new_stats_password):
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
    ssh = psi_ssh.make_ssh_session(ip_address, digitalocean_account.base_ssh_port, 'root', None, None, digitalocean_account.base_rsa_private_key)
    ssh.exec_command('export DEBIAN_FRONTEND=noninteractive && aptitude update -q && aptitude safe-upgrade -y -o Dpkg::Options::="--force-confdef"')

def get_datacenter_region(region):
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
    '''
    if 'nyc' or 'sfo' in region:
        return 'US'
    if 'ams' in region:
        return 'NL'
    if 'sgp' in region:
        return 'SG'
    if 'lon' in region:
        return 'GB'
    return ''

def wait_on_action(do_mgr=None, droplet=None, action_id=None, interval=10, 
                   action_type='create', action_status='completed'):
    """
        Check an action periodically
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

def transfer_image_to_region(do_mgr = None, image_id=None, regions=list()):
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
            if not wait_on_action(do_mgr, None, transfer_results[location]['action']['id'], 
                                  300, 'transfer', 'completed'):
                failed_transfers.append(location)
        
        return failed_transfers
    except Exception as e:
        raise

def setup_new_server(digitalocean_account, droplet):
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
        
        host = psinet.get_host_object(droplet.name, None, droplet.id, droplet.ip_address, 
                    digitalocean_account.base_ssh_port, 'root', new_root_password, 
                    ' '.join(new_droplet_public_key.split(' ')[:2]),
                    digitalocean_account.base_stats_username, new_stats_password,
                    datacenter_name, region, None, None, None, None, None, None)
        
        ssh_port = '22'
        ossh_port = random.choice(['280', '591', '901'])
        capabilities = {'handshake': True, 'FRONTED-MEEK': False, 'UNFRONTED-MEEK': False, 
                        'SSH': True, 'OSSH': True, 'VPN': True}
        
        server = psinet.get_server_object(None, droplet.name, droplet.ip_address, droplet.ip_address,
                    droplet.ip_address, psinet.get_propagation_channel_by_name('Testing').id,
                    False, False, None, capabilities, str(random.randrange(8000, 9000)), None, None, None,
                    ssh_port, None, None, None, ossh_port, None, None)
        psinet.setup_server(host, [server])
        return True
    except Exception as e:
        raise e
    
    return False

def prep_for_image_update():
    PSI_OPS_ROOT = os.path.abspath(os.path.join('..', 'Data', 'PsiOps'))
    PSI_OPS_DB_FILENAME = os.path.join(PSI_OPS_ROOT, 'psi_ops.dat')
    
    import psi_ops
    
    if os.path.isfile('psi_data_config.py'):
        import psi_data_config
        try:
            sys.path.insert(0, psi_data_config.DATA_ROOT)
            if hasattr(psi_data_config, 'CONFIG_FILE'):
                psi_ops_config = __import__(psi_data_config.CONFIG_FILE)
            else:
                psi_ops_config = __import__('psi_ops_config')
        except ImportError as error:
            print error
    
    global psinet
    psinet = psi_ops.PsiphonNetwork.load_from_file(PSI_OPS_DB_FILENAME)
    update_image(psinet._PsiphonNetwork__digitalocean_account)
    

def update_image(digitalocean_account=None, droplet_id=None, droplet_name=None, droplet_size=None, test=True):
    try:
        if not digitalocean_account:
            raise Exception('DigitalOcean account must be provided')

        Droplet = collections.namedtuple('Droplet', ['name', 'region', 'image', 
                                                     'size', 'backups'])

        do_mgr = digitalocean.Manager(token=digitalocean_account.oauth_token)
        base_image = do_mgr.get_image(digitalocean_account.base_id)

        Droplet.image = base_image.id if not droplet_id else droplet_id
        Droplet.name = base_image.name if not droplet_name else droplet_name
        Droplet.size = digitalocean_account.base_size_slug if not droplet_size else droplet_size
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
                                       backups=False)

        droplet.create(ssh_keys=str(digitalocean_account.ssh_key_template_id))

        if not wait_on_action(do_mgr, droplet, action_id=None, interval=30, 
                              action_type='create', action_status='completed'):
            raise Exception('Event did not complete in time')

        droplet = do_mgr.get_droplet(droplet.id)
        if droplet.status != 'active':
            result = droplet.power_on()
            if not wait_on_action(do_mgr, droplet, result['action']['id'], 30, 'power_on', 'completed'):
                raise Exception('Event did not complete in time')
            
            droplet = droplet.load()

        update_system_packages(digitalocean_account, droplet.ip_address)
        droplet = droplet.load()

        result = droplet.reboot()
        if not wait_on_action(do_mgr, droplet, result['action']['id'], 30, 'reboot', 'completed'):
            raise Exception('Event did not complete in time')

        droplet = droplet.load()

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

        # test the server
        if test:
            result = setup_new_server(digitalocean_account, droplet)

        if not result:
            raise 'Could not set up server successfully'

        # transfer image
        failures = transfer_image_to_region(do_mgr, droplet.snapshot_ids[0])
        if len(failures) > 0:
            print "Failed to transfer image to regions: %s" % (failures)

        if psinet.is_locked:
            base_image.rename(base_image.name + '_bak')
            image = do_mgr.get_image(droplet.snapshot_ids[0])
            digitalocean_account.base_id = image.id
            psinet.save()

        droplet.destroy()
    
    except Exception as e:
        print type(e), str(e)

def launch_new_server(digitalocean_account, _):
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
                                       backups=False)

        droplet.create(ssh_keys=str(digitalocean_account.ssh_key_template_id))
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
        if droplet != None:
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
