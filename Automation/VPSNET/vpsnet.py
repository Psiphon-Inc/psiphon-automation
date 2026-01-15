import requests
import json

class vpsnet:
    def __init__(self, api_key):
        self.__key = api_key
        self.__url = 'https://platform.vps.net'
        self.s = requests.session()
        if self.api_key:
            self.s.headers.update({'Authorization': f'Bearer {self.api_key}'})


    def _get_request(self, endpoint): #done;
        try:
            response = requests.get(self.__url + endpoint, headers={'X-Api-Token': self.__key})

            if response.ok:
                # Success - 200 OK
                return json.loads(response.content)
            else:
                # Failure
                return response.raise_for_status()
        except Exception as e:
            raise e


    def _post_request(self, endpoint, payload=None):
        try:
            #if endpoint == '/rest-api/ssd-vps/locations/0/servers': / create VM
            if payload != None:
                # Create VM
                response = requests.post(self.__url + endpoint, headers={'X-Api-Token': self.__key, 'Content-Type': 'application/json', 'Accept': 'application/json'}, data=payload)
                print(endpoint, payload)
                print(self.__url + endpoint)
                print(response)
                print("HERE")
            else:
                # Control VM
                response = requests.post(self.__url + endpoint, headers={'X-Api-Token': self.__key})

            #if response['statusCode'] == 201 or response['statusCode'] == 200:
            if response.ok:
                # Success - 201 Created or 200 Accepted
                return json.loads(response.content)
            else:
                return response.raise_for_status()
        except Exception as e:
            raise e


    def _delete_request(self, endpoint):
        try:
            response = requests.delete(self.__url + endpoint, headers={'X-Api-Token': self.__key})

            if response.ok:
                return True
            else:
                return response.raise_for_status()
        except Exception as e:
            raise e


    def get_ssd_vps_plans(self): #WORKS
        response = self._get_request('/rest-api/ssd-vps/plans/')
        return response


    # Create_VM
    def create_vm(self, location_id, data): #WORKS
###
	#data['label'] is label for the new server;
	#data['hostname'] is hostname for the new server;
	#data['product_name'] is server product name; from get_ssd_vps_plans;
	#data['custom_template_id'] is psiphon custom template id;
        #data['location_id'] is the location of the server from get_vps_locations;
	#data['bill_hourly'] is the billing type; per hour in our case;
        payload = dict()
        #payload = f"{\"label\":\"{str(data['label'])}\",\"hostname\":\"{str(data['hostname'])}\",\"backups\":false,\"product_name\":{str(data['product_name'])}\",\"os_component_code\":\"{str(data['os_component_code'])}\"}"
        payload = (f"{{"
            f"\"label\": \"{data['label']}\", "
            f"\"hostname\": \"{data['hostname']}\", "
            f"\"backups\": false, "
            f"\"bill_hourly\": true, "
            f"\"product_name\": \"{data['product_name']}\", "
            f"\"custom_template_id\": \"{data['custom_template_id']}\""
            f"}}")

        #print(payload)
        url = '/rest-api/ssd-vps/locations/' + str(location_id) + '/servers'
        print("create:" + url)
        print(payload)
        #response = self._post_request('/rest-api/ssd-vps/locations/' + str(data['location_id'])  + '/servers', payload)
        response = self._post_request(url, payload)
        #print(response.text)
        #response = self._post_request('/rest-api/ssd-vps/locations/0/servers', payload)

	    # successfully created
        if response['status_code'] == 201:
	    # response is array of array of response data;
            print(response['data'])
            return response
