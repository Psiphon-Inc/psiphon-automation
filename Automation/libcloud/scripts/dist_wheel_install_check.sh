#!/usr/bin/env bash
#  Licensed to the Apache Software Foundation (ASF) under one
#  or more contributor license agreements.  See the NOTICE file
#  distributed with this work for additional information
#  regarding copyright ownership.  The ASF licenses this file
#  to you under the Apache License, Version 2.0 (the
#  "License"); you may not use this file except in compliance
#  with the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing,
#  software distributed under the License is distributed on an
#  "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#  KIND, either express or implied.  See the License for the
#  specific language governing permissions and limitations
#  under the License.

# Verify library installs without any dependencies when using built wheel
set -e

function cleanup() {
    rm -f dist/apache*libcloud*.*
}

cleanup

trap cleanup EXIT

echo "Running dist wheel install checks"
python --version

# Ensure those packages are not installed. If they are, it indicates unclean
# environment so those checks won't work correctly
pip show requests && exit 1
pip show typing && exit 1
pip show enum34 && exit 1
pip show apache-libcloud && exit 1
rm -rf dist/apache_libcloud-*.whl

pip install build
python -m build
pip install dist/apache_libcloud-*.whl

# Verify all dependencies were installed
pip show requests
pip show typing && exit 1
pip show enum34 && exit 1

echo "Done"
