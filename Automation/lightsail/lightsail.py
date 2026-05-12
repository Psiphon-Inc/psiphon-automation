import os
import typing

import boto3


class Lightsail(object):
    """Thin wrapper around the boto3 Lightsail client.

    Handles pagination internally so callers always receive complete result
    sets.  Every public method returns plain dicts/lists — no boto3 objects
    leak out.
    """

    def __init__(
        self,
        region_name: str = 'us-east-1',
        aws_access_key_id: typing.Optional[str] = None,
        aws_secret_access_key: typing.Optional[str] = None,
    ):
        self.region_name = region_name
        self.client = boto3.client(
            'lightsail',
            region_name=region_name,
            aws_access_key_id=aws_access_key_id or os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=aws_secret_access_key or os.getenv('AWS_SECRET_ACCESS_KEY'),
        )

    def create_instance_from_snapshot(
        self,
        instance_name: str,
        availability_zone: str,
        bundle_id: str,
        instance_snapshot_name: str,
        key_pair_name: typing.Optional[str] = None,
        user_data: typing.Optional[str] = None,
        tags: typing.Optional[list] = None,
        ip_address_type: str = 'ipv4',
    ) -> list:
        kwargs = {
            'instanceNames': [instance_name],
            'availabilityZone': availability_zone,
            'bundleId': bundle_id,
            'instanceSnapshotName': instance_snapshot_name,
            'ipAddressType': ip_address_type,
        }
        if key_pair_name is not None:
            kwargs['keyPairName'] = key_pair_name
        if user_data is not None:
            kwargs['userData'] = user_data
        if tags is not None:
            kwargs['tags'] = tags

        response = self.client.create_instances_from_snapshot(**kwargs)
        return response.get('operations', [])

    def get_instance(self, instance_name: str) -> dict:
        response = self.client.get_instance(instanceName=instance_name)
        return response['instance']

    def list_instances(self) -> list:
        instances = []
        page_token = None
        while True:
            kwargs = {}
            if page_token:
                kwargs['pageToken'] = page_token
            response = self.client.get_instances(**kwargs)
            instances.extend(response.get('instances', []))
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return instances

    def delete_instance(self, instance_name: str, force_delete_add_ons: bool = True) -> list:
        response = self.client.delete_instance(
            instanceName=instance_name,
            forceDeleteAddOns=force_delete_add_ons,
        )
        return response.get('operations', [])

    def get_instance_state(self, instance_name: str) -> str:
        instance = self.get_instance(instance_name)
        return instance['state']['name']

    def list_regions(self, include_availability_zones: bool = True) -> list:
        response = self.client.get_regions(
            includeAvailabilityZones=include_availability_zones,
        )
        return response.get('regions', [])

    def copy_snapshot(
        self,
        source_snapshot_name: str,
        target_snapshot_name: str,
        source_region: str,
        target_region: str,
    ) -> list:
        # copy_snapshot must be called against the TARGET region's endpoint
        target_client = boto3.client(
            'lightsail',
            region_name=target_region,
            aws_access_key_id=self.client._request_signer._credentials.access_key,
            aws_secret_access_key=self.client._request_signer._credentials.secret_key,
        )
        response = target_client.copy_snapshot(
            sourceSnapshotName=source_snapshot_name,
            targetSnapshotName=target_snapshot_name,
            sourceRegion=source_region,
        )
        return response.get('operations', [])

    def list_snapshots(self) -> list:
        snapshots = []
        page_token = None
        while True:
            kwargs = {}
            if page_token:
                kwargs['pageToken'] = page_token
            response = self.client.get_instance_snapshots(**kwargs)
            snapshots.extend(response.get('instanceSnapshots', []))
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return snapshots

    def put_instance_public_ports(self, instance_name: str, port_infos: list) -> list:
        response = self.client.put_instance_public_ports(
            instanceName=instance_name,
            portInfos=port_infos,
        )
        return response.get('operations', [])

    def list_blueprints(self, include_inactive: bool = False) -> list:
        response = self.client.get_blueprints(includeInactive=include_inactive)
        return response.get('blueprints', [])

    def list_bundles(self, include_inactive: bool = False) -> list:
        response = self.client.get_bundles(includeInactive=include_inactive)
        return response.get('bundles', [])
