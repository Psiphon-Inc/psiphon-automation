#!/usr/bin/python
#
# Copyright (c) 2011, Psiphon Inc.
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
#

import os
import shutil
import subprocess
import textwrap
import tempfile
import time
import traceback
import sys
sys.path.insert(0, os.path.abspath(os.path.join('..', 'Data')))
import psi_db

SOURCE_ROOT = os.path.join(os.path.abspath('..'), 'Client')
BANNER_ROOT = os.path.join(os.path.abspath('..'), 'Data', 'Banners')
CLIENT_SOLUTION_FILENAME = os.path.join(SOURCE_ROOT, 'psiclient.sln')
VISUAL_STUDIO_ENV_BATCH_FILENAME = 'C:\\Program Files\\Microsoft Visual Studio 10.0\\VC\\vcvarsall.bat'
VISUAL_STUDIO_ENV_BATCH_FILENAME_x86 = 'C:\\Program Files (x86)\\Microsoft Visual Studio 10.0\\VC\\vcvarsall.bat'
SIGN_TOOL_FILENAME = 'C:\\Program Files\\Microsoft SDKs\\Windows\\v7.1\\Bin\\signtool.exe'
SIGN_TOOL_FILENAME_x86 = 'C:\\Program Files (x86)\\Microsoft SDKs\\Windows\\v7.1\\Bin\\signtool.exe'
CODE_SIGNING_PFX_FILENAME = os.path.join(os.path.abspath('..'), 'Data', 'CodeSigning', 'test-code-sigining-package.pfx')
BANNER_FILENAME = os.path.join(SOURCE_ROOT, 'psiclient', 'banner.bmp')
EMBEDDED_VALUES_FILENAME = os.path.join(SOURCE_ROOT, 'psiclient', 'embeddedvalues.h')
EXECUTABLE_FILENAME = os.path.join(SOURCE_ROOT, 'Release', 'psiphony.exe')
BUILDS_ROOT = os.path.join('.', 'Builds')


def build_client():
    visual_studio_env_batch_filename = VISUAL_STUDIO_ENV_BATCH_FILENAME
    if not os.path.isfile(visual_studio_env_batch_filename):
        visual_studio_env_batch_filename = VISUAL_STUDIO_ENV_BATCH_FILENAME_x86
    signtool_filename = SIGN_TOOL_FILENAME
    if not os.path.isfile(signtool_filename):
        signtool_filename = SIGN_TOOL_FILENAME_x86
    # TODO: delete build.cmd
    with open('build.cmd', 'w') as file:
        file.write('call "%s" x86\n' % (visual_studio_env_batch_filename,))
        file.write('msbuild %s /t:Rebuild /p:Configuration=Release\n' % (CLIENT_SOLUTION_FILENAME,))
        file.write('"%s" sign /f %s %s\n' % (signtool_filename,
                                             CODE_SIGNING_PFX_FILENAME,
                                             EXECUTABLE_FILENAME))
    if 0 != subprocess.call('build.cmd'):
        raise Exception('build failed')


def write_embedded_values(client_id, sponsor_id, client_version, embedded_server_list):
    template = textwrap.dedent('''
        #pragma once

        static const char* CLIENT_ID = "%s";

        static const char* SPONSOR_ID = "%s";

        // TODO: put this in resources instead
        static const char* CLIENT_VERSION = "%s";

        static const char* EMBEDDED_SERVER_LIST = "%s";
        ''')
    with open(EMBEDDED_VALUES_FILENAME, 'w') as file:
        file.write(template % (client_id,
                               sponsor_id,
                               client_version,
                               '\\n'.join(embedded_server_list)))


if __name__ == "__main__":

    try:
        psi_db.validate_data()
        sponsors = psi_db.get_sponsors()
        clients = psi_db.get_clients()
        versions = psi_db.get_versions()

        # store original files for restore after script
        # (to minimize chance of checking values into source control)
        def store_to_temporary_file(filename):
            temporary_file = tempfile.NamedTemporaryFile()
            with open(filename, 'r') as file:
                temporary_file.write(file.read())
                temporary_file.flush()
            return temporary_file

        banner_tempfile = store_to_temporary_file(BANNER_FILENAME)
        embedded_values_tempfile = store_to_temporary_file(EMBEDDED_VALUES_FILENAME)

        for sponsor in sponsors:
            for client in clients:

                # copy sponsor banner image file from Data to Client source tree
                banner_source_path = os.path.join(BANNER_ROOT, sponsor.Banner_Filename)
                shutil.copyfile(banner_source_path, BANNER_FILENAME)

                # overwrite embedded values source file
                write_embedded_values(
                    client.Client_ID,
                    sponsor.Sponsor_ID,
                    versions[0].Client_Version,
                    psi_db.get_encoded_server_list(client.Client_ID))

                # build
                build_client()

                # TODO: code signing

                # rename and copy executable to Builds folder
                # e.g., Builds/psiphonv-3A885577DD84EF13-8BB28C1A8E8A9ED9.exe
                if not os.path.exists(BUILDS_ROOT):
                    os.makedirs(BUILDS_ROOT)
                build_destination_path = os.path.join(
                                            BUILDS_ROOT,
                                            'psiphon-%s-%s.exe' % (client.Client_ID,
                                                                   sponsor.Sponsor_ID))
                shutil.copyfile(EXECUTABLE_FILENAME, build_destination_path)

        print 'psi_build: SUCCESS'

    except:
        traceback.print_exc()
        print 'psi_build: FAIL'

    finally:

        # attempt to restore original source files
        try:
            def restore_from_temporary_file(temporary_file, filename):
                with open(filename, 'w') as file:
                    temporary_file.seek(0)
                    file.write(temporary_file.read())
            restore_from_temporary_file(banner_tempfile, BANNER_FILENAME)
            restore_from_temporary_file(embedded_values_tempfile, EMBEDDED_VALUES_FILENAME)
        except:
            traceback.print_exc()
            pass