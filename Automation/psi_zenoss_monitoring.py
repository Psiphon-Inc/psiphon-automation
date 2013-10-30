#!/usr/bin/python
#
# Copyright (c) 2013, Psiphon Inc.
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
import json
import collections
import multiprocessing
import time
import datetime
import GeoIP
import urllib
import urllib2

import zenoss_credentials

PSI_OPS_DB_FILENAME = os.path.join(os.path.abspath('.'), 'psi_ops_stats.dat')
ZENOSS_INSTANCE = 'http://' + zenoss_credentials.ZENOSS_HOST + ':' + zenoss_credentials.ZENOSS_HTTP_PORT 
ZENOSS_USERNAME = zenoss_credentials.ZENOSS_USER
ZENOSS_PASSWORD = zenoss_credentials.ZENOSS_PASSWORD
ZENOSS_COLLECTOR = 'localhost'

PROVIDERS = zenoss_credentials.PROVIDERS

DEVICE_ORGANIZER = '/zport/dmd/Devices'
LOCATION_ORGANIZER = '/zport/dmd/Locations'
PSIPHON_ORGANIZER = zenoss_credentials.ORGANIZER

ROUTERS = { 'MessagingRouter': 'messaging',
            'EventsRouter': 'evconsole',
            'ProcessRouter': 'process',
            'ServiceRouter': 'service',
            'DeviceRouter': 'device',
            'NetworkRouter': 'network',
            'TemplateRouter': 'template',
            'DetailNavRouter': 'detailnav',
            'ReportRouter': 'report',
            'MibRouter': 'mib',
            'ZenPackRouter': 'zenpack',
            'JobsRouter': 'jobs' }

GEOIP_DAT_PATH = "/usr/local/share/GeoIP/"
if os.path.isdir(GEOIP_DAT_PATH):
    GEOIP_DAT_PATH += "GeoIPCity.dat"
elif os.path.isdir("/usr/local/GeoIP/"):
    GEOIP_DAT_PATH = "/usr/local/GeoIP/" + "GeoIPCity.dat"
else:
    print "Could not find valid GeoIPCity dat file"
    sys.exit()

class ZenossAPI():
    def __init__(self, debug=False):
        """
        Initialize the API connection, log in, and store authentication cookie
        """
        # Use the HTTPCookieProcessor as urllib2 does not save cookies by default
        self.urlOpener = urllib2.build_opener(urllib2.HTTPCookieProcessor())
        if debug: self.urlOpener.add_handler(urllib2.HTTPHandler(debuglevel=1))
        self.reqCount = 1
        
        # Contruct POST params and submit login.
        loginParams = urllib.urlencode(dict(
                        __ac_name = ZENOSS_USERNAME,
                        __ac_password = ZENOSS_PASSWORD,
                        submitted = 'true',
                        came_from = ZENOSS_INSTANCE + '/zport/dmd'))
        self.urlOpener.open(ZENOSS_INSTANCE + '/zport/acl_users/cookieAuthHelper/login',
                            loginParams)
    
    def _router_request(self, router, method, data=[]):
        if router not in ROUTERS:
            raise Exception('Router "' + router + '" not available.')
        
        # Contruct a standard URL request for API calls
        req = urllib2.Request(ZENOSS_INSTANCE + '/zport/dmd/' +
                              ROUTERS[router] + '_router')
        
        # NOTE: Content-type MUST be set to 'application/json' for these requests
        req.add_header('Content-type', 'application/json; charset=utf-8')
        
        # Convert the request parameters into JSON
        reqData = json.dumps([dict(
                    action=router,
                    method=method,
                    data=data,
                    type='rpc',
                    tid=self.reqCount)])
        #print reqData
        #raw_input('holding....')
        # Increment the request count ('tid'). More important if sending multiple
        # calls in a single request
        self.reqCount += 1
        
        # Submit the request and convert the returned JSON to objects
        return json.loads(self.urlOpener.open(req, reqData).read())

    def get_device_events(self, data):
        return self._router_request('EventsRouter', 'query', [data])

    def acknowledge_device_events(self, data):
        return self._router_request('EventsRouter', 'acknowledge', [data])
    
    def close_device_events(self, data):
        return self._router_request('EventsRouter', 'close', [data])
    
    def add_device(self, data):
        return self._router_request('DeviceRouter', 'addDevice', [data])

    def add_location(self, data):
        return self._router_request('DeviceRouter', 'addLocationNode', [data])
    
    def remove_device(self, data):
        return self._router_request('DeviceRouter', 'removeDevices', [data])
    
    def set_device_property(self, data):
        return self._router_request('DeviceRouter', 'setZenProperty', [data])
    
    def set_device_info(self, data):
        return self._router_request('DeviceRouter', 'setInfo', [data])
    
    def get_devices(self, data):
        return self._router_request('DeviceRouter', 'getDevices', [data])
    
    def move_device(self, data):
        return self._router_request('DeviceRouter', 'moveDevices', [data])
    
    def get_locations(self, data):
        return self._router_request('DeviceRouter', 'getTree', [data])

    def get_info(self, data):
        return self._router_request('DeviceRouter', 'getInfo', [data])
    
    def remodel_device(self, data):
        return self._router_request('DeviceRouter', 'remodel', [data])

    def get_job_status(self, data):
        return self._router_request('JobsRouter', 'userjobs', [data])

