# Copyright (c) 2012, Psiphon Inc.
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

import os
import json


_CONFIG_FILENAME = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'conf.json')

class Config:
    def __init__(self, privateKeyPemFile: str, privateKeyPassword: str, decryptedEmailRecipient: str,
                 awsRegion: str, s3BucketName: str, psiOpsPath: str, psinetFilePath: str,
                 googleApiKey: str, googleApiServers: list, statsEmailRecipients: list,
                 statsWarningThresholdPerMinute: int, responseEmailAddress: str,
                 defaultSponsorName: str, defaultPropagationChannelName: str,
                 s3ObjectMaxSize: int, numProcesses: int):
        self.privateKeyPemFile = privateKeyPemFile
        self.privateKeyPassword = privateKeyPassword
        self.decryptedEmailRecipient = decryptedEmailRecipient
        self.awsRegion = awsRegion
        self.s3BucketName = s3BucketName
        self.psiOpsPath = psiOpsPath
        self.psinetFilePath = psinetFilePath
        self.googleApiKey = googleApiKey
        self.googleApiServers = googleApiServers
        self.statsEmailRecipients = statsEmailRecipients
        self.statsWarningThresholdPerMinute = statsWarningThresholdPerMinute
        self.responseEmailAddress = responseEmailAddress
        self.defaultSponsorName = defaultSponsorName
        self.defaultPropagationChannelName = defaultPropagationChannelName
        self.s3ObjectMaxSize = s3ObjectMaxSize
        self.numProcesses = numProcesses

    @classmethod
    def from_json(cls, json_data):
        required_keys = {
            "privateKeyPemFile": str,
            "privateKeyPassword": str,
            "decryptedEmailRecipient": str,
            "awsRegion": str,
            "s3BucketName": str,
            "psiOpsPath": str,
            "psinetFilePath": str,
            "googleApiKey": str,
            "googleApiServers": list,
            "statsEmailRecipients": list,
            "statsWarningThresholdPerMinute": int,
            "responseEmailAddress": str,
            "defaultSponsorName": str,
            "defaultPropagationChannelName": str,
            "s3ObjectMaxSize": int,
            "numProcesses": int,
        }

        for key, value_type in required_keys.items():
            if key not in json_data:
                raise ValueError(f"Missing required config key: {key}")
            if not isinstance(json_data[key], value_type):
                raise TypeError(f"Config key '{key}' must be of type {value_type.__name__}, but got {type(json_data[key]).__name__}")

        return cls(**json_data)

# Load and validate the config
with open(_CONFIG_FILENAME, 'r') as conf_fp:
    config = Config.from_json(json.load(conf_fp))
