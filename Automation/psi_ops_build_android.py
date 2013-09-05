#!/usr/bin/python
#
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
#

import os
import shutil
import shlex
import textwrap
import sys
import fileinput
import psi_utils
import utils
from cogapp import Cog


#==== Build File Locations  ===================================================

SOURCE_ROOT = os.path.join(os.path.abspath('..'), 'Android')

PSIPHON_SOURCE_ROOT = os.path.join(SOURCE_ROOT, 'PsiphonAndroid')
PSIPHON_LIB_SOURCE_ROOT = os.path.join(SOURCE_ROOT, 'PsiphonAndroidLibrary')
ZIRCO_SOURCE_ROOT = os.path.join(SOURCE_ROOT, 'zirco-browser')

BANNER_ROOT = os.path.join(os.path.abspath('..'), 'Data', 'Banners')
KEYSTORE_FILENAME = os.path.join(os.path.abspath('..'), 'Data', 'CodeSigning', 'test.keystore')
KEYSTORE_PASSWORD = 'password'

BANNER_FILENAME = os.path.join(PSIPHON_SOURCE_ROOT, 'res', 'drawable', 'banner.bmp')
EMBEDDED_VALUES_FILENAME = os.path.join(PSIPHON_LIB_SOURCE_ROOT, 'src', 'com', 'psiphon3', 'psiphonlibrary', 'EmbeddedValues.java')
ANDROID_MANIFEST_FILENAME = os.path.join(PSIPHON_SOURCE_ROOT, 'AndroidManifest.xml')

RELEASE_UNSIGNED_APK_FILENAME = os.path.join(PSIPHON_SOURCE_ROOT, 'bin', 'PsiphonAndroid-release-unsigned.apk')
RELEASE_SIGNED_APK_FILENAME = os.path.join(PSIPHON_SOURCE_ROOT, 'bin', 'PsiphonAndroid-release-signed-unaligned.apk')
ZIPALIGNED_APK_FILENAME = os.path.join(PSIPHON_SOURCE_ROOT, 'bin', 'PsiphonAndroid-release.apk')

LIB_FILENAME = 'PsiphonAndroidLibrary.jar'

BUILDS_ROOT = os.path.join('.', 'Builds', 'Android')
APK_FILENAME_TEMPLATE = 'PsiphonAndroid-%s-%s.apk'
LIBS_ROOT = os.path.join('.', 'Builds', 'AndroidLibrary')
LIB_FILENAME_TEMPLATE = 'PsiphonAndroidLibrary-%s-%s.jar'

FEEDBACK_SOURCE_ROOT = os.path.join('.', 'FeedbackSite')
FEEDBACK_HTML_PATH = os.path.join(FEEDBACK_SOURCE_ROOT, 'feedback.html')
PSIPHON_ASSETS = os.path.join(PSIPHON_SOURCE_ROOT, 'assets')

# if psi_build_config.py exists, load it and use psi_build_config.DATA_ROOT as the data root dir

if os.path.isfile('psi_data_config.py'):
    import psi_data_config
    BANNER_ROOT = os.path.join(psi_data_config.DATA_ROOT, 'Banners')
    KEYSTORE_FILENAME = os.path.join(psi_data_config.DATA_ROOT, 'CodeSigning', psi_data_config.KEYSTORE_FILENAME)


#==============================================================================


def build_apk():

    commands = [
        'android update lib-project -p "%s"' % (ZIRCO_SOURCE_ROOT,),
        'android update lib-project -p "%s"' % (PSIPHON_LIB_SOURCE_ROOT,),
        'android update project -p "%s"' % (PSIPHON_SOURCE_ROOT,),
        'ant -q -f "%s" clean' % (os.path.join(ZIRCO_SOURCE_ROOT, 'build.xml'),),
        'ant -q -f "%s" clean' % (os.path.join(PSIPHON_LIB_SOURCE_ROOT, 'build.xml'),),
        'ant -q -f "%s" clean' % (os.path.join(PSIPHON_SOURCE_ROOT, 'build.xml'),),
        'ant -q -f "%s" release' % (os.path.join(PSIPHON_SOURCE_ROOT, 'build.xml'),),
        'jarsigner -sigalg SHA1withRSA -digestalg SHA1 -keystore "%s" -storepass %s "%s" psiphon' % (
            KEYSTORE_FILENAME, KEYSTORE_PASSWORD, RELEASE_UNSIGNED_APK_FILENAME),
        'move "%s" "%s"' % (RELEASE_UNSIGNED_APK_FILENAME, RELEASE_SIGNED_APK_FILENAME),
        'zipalign -f 4 "%s" "%s"' % (RELEASE_SIGNED_APK_FILENAME, ZIPALIGNED_APK_FILENAME)]

    for command in commands:
        if 0 != os.system(command):
            raise Exception('build failed')