################################################################################
def get_psiphon_host_list(zenapi):
    device_path = DEVICE_ORGANIZER + PSIPHON_ORGANIZER
    data = {'uid': device_path,
            'keys': ['name', 'ipAddress', 'productionState'],
            'params': {}, 'sort':'name', 'dir': 'ASC', 'limit':4000}
    psiphon_hosts = zenapi.get_devices(data)['result']
    if psiphon_hosts['success'] == True:
        return psiphon_hosts['devices']
    else:
        print 'Failed getting host list: %s', psiphon_hosts['msg']
        raise

def replace_ip_address(zenoss_hosts):
    for zhost in zenoss_hosts:
        uid = zhost['uid'].split('/')
        zhost['ipAddress'] = uid[len(uid)-1]
    return zenoss_hosts

def decommission_hosts(hosts, zenoss_hosts, zenapi):
    # Check each Zenoss_host to see if they are in the current list
    # if not, decommission them
    for zhost in zenoss_hosts:
        found_host = next((host for host in hosts if host.id == zhost['name']), None)
        if not found_host:
            host_details = zenapi.get_info({'keys': ['productionState'], 'uid': zhost['uid']})
            if host_details['result']['data']['productionState'] != -1:
                print '%s -> decommissioning ip %s' % (zhost['name'], zhost['ipAddress'])
                data = { 'uid': zhost['uid'],
                         'productionState' : -1 }
                zenapi.set_device_info(data)
                # get event count
                zhost['eventCount'] = get_host_event_count(zhost, zenapi)
                if zhost['eventCount'] > 0:
                    print 'Acknowledging events'
                    data = {'uid': zhost['uid']}
                    zhost['ackResult'] = zenapi.acknowledge_device_events(data)
                    if check_result(zhost['ackResult']):
                        # move on to closing events
                        zhost['closeResult'] = zenapi.close_device_events(data)
                        if check_result(zhost['closeResult']):
                            print 'Closed events for device %s (%s)' % (zhost['name'], zhost['ipAddress'])


def get_host_event_count(zhost, zenapi):
    #set data
    data = {'uid': zhost['uid'], 'keys': []}
    zhost['result'] = zenapi.get_device_events(data)
    if check_result(zhost['result']):
        return zhost['result']['result']['totalCount']
    else: return 0

def check_result(res):
    return res['result']['success']

def remove_hosts(zenoss_hosts, zenapi):
    # check if a host is decommissioned and has been so for longer than 4 months
    # remove host from tracking
    uids_to_remove = []
    for zhost in zenoss_hosts:
	if zhost['productionState'] == -1:
            # check if decommissioned
            data = {'keys': ['device','uptime', 'lastChanged', 'productionState'],
                    'uid': zhost['uid'] }
            zhost['info'] = zenapi.get_info(data)
            if zhost['info']['result']['success'] == False:
		        print 'getInfo for device %s -> %s failed' % (zhost['name'], zhost['ipAddress'])
            else:
                # check how long they've been decommissioned for
                last_changed = time.strptime(zhost['info']['result']['data']['lastChanged'],
                                              '%Y/%m/%d %H:%M:%S')
                limit = datetime.date.today() + datetime.timedelta(weeks=-12)
                last_changed = datetime.date.fromtimestamp(time.mktime(last_changed))
                if limit > last_changed:
                    # flag for removal
                    print "%s to be removed.  Last seen: %s" % (zhost['name'], last_changed)
                    uids_to_remove.append(zhost['uid'])
    
    if uids_to_remove > 0:
        data = {'action': 'delete',
                'uids': uids_to_remove,
                'hashcheck': 1,
                'deleteEvents': True,
                'deletePerf': True,
               }
        zenapi.remove_device(data)

# force the hosts to be Modelled
def model_hosts(zenoss_hosts, zenapi):
    for zhost in zenoss_hosts:
        if zhost['productionState'] == 1000: #check if in production
            data = {'keys': ['lastChanged', 'lastCollected'], 'uid': zhost['uid']}
            resp = zenapi.get_info(data)
            if resp['result']['success'] == False:
                print 'getinfo for device %s (%s) has failed' % (zhost['name'], zhost['ipAddress'])
            else:
                #submit the host for modeling
                if resp['result']['data']['lastCollected'] == 'Not Modeled':
                    data = {'deviceUid': zhost['uid']}
                    print 'Modeling Device: %s' % (zhost['name'])
                    zenapi.remodel_device(data)

