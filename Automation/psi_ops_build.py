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
import traceback
import sys


#==== Build File Locations  ===================================================

APPLICATION_TITLE = 'Psiphon 3' # (TODO: sync this value with client source code; only used for testing)
SOURCE_ROOT = os.path.join(os.path.abspath('..'), 'Client')
BANNER_ROOT = os.path.join(os.path.abspath('..'), 'Data', 'Banners')
CLIENT_SOLUTION_FILENAME = os.path.join(SOURCE_ROOT, 'psiclient.sln')
CODE_SIGNING_PFX_FILENAME = os.path.join(os.path.abspath('..'), 'Data', 'CodeSigning', 'test-code-signing-package.pfx')
BANNER_FILENAME = os.path.join(SOURCE_ROOT, 'psiclient', 'banner.bmp')
CUSTOM_EMAIL_BANNER = 'email.bmp'
EMAIL_BANNER_FILENAME = os.path.join(SOURCE_ROOT, 'psiclient', 'email.bmp')
EMBEDDED_VALUES_FILENAME = os.path.join(SOURCE_ROOT, 'psiclient', 'embeddedvalues.h')
EXECUTABLE_FILENAME = os.path.join(SOURCE_ROOT, 'Release', 'psiphon.exe')
BUILDS_ROOT = os.path.join('.', 'Builds')
BUILD_FILENAME_TEMPLATE = 'psiphon-%s-%s.exe'

VISUAL_STUDIO_ENV_BATCH_FILENAME = 'C:\\Program Files\\Microsoft Visual Studio 10.0\\VC\\vcvarsall.bat'
VISUAL_STUDIO_ENV_BATCH_FILENAME_x86 = 'C:\\Program Files (x86)\\Microsoft Visual Studio 10.0\\VC\\vcvarsall.bat'

SIGN_TOOL_FILENAME = 'C:\\Program Files\\Microsoft SDKs\\Windows\\v7.1\\Bin\\signtool.exe'
SIGN_TOOL_FILENAME_ALT = 'C:\\Program Files\\Microsoft SDKs\\Windows\\v7.0A\\Bin\\signtool.exe'

UPX_FILENAME = '.\Tools\upx.exe'

# Check usage restrictions here before using this service:
# http://www.whatismyip.com/faq/automation.asp
CHECK_IP_ADDRESS_URL = 'http://automation.whatismyip.com/n09230945.asp'

# if psi_build_config.py exists, load it and use psi_build_config.DATA_ROOT as the data root dir

if os.path.isfile('psi_data_config.py'):
    import psi_data_config
    BANNER_ROOT = os.path.join(psi_data_config.DATA_ROOT, 'Banners')
    CODE_SIGNING_PFX_FILENAME = os.path.join(psi_data_config.DATA_ROOT, 'CodeSigning', psi_data_config.CODE_SIGNING_PACKAGE_FILENAME)
    CHECK_IP_ADDRESS_URL = psi_data_config.CHECK_IP_ADDRESS_URL


#==============================================================================


def build_client_executable():
    visual_studio_env_batch_filename = VISUAL_STUDIO_ENV_BATCH_FILENAME
    if not os.path.isfile(visual_studio_env_batch_filename):
        visual_studio_env_batch_filename = VISUAL_STUDIO_ENV_BATCH_FILENAME_x86
    signtool_filename = SIGN_TOOL_FILENAME
    if not os.path.isfile(signtool_filename):
        signtool_filename = SIGN_TOOL_FILENAME_ALT
    commands = [
        'msbuild "%s" /v:quiet /t:Rebuild /p:Configuration=Release\n' % (CLIENT_SOLUTION_FILENAME,),
        '"%s" -qq "%s"\n' % (UPX_FILENAME, EXECUTABLE_FILENAME),
        '"%s" sign /f "%s" %s\n' % (signtool_filename,
                                             CODE_SIGNING_PFX_FILENAME,
                                             EXECUTABLE_FILENAME)]
    command_filename = 'build.cmd'
    for command in commands:
        with open(command_filename, 'w') as file:
            file.write('call "%s" x86\n' % (visual_studio_env_batch_filename,))
            file.write(command)
        try:
            if 0 != subprocess.call(command_filename):
                raise Exception('build failed')
        finally:
            os.remove(command_filename)