def write_embedded_values(propagation_channel_id,
                          sponsor_id,
                          client_version,
                          embedded_server_list,
                          remote_server_list_signature_public_key,
                          feedback_encryption_public_key,
                          remote_server_list_url,
                          info_link_url,
                          upgrade_signature_public_key,
                          upgrade_url,
                          get_new_version_url,
                          get_new_version_email,
                          propagator_managed_upgrades,
                          ignore_system_server_list=False):
    utils.set_embedded_values(client_version,
                              '","'.join(embedded_server_list),
                              feedback_encryption_public_key,
                              info_link_url,
                              '',
                              '',
                              upgrade_url[0] + '://' + upgrade_url[1] + '/' + upgrade_url[2],
                              upgrade_signature_public_key,
                              get_new_version_url,
                              get_new_version_email,
                              get_new_version_url + '#other_frequently_asked_questions',
                              get_new_version_url + '#what_user_information_does_psiphon_3_collect',
                              propagator_managed_upgrades,
                              propagation_channel_id,
                              sponsor_id,
                              remote_server_list_url[0] + '://' + remote_server_list_url[1] + '/' + remote_server_list_url[2],
                              remote_server_list_signature_public_key)
                              
    cog_args = shlex.split('cog -U -I "%s" -o "%s" -D buildname="" "%s"' % (os.getcwd(), EMBEDDED_VALUES_FILENAME, EMBEDDED_VALUES_FILENAME + '.stub'))
    ret_error = Cog().main(cog_args)

    if ret_error != 0:
        print 'Cog failed with error: %d' % ret_error
        raise


def write_android_manifest_version(client_version):
    for line in fileinput.input(ANDROID_MANIFEST_FILENAME, inplace=1):
        sys.stdout.write(
            line.replace(
                'android:versionCode=\"0\"',
                'android:versionCode=\"%s\"' % (client_version,)).
                    replace(
                        'android:versionName=\"0.0\"',
                        'android:versionName=\"%s\"' % (client_version,)))


def build_client(
        propagation_channel_id,
        sponsor_id,
        banner,
        encoded_server_list,
        remote_server_list_signature_public_key,
        remote_server_list_url,
        feedback_encryption_public_key,
        feedback_upload_server,          # unused by Android
        feedback_upload_path,            # unused by Android
        feedback_upload_server_headers,  # unused by Android
        info_link_url,
        upgrade_signature_public_key,
        upgrade_url,
        get_new_version_url,
        get_new_version_email,
        version,
        propagator_managed_upgrades,
        test=False):

    try:
        # Backup/restore original files minimize chance of checking values into source control
        backup = psi_utils.TemporaryBackup([BANNER_FILENAME, ANDROID_MANIFEST_FILENAME])

        # Copy sponsor banner image file from Data to Client source tree
        if banner:
            with open(BANNER_FILENAME, 'wb') as banner_file:
                banner_file.write(banner)

        # Overwrite version in Android manifest file
        write_android_manifest_version(version)

        # overwrite embedded values source file
        write_embedded_values(
            propagation_channel_id,
            sponsor_id,
            version,
            encoded_server_list,
            remote_server_list_signature_public_key,
            feedback_encryption_public_key,
            remote_server_list_url,
            info_link_url,
            upgrade_signature_public_key,
            upgrade_url,
            get_new_version_url,
            get_new_version_email,
            propagator_managed_upgrades,
            ignore_system_server_list=test)

        # copy feedback.html
        shutil.copy(FEEDBACK_HTML_PATH, PSIPHON_ASSETS)

        # build
        build_apk()

        if test:
            return ZIPALIGNED_APK_FILENAME

        # rename and copy executable to Builds folder
        # e.g., Builds/psiphon-3A885577DD84EF13-8BB28C1A8E8A9ED9.exe
        if not os.path.exists(BUILDS_ROOT):
            os.makedirs(BUILDS_ROOT)
        build_destination_path = os.path.join(
                                    BUILDS_ROOT,
                                    APK_FILENAME_TEMPLATE % (propagation_channel_id,
                                                             sponsor_id))
        shutil.copyfile(ZIPALIGNED_APK_FILENAME, build_destination_path)

        print 'Build: SUCCESS'

        return build_destination_path

    except:
        print 'Build: FAILURE'
        raise

    finally:
        backup.restore_all()


def build_library(
        propagation_channel_id,
        sponsor_id,
        encoded_server_list,
        remote_server_list_signature_public_key,
        feedback_encryption_public_key,
        remote_server_list_url,
        info_link_url,
        version):

    try:
        # overwrite embedded values source file
        write_embedded_values(
            propagation_channel_id,
            sponsor_id,
            version,
            encoded_server_list,
            remote_server_list_signature_public_key,
            feedback_encryption_public_key,
            remote_server_list_url,
            info_link_url)

        # TODO: clean the PSIPHON_LIB_SOURCE_ROOT directory of files that are not from source control

        # create the jar
        os.system('jar -cf %s -C %s .' % (LIB_FILENAME, PSIPHON_LIB_SOURCE_ROOT))

        # rename and copy the jar file to Builds folder
        if not os.path.exists(LIBS_ROOT):
            os.makedirs(LIBS_ROOT)
        build_destination_path = os.path.join(
                                    LIBS_ROOT,
                                    LIB_FILENAME_TEMPLATE % (propagation_channel_id,
                                                             sponsor_id))
        shutil.copyfile(LIB_FILENAME, build_destination_path)

        print 'Build: SUCCESS'

        return build_destination_path

    except:
        print 'Build: FAILURE'
        raise

