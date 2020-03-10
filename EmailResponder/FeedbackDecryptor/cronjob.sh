#!/bin/bash

# Copyright (c) 2020, Psiphon Inc.
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

# Update source
hg pull -u

# Update the local copy of psinet
cd ../../Automation
python ./psi_update_stats_dat.py
cd -

# Restart services to use the new code and psinet
sudo systemctl restart s3decryptor.service
sudo systemctl restart mailsender.service
sudo systemctl restart autoresponder.service
sudo systemctl restart statschecker.service