def organize_hosts(hosts, zenoss_hosts, zenapi):
    device_path = DEVICE_ORGANIZER + PSIPHON_ORGANIZER
    for zhost in zenoss_hosts:
        found_host = next((host for host in hosts if host.id == zhost['name']), None)
        if found_host:
            target_path = device_path + '/' + PROVIDERS[found_host.provider]
            if target_path not in zhost['uid']:
                print '%s -> moved to %s' % (zhost['name'], zhost['uid'])
                data = {'uids': zhost['uid'],
                        'ranges': [],
                        'target': target_path,
                        'asynchronous': 'false'}
                zenapi.move_device(data)

def organize_hosts_by_country(hosts, zenoss_hosts, zenapi):
    device_path = LOCATION_ORGANIZER
    for zhost in zenoss_hosts:
        found_host = next((host for host in hosts if host.id == zhost['name']), None)
        if found_host:
            host_details = zenapi.get_info({'keys': ['location'], 'uid': zhost['uid']})
            target_path = device_path + '/' + zhost['country_name']
            if host_details['result']['data']['location'] is None:
                print '%s -> moved to %s' % (zhost['name'], zhost['country_name'])
                data = {'uids': [zhost['uid']],
                        'ranges': [],
                        'target': device_path + '/' + zhost['country_name'],
                        'asynchronous': 'false'}
                zenapi.move_device(data)

# Set device specific configuration options here
# including user credentials and how to monitor.
def set_psiphon_hosts_model_config(hosts, zenoss_hosts, zenapi):
    device_path = DEVICE_ORGANIZER + PSIPHON_ORGANIZER
    for zhost in zenoss_hosts:
        found_host = next((host for host in hosts if host.id == zhost['name']), None)
        if found_host:
            print '%s -> setting ssh username' % found_host.id
            data = {'uid': device_path + '/' + PROVIDERS[found_host.provider] 
                           + '/devices/' + found_host.ip_address,
                    'zProperty': 'zCommandUsername',
                    'value': found_host.stats_ssh_username }
            zenapi.set_device_property(data)
            
            print '%s -> setting ssh password' % found_host.id
            data['zProperty'] = 'zCommandPassword'
            data['value'] = found_host.stats_ssh_password        
            zenapi.set_device_property(data)
            
            print '%s -> setting command port' % found_host.id
            data['zProperty'] = 'zCommandPort'
            data['value'] = found_host.ssh_port
            zenapi.set_device_property(data)
            
            print '%s -> setting ping ignore' % found_host.id
            data['zProperty'] = 'zPingMonitorIgnore'
            data['value'] = 'true'
            zenapi.set_device_property(data)
            
            print '%s -> setting snmp ignore' % found_host.id
            data['zProperty'] = 'zSnmpMonitorIgnore'
            data['value'] = 'true'
            zenapi.set_device_property(data)

def set_psiphon_modeling_config(host, zenapi):
    device_path = DEVICE_ORGANIZER + PSIPHON_ORGANIZER + '/' + PROVIDERS[host.provider]
    data = dict(uid=device_path + '/devices/'
                + host.ip_address,
                zProperty='zCommandUsername',
                value=host.stats_ssh_username,
                )
    print '%s -> setting ssh username' % host.id
    zenapi.set_device_property(data)
    data['zProperty'] = 'zCommandPassword'
    data['value'] = host.stats_ssh_password
    print '%s -> setting ssh password' % host.id
    zenapi.set_device_property(data)
    data['zProperty'] = 'zCommandPort'
    data['value'] = host.ssh_port
    print '%s -> setting command port' % host.id
    zenapi.set_device_property(data)
    data['zProperty'] = 'zPingMonitorIgnore'
    data['value'] = 'true'
    print '%s -> setting ping ignore' % host.id
    zenapi.set_device_property(data)
    data['zProperty'] = 'zSnmpMonitorIgnore'
    data['value'] = 'true'
    print '%s -> setting snmp ignore' % host.id
    zenapi.set_device_property(data)    

def add_new_hosts(hosts, zenoss_hosts, zenapi):
    for host in hosts:
        new_host = [host for zhost in zenoss_hosts if zhost['name'] == host.id]
        if len(new_host) >= 1:
            new_host = new_host[0]
            device_path = PSIPHON_ORGANIZER + '/' + PROVIDERS[new_host.provider]
            data = dict(deviceName=new_host.ip_address,
                        deviceClass=device_path,
                        collector=ZENOSS_COLLECTOR,
                        model='false',
                        title=new_host.id,)
            zenapi.add_device(data)

