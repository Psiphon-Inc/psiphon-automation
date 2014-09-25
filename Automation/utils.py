#!/usr/bin/python
#
# Copyright (c) 2013, Psiphon Inc.
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

embedded_values = {}


def set_embedded_values(client_version,
                        embedded_server_list,
                        ignore_non_embedded_server_entries,
                        feedback_encryption_public_key,
                        feedback_upload_server,
                        feedback_upload_path,
                        feedback_upload_server_headers,
                        info_link_url,
                        proxied_web_app_http_auth_username,
                        proxied_web_app_http_auth_password,
                        upgrade_url,
                        upgrade_signature_public_key,
                        get_new_version_url,
                        get_new_version_email,
                        faq_url,
                        data_collection_info_url,
                        is_play_store_build,
                        propagation_channel_id,
                        sponsor_id,
                        remote_server_list_url,
                        remote_server_list_signature_public_key,
                        home_tab_url_exclusions):
    global embedded_values
    embedded_values['CLIENT_VERSION'] = client_version
    embedded_values['EMBEDDED_SERVER_LIST'] = embedded_server_list
    embedded_values['IGNORE_NON_EMBEDDED_SERVER_ENTRIES'] = ignore_non_embedded_server_entries
    embedded_values['FEEDBACK_ENCRYPTION_PUBLIC_KEY'] = feedback_encryption_public_key
    embedded_values['FEEDBACK_DIAGNOSTIC_INFO_UPLOAD_SERVER'] = feedback_upload_server
    embedded_values['FEEDBACK_DIAGNOSTIC_INFO_UPLOAD_PATH'] = feedback_upload_path
    embedded_values['FEEDBACK_DIAGNOSTIC_INFO_UPLOAD_SERVER_HEADERS'] = feedback_upload_server_headers
    embedded_values['INFO_LINK_URL'] = info_link_url
    embedded_values['PROXIED_WEB_APP_HTTP_AUTH_USERNAME'] = proxied_web_app_http_auth_username
    embedded_values['PROXIED_WEB_APP_HTTP_AUTH_PASSWORD'] = proxied_web_app_http_auth_password
    embedded_values['UPGRADE_URL'] = upgrade_url
    embedded_values['UPGRADE_SIGNATURE_PUBLIC_KEY'] = upgrade_signature_public_key
    embedded_values['GET_NEW_VERSION_URL'] = get_new_version_url
    embedded_values['GET_NEW_VERSION_EMAIL'] = get_new_version_email
    embedded_values['FAQ_URL'] = faq_url
    embedded_values['DATA_COLLECTION_INFO_URL'] = data_collection_info_url
    embedded_values['IS_PLAY_STORE_BUILD'] = is_play_store_build
    embedded_values['PROPAGATION_CHANNEL_ID'] = propagation_channel_id
    embedded_values['SPONSOR_ID'] = sponsor_id
    embedded_values['REMOTE_SERVER_LIST_URL'] = remote_server_list_url
    embedded_values['REMOTE_SERVER_LIST_SIGNATURE_PUBLIC_KEY'] = remote_server_list_signature_public_key
    embedded_values['HOME_TAB_URL_EXCLUSIONS'] = home_tab_url_exclusions


# This function is to be called by psi_ops_build_android.py, retaining compatibility
# with cog functionality originally written for the PsiphonProxiedWebApp
def get_embedded_value(_, key):
    global embedded_values
    return embedded_values[key]
