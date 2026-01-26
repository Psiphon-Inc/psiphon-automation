import requests
import json

class vpsnet:
    def __init__(self, api_key):
        self.__key = api_key
        self.__url = 'https://platform.vps.net'
        self.api_key = api_key
        #self.s = requests.session()
        #if self.api_key:
        #    self.s.headers.update({'Authorization': f'Bearer {self.api_key}'})


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
	    #data['label'] is label for the new server;
	    #data['hostname'] is hostname for the new server;
	    #data['product_name'] is server product name; from get_ssd_vps_plans;
	    #data['custom_template_id'] is psiphon custom template id;
            #data['location_id'] is the location of the server from get_vps_locations;
	    #data['bill_hourly'] is the billing type; per hour in our case;
        url = '/rest-api/ssd-vps/locations/' + str(location_id) + '/servers'
        response = self._post_request(url, data)

        # successfully created
        if response['status_code'] == 201:
	    # response is array of array of response data;
            print(response['data'])
            return response
        else :
            return "Failed To Create VM"
        return "Failed TO Create VM"

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


    def provider_id_to_location_server_ids(provider_id) :
        delimiter = "-"
        split_ids = provider_id.split(delimiter)
        return split_ids


    # gets all custom os ids for all locations
    def get_location_custom_os_ids(self) :
        location_custom_os_ids = dict()
        locations = self.get_vps_locations()
        for i in range(len(locations['data'])):
            location_custom_os_ids[i] = self.get_custom_os_ssd_vps(locations['data'][i]['id'])
        return location_custom_os_ids


    # gets all custom os id for locations with the label: "label" and returns the one matching "location_id"
    def get_custom_os_id(self, location_id, label):
        location_ids = get_location_custom_os_ids()
        custom_os_id_info = dict()
        if location_ids[location_id][0]['label'] == label:
            custom_os_id = location_ids_info[location_id]['data'][0]['id']
        return custom_os_id


    def get_server_id_by_host_id(self, host_id) :
        all_vps_vms = self.get_vms()
        for i in range(len(all_vps_vms['data'])) :
            if all_vps_vms['data'][i]['hostname'] == host_id :
                server_id = all_vps_vms['data'][i]['id']
        return server_id


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


