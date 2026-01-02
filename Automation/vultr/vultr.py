import os
import typing
import requests

class Vultr(object):
    API_URL = 'https://api.vultr.com/v2'

    def __init__(self, api_key: typing.Union[str, None]):
        """
        :param str api_key: Vultr API Key or VULTR_API_KEY environment variable
        """
        self.api_key = api_key or os.getenv('VULTR_API_KEY')
        self.s = requests.session()
        if self.api_key:
            self.s.headers.update({'Authorization': f'Bearer {self.api_key}'})

    # Remove all extra functions
    # Only leave necessary functions
    def list_os(self):
        url = f'{self.API_URL}/os'
        return self._get(url)['os']

    def list_plans(self):
        url = f'{self.API_URL}/plans'
        return self._get(url)['plans']

    def list_regions(self):
        url = f'{self.API_URL}/regions'
        return self._get(url)['regions']

    def list_instances(self):
        url = f'{self.API_URL}/instances'
        return self._get(url)['instances']

    def get_instance(self, instance: typing.Union[str, dict]):
        instance_id = self._get_obj_key(instance)
        url = f'{self.API_URL}/instances/{instance_id}'
        return self._get(url)['instance']

    def create_instance(self, region: str, plan: str, **kwargs):
        data = {'region': region, 'plan': plan}
        data.update(kwargs)
        url = f'{self.API_URL}/instances'
        return self._post(url, data)['instance']

    def update_instance(self, instance: typing.Union[str, dict], **kwargs):
        instance_id = self._get_obj_key(instance)
        url = f'{self.API_URL}/instances/{instance_id}'
        return self._patch(url, kwargs)['instance']

    def delete_instance(self, instance: typing.Union[str, dict]):
        instance_id = self._get_obj_key(instance)
        url = f'{self.API_URL}/instances/{instance_id}'
        return self._delete(url)

    def list_keys(self):
        url = f'{self.API_URL}/ssh-keys'
        return self._get(url)['ssh_keys']

    def get_key(self, key: typing.Union[str, dict]):
        key_id = self._get_obj_key(key)
        url = f'{self.API_URL}/ssh-keys/{key_id}'
        return self._get(url)['ssh_key']

    def create_key(self, name: str, key: str, **kwargs):
        data = {'name': name, 'ssh_key': key}
        data.update(kwargs)
        url = f'{self.API_URL}/ssh-keys'
        return self._post(url, data)['ssh_key']

    def update_key(self, key: typing.Union[str, dict], **kwargs):
        key_id = self._get_obj_key(key)
        url = f'{self.API_URL}/ssh-keys/{key_id}'
        return self._patch(url, kwargs)['ssh_key']

    def delete_key(self, key: typing.Union[str, dict]):
        key_id = self._get_obj_key(key)
        url = f'{self.API_URL}/ssh-keys/{key_id}'
        return self._delete(url)

    def list_scripts(self):
        url = f'{self.API_URL}/startup-scripts'
        return self._get(url)['startup_scripts']

    def get_script(self, script: typing.Union[str, dict]):
        script_id = self._get_obj_key(script)
        url = f'{self.API_URL}/startup-scripts/{script_id}'
        return self._get(url)['startup_script']

    def create_script(self, name: str, script: str, **kwargs):
        data = {'name': name, 'script': script}
        data.update(kwargs)
        url = f'{self.API_URL}/startup-scripts'
        return self._post(url, data)['startup_script']

    def update_script(self, script: typing.Union[str, dict], **kwargs):
        script_id = self._get_obj_key(script)
        url = f'{self.API_URL}/startup-scripts/{script_id}'
        return self._patch(url, kwargs)['startup_script']

    def delete_script(self, script: typing.Union[str, dict]):
        script_id = self._get_obj_key(script)
        url = f'{self.API_URL}/startup-scripts/{script_id}'
        return self._delete(url)

    def list_ipv4(self, instance: typing.Union[str, dict]):
        instance_id = self._get_obj_key(instance)
        url = f'{self.API_URL}/instances/{instance_id}/ipv4'
        return self._get(url)['ipv4s']

    def create_ipv4(self, instance: typing.Union[str, dict], **kwargs):
        instance_id = self._get_obj_key(instance)
        url = f'{self.API_URL}/instances/{instance_id}/ipv4'
        return self._post(url, kwargs)['ipv4']

    def delete_ipv4(self, instance: typing.Union[str, dict]):
        instance_id = self._get_obj_key(instance)
        url = f'{self.API_URL}/instances/{instance_id}/ipv4'
        return self._delete(url)

    @staticmethod
    def filter_keys(keys: list, name: str) -> dict:
        try:
            return next(d for d in keys if d['name'].lower() == name.lower())
        except StopIteration:
            return {}

    @staticmethod
    def filter_os(os_list: list, name: str) -> dict:
        try:
            return next(d for d in os_list if d['name'].lower() == name.lower())
        except StopIteration:
            return {}

    @staticmethod
    def filter_scripts(scripts: list, name: str) -> dict:
        try:
            return next(d for d in scripts if d['name'].lower() == name.lower())
        except StopIteration:
            return {}

    @staticmethod
    def filter_regions(regions: list, locations: list) -> list:
        return [d for d in regions if d['id'] in locations]

    def _get(self, url):
        r = self.s.get(url, timeout=10)
        if not r.ok:
            r.raise_for_status()
        return r.json()

    def _post(self, url, data):
        r = self.s.post(url, json=data, timeout=10)
        if not r.ok:
            r.raise_for_status()
        return r.json()

    def _patch(self, url, data):
        r = self.s.patch(url, json=data, timeout=10)
        if not r.ok:
            r.raise_for_status()
        return r.json()

    def _delete(self, url):
        r = self.s.delete(url, timeout=10)
        if not r.ok:
            r.raise_for_status()
        return None

    @staticmethod
    def _get_obj_key(obj, key='id'):
        if isinstance(obj, str):
            return obj
        elif isinstance(obj, int):
            return str(obj)
        elif isinstance(obj, dict):
            if key in obj:
                return obj[key]
        else:
            raise ValueError(f'Unable to parse object: {key}')