###
        #json_request = dict()

        #json_request['name'] = name
        #json_request['region_id'] = region
        #json_request['package_id'] = package
        #json_request['os_template_id'] = 69
        #json_request['has_ipv6'] = False
        #json_request['has_private_networking'] = False
        #json_request['ssh_key_ids'] = [357]

        #response =  self._post_request('/virtual_machines', json_request)

        #if response['status'] == 'success':
        #    return response['id']


    # Get VM Status
    def get_vm_server_status(self, location_id, server_id): #WORKS;
        response = self._get_request('/rest-api/ssd-vps/locations/'+ str(location_id) + '/servers/' + str(server_id) + '/status')
        return response


    # Get VM
    def get_vms(self): #WORKS;
        response = self._get_request("/rest-api/ssd-vps/servers")
        return response


    # Stop_VM / Power Off VM
    def stop_vm(self, location_id, server_id): #WORKS;
        response = self._post_request('/rest-api/ssd-vps/locations/'+ str(location_id) + '/servers/' + str(server_id) + '/power/off')
        return response


    # Start_VM
    def start_vm(self, location_id, server_id): #WORKS;
        response = self._post_request('/rest-api/ssd-vps/locations/'+ str(location_id) + '/servers/' + str(server_id) + '/power/on')
        return response

    # Reboot_VM
    def reboot_vm(self, location_id, server_id): #WORKS;
        response = self._post_request('/rest-api/ssd-vps/locations/'+ str(location_id) + '/servers/' + str(server_id) + '/power/reboot')
        return response


    # Get Regions
    def get_vps_locations(self): #WORKS
        response = self._get_request('/rest-api/ssd-vps/locations')
        return response


    # Get VM Server Details
    def get_vm_server_details(self, location_id, server_id): #WORKS
        response = self._get_request('/rest-api/ssd-vps/locations/' + str(location_id) + '/servers/' + str(server_id))
        return response


    def get_status_updates(self): #WORKS
        response = self._get_request('/rest-api/status-updates')
        return response


    def get_custom_os_ssd_vps(self, location_id): #WORKS
        response = self._get_request('/rest-api/ssd-vps/locations/' + str(location_id) + '/templates/custom')
        return response


    def delete_vm_vps_server(self, location_id, server_id): #WORKS
        response = self._delete_request('/rest-api/ssd-vps/locations/' + str(location_id) + '/servers/' + str(server_id))
        return response


    def get_operating_systems(self, location_id) : #WORKS
        response = self._get_request('/rest-api/ssd-vps/locations/' + str(location_id) + '/operating-systems')
        return response


    def get_custom_os_id(location_ids, label):
        count = 0
        location_id = 0
        custom_os_id_info = dict()
        for i in range(len(location_ids)):
            location_id = location_ids[i]
            location_ids_info = get_custom_os_ssd_vps(location_ids[i])
            for j in range(location_ids_info['data']) :
                if location_ids_info['data'][j]['label'] == label:
                    custom_os_id = location_ids_info['data'][j]['id']
                    break
                else:
                    return false
        custom_os_id_info[location_id] : custom_os_id
    return custom_os_id_info


    def provider_id_to_location_server_ids(provider_id) :
        delimiter = "-"
        split_ids = provider_id.split(delimiter)
        return split_ids


    def get_custom_os_id(self, location_ids, label):
        count = 0
        location_id = 0
        custom_os_id_info = dict()
        for i in range(len(location_ids)):
            location_id = location_ids[i]
            location_ids_info = self.get_custom_os_ssd_vps(location_ids[i])
            for j in range(len(location_ids_info['data'])) :
                if location_ids_info['data'][j]['label'] == label:
                    custom_os_id = location_ids_info['data'][j]['id']
                    break
                else:
                    return false
            custom_os_id_info[location_id] = str(custom_os_id)
        return custom_os_id_info


    def get_ssh_keys(self):
        response = self._get_request('/rest-api/ssh-keys/')
        return response


    def get_ssh_key(self, ssh_key) :
        response = self._get_request('/rest-api/ssh-keys/' + str(ssh_key))
        return response


    def add_ssh_key(self, public_key, key_label):
        payload = dict()
        payload = (f"{{"
            f"\"public_key\": \"{public_key}\", "
            f"\"label\": \"{key_label}\""
            f"}}")
        url = '/rest-api/ssh-keys'
        response = self._post_request(url, payload)

        # successfully created
        if response['status_code'] == 200:
            # response is array of array of response data;
            print(response)
            return response
        else: #error
            print(response)
            return response


    def delete_ssh_key(self, ssh_key) :
        response = self._delete_request('/rest-api/ssh-keys/' + str(ssh_key))
        return response


