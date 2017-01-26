import requests
import json

class Api:
    def __init__(self, key):
        self.__key = key
        self.__url = 'https://api.vps247.com'

    def _get_request(self, endpoint):
        try:
            response = requests.get(self.__url + endpoint, headers={'X-Api-Key': self.__key})

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
            if endpoint == '/virtual_machines':
                # Create VM
                response = requests.post(self.__url + endpoint, headers={'X-Api-Key': self.__key, 'Content-Type': 'application/json'}, data=json.dumps(payload))
            else:
                # Control VM
                response = requests.post(self.__url + endpoint, headers={'X-Api-Key': self.__key})

            if response.ok:
                # Success - 201 Created or 200 Accepted
                return json.loads(response.content)
            else:
                return response.raise_for_status()
        except Exception as e:
            raise e

    def _delete_request(self, endpoint):
        try:
            response = requests.delete(self.__url + endpoint, headers={'X-Api-Key': self.__key})

            if response.ok:
                return True
            else:
                return response.raise_for_status()
        except Exception as e:
            raise e

    # Create_VM
    def create_vm(self, name, region, package=4):
        json_request = dict()

        json_request['name'] = name
        json_request['region_id'] = region['id']
        json_request['package_id'] = package
        json_request['os_template_id'] = 34
        json_request['has_ipv6'] = False
        json_request['has_private_networking'] = False

        response =  self._post_request('/virtual_machines', json_request)

        if response['status'] == 'success':
            return response['id']

    # Delete_VM !!!DO NOT USE THIS FUNCTION!!!
    def delete_vm(self, id):
        vm = self._get_request('/virtual_machines/' + id)
        if vm['state'] != 'off':
            response = self.kill_vm(id)
            if response == 'success':
                check = 3
                while check > 0:
                    state = self._get_request('/virtual_machines/' + id)['state']
                    if state == 'off':
                        check = 0
                    else:
                        time.sleep(3)
                        check -= 1
                delete_response = self._delete_request('/virtual_machines/' + id)
                return response['status']
        else:
            delete_response = self._delete_request('/virtual_machines/' + id)
            return response['status']

    # Stop_VM
    def stop_vm(self, id):
        response = self._post_request('/virtual_machines/' + id + '/stop')
        return response['status']

    def kill_vm(self, id):
        response = self._post_request('/virtual_machines/' + id + '/kill')
        return response['status']


    # Start_VM
    def start_vm(self, id):
        response = self._post_request('/virtual_machines/' + id + '/start')
        return response['status']

    # Restart_VM
    def restart_vm(self, id):
        response = self._post_request('/virtual_machines/' + id + '/restart')
        return response['status']

    # Get Regions
    def get_all_regions(self):
        response = self._get_request('/regions')
        return response
