#!/bin/bash
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
set -e

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

pushd "${SCRIPT_DIR}/../"

# We redirect stderr to /dev/null since sometimes setuptools may print pyproject
# related warning
VERSION=$(python setup.py --version 2> /dev/null)
popd

pushd "${SCRIPT_DIR}"

echo "Uploading packages"
# shellcheck disable=SC2086
ls ./*$VERSION*.tar.gz ./*$VERSION*.whl ./*$VERSION*.tar.gz.asc
# shellcheck disable=SC2086
twine check ./*$VERSION*.tar.gz ./*$VERSION*.whl
# shellcheck disable=SC2086
twine upload ./*$VERSION*.tar.gz ./*$VERSION*.whl ./*$VERSION*.tar.gz.asc

popd
