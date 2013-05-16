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
import psi_utils

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
BUILDS_ROOT = os.path.join('.', 'Builds', 'Windows')
BUILD_FILENAME_TEMPLATE = 'psiphon-%s-%s.exe'

FEEDBACK_SOURCE_ROOT = os.path.join('.', 'FeedbackSite')
FEEDBACK_HTML_SOURCE_PATH = os.path.join(FEEDBACK_SOURCE_ROOT, 'feedback.html')
FEEDBACK_HTML_PATH = os.path.join(SOURCE_ROOT, 'psiclient', 'feedback.html')

VISUAL_STUDIO_ENV_BATCH_FILENAME = 'C:\\Program Files\\Microsoft Visual Studio 10.0\\VC\\vcvarsall.bat'
VISUAL_STUDIO_ENV_BATCH_FILENAME_x86 = 'C:\\Program Files (x86)\\Microsoft Visual Studio 10.0\\VC\\vcvarsall.bat'

SIGN_TOOL_FILENAME = 'C:\\Program Files\\Microsoft SDKs\\Windows\\v7.1\\Bin\\signtool.exe'
SIGN_TOOL_FILENAME_ALT = 'C:\\Program Files\\Microsoft SDKs\\Windows\\v7.0A\\Bin\\signtool.exe'

UPX_FILENAME = '.\Tools\upx.exe'

# if psi_build_config.py exists, load it and use psi_build_config.DATA_ROOT as the data root dir

if os.path.isfile('psi_data_config.py'):
    import psi_data_config
    BANNER_ROOT = os.path.join(psi_data_config.DATA_ROOT, 'Banners')
    CODE_SIGNING_PFX_FILENAME = os.path.join(psi_data_config.DATA_ROOT, 'CodeSigning', psi_data_config.CODE_SIGNING_PACKAGE_FILENAME)


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
        '"%s" sign /t http://timestamp.digicert.com /f "%s" "%s"\n' % (signtool_filename,
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
                          remote_server_list_signature_public_key,
                          remote_server_list_url,
                          feedback_encryption_public_key,
                          feedback_upload_server,
                          feedback_upload_path,
                          feedback_upload_server_headers,
                          info_link_url,
                          upgrade_signature_public_key,
                          upgrade_url,
                          ignore_system_server_list=False):
    template = textwrap.dedent('''
        #pragma once

        static const char* PROPAGATION_CHANNEL_ID = "%s";

        static const char* SPONSOR_ID = "%s";

        // NOTE: if we put this in resources instead/as well, it would show up
        //       in Explorer properties tab, etc.
        static const char* CLIENT_VERSION = "%s";

        #include <string.h>
        static string embedded_server_list = string() + "%s";
        static const char* EMBEDDED_SERVER_LIST = embedded_server_list.c_str();

        // When this flag is set, only the embedded server list is used. This is for testing only.
        static const int IGNORE_SYSTEM_SERVER_LIST = %d;

        static const char* REMOTE_SERVER_LIST_SIGNATURE_PUBLIC_KEY = "%s";
        static const char* REMOTE_SERVER_LIST_ADDRESS = "%s";
        static const char* REMOTE_SERVER_LIST_REQUEST_PATH = "%s";

        // These values are used when uploading diagnostic info
        static const char* FEEDBACK_ENCRYPTION_PUBLIC_KEY = "%s";
        static const char* FEEDBACK_DIAGNOSTIC_INFO_UPLOAD_SERVER = "%s";
        static const char* FEEDBACK_DIAGNOSTIC_INFO_UPLOAD_PATH = "%s";
        static const char* FEEDBACK_DIAGNOSTIC_INFO_UPLOAD_SERVER_HEADERS = "%s";

        // NOTE: Info link may be opened when not tunneled
        static const TCHAR* INFO_LINK_URL
            = _T("%s");

        static const char* UPDATE_SIGNATURE_PUBLIC_KEY = "%s";
        static const char* UPDATE_ADDRESS = "%s";
        static const char* UPDATE_REQUEST_PATH = "%s";
        ''')
    with open(EMBEDDED_VALUES_FILENAME, 'w') as file:
        file.write(template % (propagation_channel_id,
                               sponsor_id,
                               client_version,
                               '\\n\" + \"'.join(embedded_server_list),
                               (1 if ignore_system_server_list else 0),
                               remote_server_list_signature_public_key,
                               remote_server_list_url[1],
                               remote_server_list_url[2],
                               feedback_encryption_public_key,
                               feedback_upload_server,
                               feedback_upload_path,
                               feedback_upload_server_headers,
                               info_link_url,
                               upgrade_signature_public_key,
                               upgrade_url[1],
                               upgrade_url[2]))


def build_client(
        propagation_channel_id,
        sponsor_id,
        banner,
        encoded_server_list,
        remote_server_list_signature_public_key,
        remote_server_list_url,
        feedback_encryption_public_key,
        feedback_upload_server,
        feedback_upload_path,
        feedback_upload_server_headers,
        info_link_url,
        upgrade_signature_public_key,
        upgrade_url,
        version,
        test=False):

    try:
        # Backup/restore original files minimize chance of checking values into source control
        backup = psi_utils.TemporaryBackup(
            [BANNER_FILENAME, EMAIL_BANNER_FILENAME, FEEDBACK_HTML_PATH])

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
            remote_server_list_signature_public_key,
            remote_server_list_url,
            feedback_encryption_public_key,
            feedback_upload_server,
            feedback_upload_path,
            feedback_upload_server_headers,
            info_link_url,
            upgrade_signature_public_key,
            upgrade_url,
            ignore_system_server_list=test)

        # copy feedback.html
        shutil.copyfile(FEEDBACK_HTML_SOURCE_PATH, FEEDBACK_HTML_PATH)

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
        backup.restore_all()