def write_embedded_values(propagation_channel_id,
                          sponsor_id,
                          client_version,
                          embedded_server_list,
                          ignore_system_server_list=False,
                          ignore_vpn_relay=False):
    template = textwrap.dedent('''
        #pragma once

        static const char* PROPAGATION_CHANNEL_ID = "%s";

        static const char* SPONSOR_ID = "%s";

        // NOTE: if we put this in resources instead/as well, it would show up
        //       in Explorer properties tab, etc.
        static const char* CLIENT_VERSION = "%s";

        static const char* EMBEDDED_SERVER_LIST = "%s";

        // When this flag is set, only the embedded server list is used. This is for testing only.
        static const int IGNORE_SYSTEM_SERVER_LIST = %d;

        // When this flag is set, VPN relay is skipped. This is for testing only.
        static const int IGNORE_VPN_RELAY = %d;
        ''')
    with open(EMBEDDED_VALUES_FILENAME, 'w') as file:
        file.write(template % (propagation_channel_id,
                               sponsor_id,
                               client_version,
                               '\\n'.join(embedded_server_list),
                               (1 if ignore_system_server_list else 0),
                               (1 if ignore_vpn_relay else 0)))


def build_client(
        propagation_channel_id,
        sponsor_id,
        banner,
        encoded_server_list,
        version,
        test=False):
    try:
        # Helper: store original files for restore after script
        # (to minimize chance of checking values into source control)
        def store_to_temporary_file(filename):
            temporary_file = tempfile.NamedTemporaryFile()
            with open(filename, 'rb') as file:
                temporary_file.write(file.read())
                temporary_file.flush()
            return temporary_file
        banner_tempfile = store_to_temporary_file(BANNER_FILENAME)
        email_banner_tempfile = store_to_temporary_file(EMAIL_BANNER_FILENAME)
        embedded_values_tempfile = store_to_temporary_file(EMBEDDED_VALUES_FILENAME)

        # Copy custom email banner from Data to source tree
        # (there's only one custom email banner for all sponsors)
        banner_source_path = os.path.join(BANNER_ROOT, CUSTOM_EMAIL_BANNER)
        shutil.copyfile(banner_source_path, EMAIL_BANNER_FILENAME)

        # Copy sponsor banner image file from Data to Client source tree
        if banner:
            with open(BANNER_FILENAME, 'wb') as banner_file:
                banner_file.write(banner)

        # overwrite embedded values source file
        write_embedded_values(
            propagation_channel_id,
            sponsor_id,
            version,
            encoded_server_list,
            ignore_system_server_list=test)

        # build
        build_client_executable()

        if test:
            return EXECUTABLE_FILENAME

        # rename and copy executable to Builds folder
        # e.g., Builds/psiphon-3A885577DD84EF13-8BB28C1A8E8A9ED9.exe
        if not os.path.exists(BUILDS_ROOT):
            os.makedirs(BUILDS_ROOT)
        build_destination_path = os.path.join(
                                    BUILDS_ROOT,
                                    BUILD_FILENAME_TEMPLATE % (propagation_channel_id,
                                                               sponsor_id))
        shutil.copyfile(EXECUTABLE_FILENAME, build_destination_path)

        print 'Build: SUCCESS'

        return build_destination_path

    except:
        print 'Build: FAILURE'
        raise

    finally:

        # attempt to restore original source files
        try:
            def restore_from_temporary_file(temporary_file, filename):
                with open(filename, 'wb') as file:
                    temporary_file.seek(0)
                    file.write(temporary_file.read())
            restore_from_temporary_file(banner_tempfile, BANNER_FILENAME)
            restore_from_temporary_file(email_banner_tempfile, EMAIL_BANNER_FILENAME)
            restore_from_temporary_file(embedded_values_tempfile, EMBEDDED_VALUES_FILENAME)
        except:
            pass
