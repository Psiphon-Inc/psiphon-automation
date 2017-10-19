# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
VPS.net driver
"""
import base64

try:
    import simplejson as json
except ImportError:
    import json

from libcloud.utils.py3 import b

from libcloud.common.base import ConnectionUserAndKey, JsonResponse
from libcloud.common.types import InvalidCredsError, MalformedResponseError
from libcloud.compute.providers import Provider
from libcloud.compute.types import NodeState
from libcloud.compute.base import Node, NodeDriver
from libcloud.compute.base import NodeSize, NodeImage, NodeLocation

API_HOST = 'api.vps.net'
API_VERSION = 'api10json'

RAM_PER_NODE = 256
DISK_PER_NODE = 10
BANDWIDTH_PER_NODE = 250


class VPSNetResponse(JsonResponse):
    def parse_body(self):
        try:
            return super(VPSNetResponse, self).parse_body()
        except MalformedResponseError:
            return self.body

    def success(self):
        # vps.net wrongly uses 406 for invalid auth creds
        if self.status == 406 or self.status == 403:
            raise InvalidCredsError()
        return True

    def parse_error(self):
        try:
            errors = super(VPSNetResponse, self).parse_body()['errors'][0]
        except MalformedResponseError:
            return self.body
        else:
            return "\n".join(errors)


class VPSNetConnection(ConnectionUserAndKey):
    """
    Connection class for the VPS.net driver
    """

    host = API_HOST
    responseCls = VPSNetResponse

    allow_insecure = False

    def add_default_headers(self, headers):
        user_b64 = base64.b64encode(b('%s:%s' % (self.user_id, self.key)))
        headers['Authorization'] = 'Basic %s' % (user_b64.decode('utf-8'))
        return headers


class VPSNetNodeDriver(NodeDriver):
    """
    VPS.net node driver
    """

    type = Provider.VPSNET
    api_name = 'vps_net'
    name = "vps.net"
    website = 'http://vps.net/'
    connectionCls = VPSNetConnection

    def _to_node(self, vm):
        if vm['running']:
            state = NodeState.RUNNING
        else:
            state = NodeState.PENDING

        n = Node(id=vm['id'],
                 name=vm['label'],
                 state=state,
                 public_ips=[vm.get('primary_ip_address', None)],
                 private_ips=[],
                 extra={'slices_count': vm['slices_count'],
                        'password': vm.get('password', None)},
                 # Number of nodes consumed by VM
                 driver=self.connection.driver)
        return n

    def _to_image(self, image, cloud):
        image = NodeImage(id=image['id'],
                          name="%s: %s" % (cloud, image['label']),
                          driver=self.connection.driver)

        return image

    def _to_size(self, num):
        size = NodeSize(id=num,
                        name="%d Node" % (num,),
                        ram=RAM_PER_NODE * num,
                        disk=DISK_PER_NODE,
                        bandwidth=BANDWIDTH_PER_NODE * num,
                        price=self._get_price_per_node(num) * num,
                        driver=self.connection.driver)
        return size

    def _get_price_per_node(self, num):
        single_node_price = self._get_size_price(size_id='1')
        return num * single_node_price

    def create_node(self, name, image_id, cloud_id,size, **kwargs):
        """Create a new VPS.net node

        @inherits: :class:`NodeDriver.create_node`

        :keyword    ex_backups_enabled: Enable automatic backups
        :type       ex_backups_enabled: ``bool``

        :keyword    ex_fqdn:   Fully Qualified domain of the node
        :type       ex_fqdn:   ``str``
        """
        headers = {'Content-Type': 'application/json'}
        request = {'virtual_machine':
                   {'label': name,
                    'fqdn': kwargs.get('ex_fqdn', ''),
                    'system_template_id': image_id,
                    'cloud_id': cloud_id,
                    'backups_enabled': kwargs.get('ex_backups_enabled', 0),
                    'slices_required': size}}

        res = self.connection.request('/virtual_machines.%s' % (API_VERSION,),
                                      data=json.dumps(request),
                                      headers=headers,
                                      method='POST')

        if 'virtual_machine' in res.object:
            node = self._to_node(res.object['virtual_machine'])
        else:
            node = res
        return node

    def reboot_node(self, node):
        res = self.connection.request(
            '/virtual_machines/%s/%s.%s' % (node.id,
                                            'reboot',
                                            API_VERSION),
            method="POST")
        node = self._to_node(res.object['virtual_machine'])
        return True

    def list_sizes(self, location=None):
        res = self.connection.request('/nodes.%s' % (API_VERSION,))
        available_nodes = len([size for size in res.object
                               if size['slice']['virtual_machine_id']])
        sizes = [self._to_size(i) for i in range(1, available_nodes + 1)]
        return sizes

    def destroy_node(self, node):
        res = self.connection.request('/virtual_machines/%s.%s'
                                      % (node.id, API_VERSION),
                                      method='DELETE')
        return res.status == 200

    def list_nodes(self):
        res = self.connection.request('/virtual_machines.%s' % (API_VERSION,))
        return [self._to_node(i['virtual_machine']) for i in res.object]

    def list_images(self, location=None):
        res = self.connection.request('/available_clouds.%s' % (API_VERSION,))

        images = []
        for cloud in res.object:
            label = cloud['cloud']['label']
            templates = cloud['cloud']['system_templates']
            images.extend([self._to_image(image, label)
                           for image in templates])

        return images

    def list_locations(self):
        return [NodeLocation(0, "VPS.net Western US", 'US', self)]
    
    def list_ssd_nodes(self, location=None):
        res = self.connection.request(
            '/ssd_virtual_machines.%s' % (API_VERSION,))
        if 'errors' in res.object:
            raise 'Error returning list of nodes: %s' % (res.object['errors'])
        
        return [self._to_ssd_node(i['virtual_machine']) for i in res.object]
    
    def get_node(self, node_id):
        res = self.connection.request(
            '/virtual_machines/%s.%s' % (node_id,
                                             API_VERSION),
            method="GET")
        node = self._to_node(res.object['virtual_machine'])
        return node

    def get_ssd_node(self, node_id):
        res = self.connection.request(
            '/ssd_virtual_machines/%s.%s' % (node_id,
                                             API_VERSION),
            method="GET")
        node = self._to_ssd_node(res.object['virtual_machine'])
        return node
    
    def reboot_ssd_node(self, node):
        res = self.connection.request(
            '/ssd_virtual_machines/%s/%s.%s' % (node.id,
                                                'reboot',
                                                API_VERSION),
            method="POST")
        node = self._to_ssd_node(res.object['virtual_machine'])
        return True
    
    def shutdown_ssd_node(self, node):
        res = self.connection.request(
            '/ssd_virtual_machines/%s/%s.%s' % (node.id,
                                                'shutdown',
                                                API_VERSION),
            method="POST")
        node = self._to_ssd_node(res.object['virtual_machine'])
        return True
    
    def force_shutdown_ssd_node(self, node):
        res = self.connection.request(
            '/ssd_virtual_machines/%s/%s.%s' % (node.id,
                                                'power_off',
                                                API_VERSION),
            method="POST")
        node = self._to_ssd_node(res.object['virtual_machine'])
        return True
    
    def start_ssd_node(self, node):
        res = self.connection.request(
            '/ssd_virtual_machines/%s/%s.%s' % (node.id,
                                                'power_on',
                                                API_VERSION),
            method="POST")
        node = self._to_ssd_node(res.object['virtual_machine'])
        return True
    
    def delete_ssd_node(self, node):
        res = self.connection.request(
            '/ssd_virtual_machines/%s.%s' % (node.id,
                                             API_VERSION),
            method="DELETE")
        return res
    
    def create_ssd_node(self, fqdn, image_id, cloud_id, size, **kwargs):
        """Create a new VPS.net node

        @inherits: :class:`NodeDriver.create_node`

        :keyword    ex_backups_enabled:       Enable automatic backups
        :type       ex_backups_enabled:       ``bool``

        :keyword    ex_rsync_backups_enabled: Fully Qualified domain of the node
        :type       ex_rsync_backups_enabled:   ``bool``
        """
        headers = {'Content-Type': 'application/json'}
        request = {'virtual_machine':
                   {'ssd_vps_plan': size,
                    'fqdn': fqdn,
                    'system_template_id': image_id,
                    'cloud_id': cloud_id,
                    'backups_enabled': kwargs.get('backups_enabled', 0),
                    'rsync_backups_enabled': kwargs.get(
                        'rsync_backups_enabled', 0)}}
        
        res = self.connection.request(
            '/ssd_virtual_machines.%s' % (API_VERSION,),
            data=json.dumps(request),
            headers=headers,
            method='POST')
        if 'virtual_machine' in res.object:
            node = self._to_ssd_node(res.object['virtual_machine'])
        else:
            node = res
        return node
    
    def _to_ssd_node(self, vm):
        if vm['running']:
            state = NodeState.RUNNING
        else:
            state = NodeState.PENDING

        n = Node(id=vm['id'],
                 name=vm['ssd_vps_label'],
                 state=state,
                 public_ips=[vm.get('primary_ip_address', None)],
                 private_ips=[],
                 extra={
                    'password': vm.get('password', None),
                    'backups_enabled': vm['backups_enabled'],
                    'cloud_id': vm['cloud_id']},
                 driver=self.connection.driver)
        return n
    
    def get_system_templates(self):
        res = self.connection.request(
            '/system_templates.%s' % (API_VERSION),
            method="GET")
        return res
    
    def get_all_ssd_clouds(self):
        res = self.connection.request(
            '/available_ssd_clouds.%s' % (API_VERSION),
            method='GET')
        return res.parse_body()
    
    def get_available_ssd_clouds(self):
        available_clouds = list()
        clouds = self.get_all_ssd_clouds()
        for cloud in clouds:
            if cloud['cloud']['available']:
                available_clouds.append(cloud)
        
        return available_clouds

    def get_all_clouds(self):
        res = self.connection.request(
            '/available_clouds.%s' % (API_VERSION),
            method='GET')
        return res.parse_body()
    
    def get_available_clouds(self):
        available_clouds = list()
        clouds = self.get_all_clouds()
        for cloud in clouds:
            if cloud['cloud']['available']:
                available_clouds.append(cloud)
        
        return available_clouds