def start_monitoring(hosts, zenapi):    
    for host in hosts:
        device_path = PSIPHON_ORGANIZER + '/' + PROVIDERS[host.provider]
        data = dict(deviceName=host.ip_address,
                    deviceClass=device_path,
                    collector=ZENOSS_COLLECTOR,
                    model='false',
                    title=host.id,)
        zenapi.add_device(data)

def check_running_jobs(zenapi):
    jobs = zenapi.get_job_status({})['result']['totals']
    if 'PENDING' in jobs:
        return jobs['PENDING']
    else:
        return 0

def get_location_list(zenapi):
    data = LOCATION_ORGANIZER
    response = zenapi.get_locations(data)
    locations = response['result'][0]['children']
    l = []
    for location in locations:
        if location['uid'] is not None:
            l.append(location['text']['text'])
    return l

def geocode_hosts(zenoss_hosts):
    gi = GeoIP.open(GEOIP_DAT_PATH, GeoIP.GEOIP_STANDARD)
    #lookup server location
    try:
        for idx, zhost in enumerate(zenoss_hosts):
            zenoss_hosts[idx] = dict(zhost.items() + gi.record_by_addr(zhost['ipAddress']).items())
    except Exception, e:
        print e

    return zenoss_hosts

def update_locations(zenoss_hosts, zenapi, mapped_locations):
    location_path = LOCATION_ORGANIZER
    for zhost in zenoss_hosts:
        if zhost['country_name'] not in mapped_locations:
            print "processing location: %s" % (zhost['country_name'])
            data = dict(id=zhost['country_name'],
                        description=zhost['country_code'],
                        type='organizer',
                        contextUid=location_path,
                        address=zhost['region_name'] +', '+ zhost['country_name'] if zhost['region_name'] else zhost['country_name']
                        )
            zenapi.add_location(data)

####################################################
if __name__ == "__main__":
    print "Starting Zenoss Monitoring at: %s" % (datetime.datetime.now())
    start_time = time.time()
    # Open the db and load psiphon hosts as 'hosts'
    with open(PSI_OPS_DB_FILENAME) as file:
        psinet = json.loads(file.read())
    
    Host = collections.namedtuple(
        'Host',
        'id, provider, ip_address, ssh_port, ssh_host_key, stats_ssh_username, stats_ssh_password')

    hosts = [Host(host['id'],
                  host['provider'],
                  host['ip_address'],
                  host['ssh_port'],
                  host['ssh_host_key'],
                  host['stats_ssh_username'],
                  host['stats_ssh_password'])
             for host in psinet['_PsiphonNetwork__hosts'].itervalues()]
    
    # Connect to Zenoss and add in hosts
    try:
        zenapi = ZenossAPI()
        #jobs_left = check_running_jobs(zenapi)
        print "Adding hosts to be monitored"
        zenoss_hosts = get_psiphon_host_list(zenapi)
        add_new_hosts(hosts, zenoss_hosts, zenapi)
        #start_monitoring(hosts, zenapi)
        jobs_left = check_running_jobs(zenapi)
        while jobs_left > 0:
            jobs_left = check_running_jobs(zenapi)
            print 'Jobs remaining: %s' % jobs_left
            time.sleep(30)

        # get the known Psiphon hosts in Zenoss
        print "Getting current Location Mappings"
        mapped_locations = get_location_list(zenapi)
        print "Getting Zenoss host list"
        zenoss_hosts = get_psiphon_host_list(zenapi)
        # dirty fix to replace the ip address:
        print "Replacing IP addresses"
        zenoss_hosts = replace_ip_address(zenoss_hosts)
        print "Geocoding Zenoss hosts"
        zenoss_hosts = geocode_hosts(zenoss_hosts)
        print 'Organizing Hosts'
        update_locations(zenoss_hosts, zenapi, mapped_locations)
        organize_hosts(hosts, zenoss_hosts, zenapi)
        organize_hosts_by_country(hosts, zenoss_hosts, zenapi)
        print 'Setting Hosts Modeler config'
        set_psiphon_hosts_model_config(hosts, zenoss_hosts, zenapi)
        print 'Checking decommissioned Hosts'
        decommission_hosts(hosts, zenoss_hosts, zenapi)
        print 'Removing decommissioned hosts older than 90 days' 
        remove_hosts(zenoss_hosts, zenapi)
        print 'Model hosts'
        model_hosts(zenoss_hosts, zenapi)
    except Exception, e:
        print "Failed: ", e
    
    print 'elapsed time: %fs' % (time.time()-start_time,)

