#!/usr/bin/python

import requests
import sys

class DigitalOceanAPI():
    def __init__(self, client_id, api_key):
        self.credentials = {'client_id': client_id,
                                'api_key': api_key,
                                }

        self.api_requests = {'droplets': 'droplets',
                            'regions': 'regions',
                            'images': 'images',
                            'ssh_keys': 'ssh_keys',
                            'sizes': 'sizes',
                            'domains': 'domains',
                            'events': 'events',
                            'errors': 'errors',
                           }
        
        for k in self.api_requests:
            self.api_requests[k] = 'https://api.digitalocean.com/v1/' + k + '/'
    
    def _get_content(self, url, payload=None):
        resp = requests.get(url, params=payload)
        if resp.status_code == 200:
            return resp.json()
        else:
            print 'Invalid Response: %s' % (resp.status_code)
            #sys.exit()
    
    def get_running_droplets(self):
        resp = self._get_content(self.api_requests['droplets'], self.credentials)
        return resp['droplets']
    
    def get_all_regions(self):
        resp = self._get_content(self.api_requests['regions'], self.credentials)
        return resp['regions']
        
    def get_all_images(self):
        resp = self._get_content(self.api_requests['images'], self.credentials)
        return resp['images']
    
    def get_all_droplet_sizes(self):
        resp = self._get_content(self.api_requests['sizes'], self.credentials)
        return resp['sizes']
    
    def show_all_regions(self):
        resp = self.get_all_regions()
        print 'Regions Available:\n'
        for r in resp:
            print r
    
    def show_all_images(self):
        resp = self.get_all_images()
        for r in resp:
            print r
    
    def show_all_droplet_sizes(self):
        resp = self.get_all_droplet_sizes()
        for r in resp:
            print r
    
    '''Parameters: 
        https://api.digitalocean.com/droplets/new?client_id=[your_client_id]&api_key=[your_api_key]&name=[droplet_name]&size_id=[size_id]&image_id=[image_id]&region_id=[region_id]&ssh_key_ids=[ssh_key_id1],[ssh_key_id2]'''
    def create_new_droplet(self, params):
        resp = self._get_content((self.api_requests['droplets'] + 'new'), 
                                  dict(self.credentials.items() + params.items()))
        return resp

    def droplet_show(self, droplet_id):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id)),
                                  self.credentials)
        return resp

    def droplet_reboot(self, droplet_id):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/reboot/'), self.credentials)
        return resp
    
    def droplet_power_cycle(self, droplet_id):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/power_cycle/'), self.credentials)
        return resp
    
    def droplet_shutdown(self, droplet_id):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/shutdown/'), self.credentials)
        return resp
    
    def droplet_power_off(self, droplet_id):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/power_off/'), self.credentials)
        return resp
    
    def droplet_power_on(self, droplet_id):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/power_on/'), self.credentials)
        return resp
    
    def droplet_password_reset(self, droplet_id):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/password_reset/'), self.credentials)
        return resp
    
    def droplet_resize(self, droplet_id, new_size):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/resize/'), dict(self.credentials.items() + new_size.items()))
        return resp
    
    def droplet_snapshot(self, droplet_id, snapshot=dict()):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/snapshot/'), dict(snapshot.items() + self.credentials.items()))
        return resp
    
    def droplet_restore(self, droplet_id, params=dict()):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/restore/'), dict(self.credentials.items() + params.items()))
        return resp
    
    # takes rebuilds droplet with image_id
    # params = {'image_id': ''}
    def droplet_rebuild(self, droplet_id, params=dict()):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/rebuild/'), dict(self.credentials.items() + params.items()))
        return resp
    
    def droplet_enable_backups(self, droplet_id):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/enable_backups/'), dict(self.credentials.items()))
        return resp
    
    def droplet_disable_backups(self, droplet_id):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/disable_backups/'), dict(self.credentials.items()))
        return resp
    
    # takes in str(), {'name': 'new_name'}
    def droplet_rename(self, droplet_id, params=dict()):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/restore/'), dict(self.credentials.items() + params.items()))
        return resp
    
    def droplet_destroy(self, droplet_id, params=dict()):
        resp = self._get_content((self.api_requests['droplets'] + str(droplet_id) +
                                  '/destroy/'), dict(self.credentials.items() + params.items()))
        return resp
    
    def image_show(self, image_id):
        resp = self._get_content((self.api_requests['images'] + str(image_id) + 
                                  '/'), self.credentials)
        return resp
    
    def image_destroy(self, image_id):
        resp = self._get_content((self.api_requests['images'] + str(image_id) + 
                                  '/destroy/'), self.credentials)
        return resp
    
    # params = {'region_id': 'new_region'}
    def image_transfer(self, image_id, params):
        resp = self._get_content((self.api_requests['images'] + str(image_id) + 
                                  '/transfer/'), dict(self.credentials.items() + params.items()))
        return resp
    
    def ssh_keys_show_all_keys(self):
        resp = self._get_content(self.api_requests['ssh_keys'], self.credentials)
        return resp
    
    # params = {'name': 'new_name', 'ssh_pub_key': 'new pub_key'}
    def ssh_keys_add_new(self, params):
        resp = self._get_content(self.api_requests['ssh_keys'] + 'new/', dict(self.credentials.items() + params.items()))
        return resp
    
    def get_ssh_key(self, ssh_key_id):
        resp = self._get_content((self.api_requests['ssh_keys'] + str(ssh_key_id) + '/'), 
                                  self.credentials)
        return resp
    
    def ssh_keys_edit(self, ssh_key_id):
        resp = self._get_content((self.api_requests['ssh_keys'] + str(ssh_key_id) + 
                                  '/edit/'), self.credentials)
        return resp
    
    def ssh_keys_destroy(self, ssh_key_id, params):
        resp = self._get_content((self.api_reqeusts['ssh_keys'] + str(ssh_key_id) +
                                  '/destroy/'), self.credentials)
        return resp
    
    def get_event(self, event_id):
        resp = self._get_content((self.api_requests['events'] + str(event_id) + '/'),
                                  self.credentials)
        return resp
    

