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

import sys
import datetime
from unittest.mock import Mock

from libcloud.test import MockHttp, unittest
from libcloud.utils.py3 import httplib, assertRaisesRegex
from libcloud.test.secrets import OPENSTACK_PARAMS
from libcloud.common.openstack import OpenStackBaseConnection
from libcloud.test.file_fixtures import ComputeFileFixtures
from libcloud.common.openstack_identity import (
    AUTH_TOKEN_EXPIRES_GRACE_SECONDS,
    OpenStackIdentityUser,
    OpenStackServiceCatalog,
    OpenStackIdentity_2_0_Connection,
    OpenStackIdentity_3_0_Connection,
    OpenStackIdentity_2_0_Connection_VOMS,
    OpenStackIdentity_3_0_Connection_AppCred,
    OpenStackIdentity_3_0_Connection_OIDC_access_token,
    get_class_for_auth_version,
)
from libcloud.compute.drivers.openstack import OpenStack_1_0_NodeDriver
from libcloud.test.compute.test_openstack import (
    OpenStackMockHttp,
    OpenStack_2_0_MockHttp,
    OpenStackMockAuthCache,
)

try:
    import simplejson as json
except ImportError:
    import json


TOMORROW = datetime.datetime.today() + datetime.timedelta(1)
YESTERDAY = datetime.datetime.today() - datetime.timedelta(1)


class OpenStackIdentityConnectionTestCase(unittest.TestCase):
    def setUp(self):
        OpenStackBaseConnection.auth_url = None
        OpenStackBaseConnection.conn_class = OpenStackMockHttp
        OpenStack_2_0_MockHttp.type = None
        OpenStackIdentity_3_0_MockHttp.type = None

    def test_auth_url_is_correctly_assembled(self):
        tuples = [
            ("1.0", OpenStackMockHttp, {}),
            ("1.1", OpenStackMockHttp, {}),
            ("2.0", OpenStack_2_0_MockHttp, {}),
            ("2.0_apikey", OpenStack_2_0_MockHttp, {}),
            ("2.0_password", OpenStack_2_0_MockHttp, {}),
            (
                "3.x_password",
                OpenStackIdentity_3_0_MockHttp,
                {"tenant_name": "tenant-name"},
            ),
            ("3.x_appcred", OpenStackIdentity_3_0_MockHttp, {}),
            (
                "3.x_oidc_access_token",
                OpenStackIdentity_3_0_MockHttp,
                {"tenant_name": "tenant-name"},
            ),
        ]

        auth_urls = [
            ("https://auth.api.example.com", ""),
            ("https://auth.api.example.com/", "/"),
            ("https://auth.api.example.com/foo/bar", "/foo/bar"),
            ("https://auth.api.example.com/foo/bar/", "/foo/bar/"),
        ]

        actions = {
            "1.0": "{url_path}/v1.0",
            "1.1": "{url_path}/v1.1/auth",
            "2.0": "{url_path}/v2.0/tokens",
            "2.0_apikey": "{url_path}/v2.0/tokens",
            "2.0_password": "{url_path}/v2.0/tokens",
            "3.x_password": "{url_path}/v3/auth/tokens",
            "3.x_appcred": "{url_path}/v3/auth/tokens",
            "3.x_oidc_access_token": "{url_path}/v3/OS-FEDERATION/identity_providers/user_name/protocols/tenant-name/auth",
        }

        user_id = OPENSTACK_PARAMS[0]
        key = OPENSTACK_PARAMS[1]

        for auth_version, mock_http_class, kwargs in tuples:
            for url, url_path in auth_urls:
                connection = self._get_mock_connection(
                    mock_http_class=mock_http_class, auth_url=url
                )

                auth_url = connection.auth_url
                cls = get_class_for_auth_version(auth_version=auth_version)
                osa = cls(
                    auth_url=auth_url,
                    user_id=user_id,
                    key=key,
                    parent_conn=connection,
                    **kwargs,
                )

                try:
                    osa = osa.authenticate()
                except Exception:
                    pass

                expected_path = actions[auth_version].format(url_path=url_path).replace("//", "/")

                self.assertEqual(
                    osa.action,
                    expected_path,
                )

    def test_basic_authentication(self):
        tuples = [
            ("1.0", OpenStackMockHttp, {}),
            ("1.1", OpenStackMockHttp, {}),
            ("2.0", OpenStack_2_0_MockHttp, {}),
            ("2.0_apikey", OpenStack_2_0_MockHttp, {}),
            ("2.0_password", OpenStack_2_0_MockHttp, {}),
            (
                "3.x_password",
                OpenStackIdentity_3_0_MockHttp,
                {
                    "user_id": "test_user_id",
                    "key": "test_key",
                    "token_scope": "project",
                    "tenant_name": "test_tenant",
                    "tenant_domain_id": "test_tenant_domain_id",
                    "domain_name": "test_domain",
                },
            ),
            (
                "3.x_appcred",
                OpenStackIdentity_3_0_MockHttp,
                {"user_id": "appcred_id", "key": "appcred_secret"},
            ),
            (
                "3.x_oidc_access_token",
                OpenStackIdentity_3_0_MockHttp,
                {
                    "user_id": "test_user_id",
                    "key": "test_key",
                    "token_scope": "domain",
                    "tenant_name": "test_tenant",
                    "tenant_domain_id": "test_tenant_domain_id",
                    "domain_name": "test_domain",
                },
            ),
        ]

        user_id = OPENSTACK_PARAMS[0]
        key = OPENSTACK_PARAMS[1]

        for auth_version, mock_http_class, kwargs in tuples:
            connection = self._get_mock_connection(mock_http_class=mock_http_class)
            auth_url = connection.auth_url

            if not kwargs:
                kwargs["user_id"] = user_id
                kwargs["key"] = key

            cls = get_class_for_auth_version(auth_version=auth_version)
            osa = cls(auth_url=auth_url, parent_conn=connection, **kwargs)

            self.assertEqual(osa.urls, {})
            self.assertIsNone(osa.auth_token)
            self.assertIsNone(osa.auth_user_info)
            osa = osa.authenticate()

            self.assertTrue(len(osa.urls) >= 1)
            self.assertTrue(osa.auth_token is not None)

            if auth_version in [
                "1.1",
                "2.0",
                "2.0_apikey",
                "2.0_password",
                "3.x_password",
                "3.x_appcred",
                "3.x_oidc_access_token",
            ]:
                self.assertTrue(osa.auth_token_expires is not None)

            if auth_version in [
                "2.0",
                "2.0_apikey",
                "2.0_password",
                "3.x_password",
                "3.x_appcred",
                "3.x_oidc_access_token",
            ]:
                self.assertTrue(osa.auth_user_info is not None)

    def test_token_expiration_and_force_reauthentication(self):
        user_id = OPENSTACK_PARAMS[0]
        key = OPENSTACK_PARAMS[1]

        connection = self._get_mock_connection(OpenStack_2_0_MockHttp)
        auth_url = connection.auth_url

        osa = OpenStackIdentity_2_0_Connection(
            auth_url=auth_url, user_id=user_id, key=key, parent_conn=connection
        )

        mocked_auth_method = Mock(wraps=osa._authenticate_2_0_with_body)
        osa._authenticate_2_0_with_body = mocked_auth_method

        # Force re-auth, expired token
        osa.auth_token = None
        osa.auth_token_expires = YESTERDAY
        count = 5

        for i in range(0, count):
            osa.authenticate(force=True)

        self.assertEqual(mocked_auth_method.call_count, count)

        # No force reauth, expired token
        osa.auth_token = None
        osa.auth_token_expires = YESTERDAY

        mocked_auth_method.call_count = 0
        self.assertEqual(mocked_auth_method.call_count, 0)

        for i in range(0, count):
            osa.authenticate(force=False)

        self.assertEqual(mocked_auth_method.call_count, 1)

        # No force reauth, valid / non-expired token
        osa.auth_token = None

        mocked_auth_method.call_count = 0
        self.assertEqual(mocked_auth_method.call_count, 0)

        for i in range(0, count):
            osa.authenticate(force=False)

            if i == 0:
                osa.auth_token_expires = TOMORROW

        self.assertEqual(mocked_auth_method.call_count, 1)

        # No force reauth, valid / non-expired token which is about to expire in
        # less than AUTH_TOKEN_EXPIRES_GRACE_SECONDS
        soon = datetime.datetime.utcnow() + datetime.timedelta(
            seconds=AUTH_TOKEN_EXPIRES_GRACE_SECONDS - 1
        )
        osa.auth_token = None

        mocked_auth_method.call_count = 0
        self.assertEqual(mocked_auth_method.call_count, 0)

        for i in range(0, count):
            if i == 0:
                osa.auth_token_expires = soon

            osa.authenticate(force=False)

        self.assertEqual(mocked_auth_method.call_count, 1)

    def test_authentication_cache(self):
        tuples = [
            # 1.0 does not provide token expiration, so it always
            # re-authenticates and never uses the cache.
            # ('1.0', OpenStackMockHttp, {}),
            ("1.1", OpenStackMockHttp, {}),
            ("2.0", OpenStack_2_0_MockHttp, {}),
            ("2.0_apikey", OpenStack_2_0_MockHttp, {}),
            ("2.0_password", OpenStack_2_0_MockHttp, {}),
            (
                "3.x_password",
                OpenStackIdentity_3_0_MockHttp,
                {
                    "user_id": "test_user_id",
                    "key": "test_key",
                    "token_scope": "project",
                    "tenant_name": "test_tenant",
                    "tenant_domain_id": "test_tenant_domain_id",
                    "domain_name": "test_domain",
                },
            ),
            (
                "3.x_oidc_access_token",
                OpenStackIdentity_3_0_MockHttp,
                {
                    "user_id": "test_user_id",
                    "key": "test_key",
                    "token_scope": "domain",
                    "tenant_name": "test_tenant",
                    "tenant_domain_id": "test_tenant_domain_id",
                    "domain_name": "test_domain",
                },
            ),
        ]

        user_id = OPENSTACK_PARAMS[0]
        key = OPENSTACK_PARAMS[1]

        for auth_version, mock_http_class, kwargs in tuples:
            mock_http_class.type = None
            connection = self._get_mock_connection(mock_http_class=mock_http_class)
            auth_url = connection.auth_url

            if not kwargs:
                kwargs["user_id"] = user_id
                kwargs["key"] = key

            auth_cache = OpenStackMockAuthCache()
            self.assertEqual(len(auth_cache), 0)
            kwargs["auth_cache"] = auth_cache

            cls = get_class_for_auth_version(auth_version=auth_version)
            osa = cls(auth_url=auth_url, parent_conn=connection, **kwargs)
            osa = osa.authenticate()

            # Token is cached
            self.assertEqual(len(auth_cache), 1)

            # New client, token from cache is re-used
            osa = cls(auth_url=auth_url, parent_conn=connection, **kwargs)
            osa.request = Mock(wraps=osa.request)
            osa = osa.authenticate()

            # No auth API call
            if auth_version in ("1.1", "2.0", "2.0_apikey", "2.0_password"):
                self.assertEqual(osa.request.call_count, 0)
            elif auth_version in ("3.x_password", "3.x_oidc_access_token"):
                # v3 only caches token and expiration; service catalog URLs
                # and the rest of the auth context are fetched from Keystone
                osa.request.assert_called_once_with(
                    action="/v3/auth/tokens",
                    params=None,
                    data=None,
                    headers={
                        "X-Subject-Token": "00000000000000000000000000000000",
                        "X-Auth-Token": "00000000000000000000000000000000",
                    },
                    method="GET",
                    raw=False,
                )

            # Cache size unchanged
            self.assertEqual(len(auth_cache), 1)

            # Authenticates if cached token expired
            cache_key = list(auth_cache.store.keys())[0]
            auth_context = auth_cache.get(cache_key)
            auth_context.expiration = YESTERDAY
            auth_cache.put(cache_key, auth_context)

            osa = cls(auth_url=auth_url, parent_conn=connection, **kwargs)
            osa.request = Mock(wraps=osa.request)
            osa._get_unscoped_token_from_oidc_token = Mock(return_value="000")
            OpenStackIdentity_3_0_MockHttp.type = "GET_UNAUTHORIZED_POST_OK"
            osa = osa.authenticate()

            if auth_version in ("1.1", "2.0", "2.0_apikey", "2.0_password"):
                self.assertEqual(osa.request.call_count, 1)
                self.assertTrue(osa.request.call_args[1]["method"], "POST")
            elif auth_version in ("3.x_password", "3.x_oidc_access_token"):
                self.assertTrue(osa.request.call_args[0][0], "/v3/auth/tokens")
                self.assertTrue(osa.request.call_args[1]["method"], "POST")

            # Token evicted from cache if 401 received on another call
            if hasattr(osa, "list_projects"):
                mock_http_class.type = None
                auth_cache.reset()

                osa = cls(auth_url=auth_url, parent_conn=connection, **kwargs)
                osa.request = Mock(wraps=osa.request)
                osa = osa.authenticate()
                self.assertEqual(len(auth_cache), 1)
                mock_http_class.type = "UNAUTHORIZED"
                try:
                    osa.list_projects()
                except:  # These methods don't handle 401s
                    pass
                self.assertEqual(len(auth_cache), 0)

    def _get_mock_connection(self, mock_http_class, auth_url=None):
        OpenStackBaseConnection.conn_class = mock_http_class

        if auth_url is None:
            auth_url = "https://auth.api.example.com"

        OpenStackBaseConnection.auth_url = auth_url
        connection = OpenStackBaseConnection(*OPENSTACK_PARAMS)

        connection._ex_force_base_url = "https://www.foo.com"
        connection.driver = OpenStack_1_0_NodeDriver(*OPENSTACK_PARAMS)

        return connection


class OpenStackIdentity_2_0_ConnectionTests(unittest.TestCase):
    def setUp(self):
        mock_cls = OpenStackIdentity_2_0_MockHttp
        mock_cls.type = None
        OpenStackIdentity_2_0_Connection.conn_class = mock_cls

        self.auth_instance = OpenStackIdentity_2_0_Connection(
            auth_url="http://none",
            user_id="test",
            key="test",
            tenant_name="test",
            proxy_url="http://proxy:8080",
            timeout=10,
        )
        self.auth_instance.auth_token = "mock"
        self.assertEqual(self.auth_instance.proxy_url, "http://proxy:8080")

    def test_list_projects(self):
        result = self.auth_instance.list_projects()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "a")
        self.assertEqual(result[0].name, "test")
        self.assertEqual(result[0].description, "test project")
        self.assertTrue(result[0].enabled)


class OpenStackIdentity_3_0_ConnectionTests(unittest.TestCase):
    def setUp(self):
        mock_cls = OpenStackIdentity_3_0_MockHttp
        mock_cls.type = None
        OpenStackIdentity_3_0_Connection.conn_class = mock_cls

        self.auth_instance = OpenStackIdentity_3_0_Connection(
            auth_url="http://none",
            user_id="test",
            key="test",
            tenant_name="test",
            proxy_url="http://proxy:8080",
            timeout=10,
        )
        self.auth_instance.auth_token = "mock"
        self.assertEqual(self.auth_instance.proxy_url, "http://proxy:8080")

    def test_token_scope_argument(self):
        # Invalid token_scope value
        expected_msg = 'Invalid value for "token_scope" argument: foo'
        assertRaisesRegex(
            self,
            ValueError,
            expected_msg,
            OpenStackIdentity_3_0_Connection,
            auth_url="http://none",
            user_id="test",
            key="test",
            token_scope="foo",
        )

        # Missing tenant_name
        expected_msg = "Must provide tenant_name and domain_name argument"
        assertRaisesRegex(
            self,
            ValueError,
            expected_msg,
            OpenStackIdentity_3_0_Connection,
            auth_url="http://none",
            user_id="test",
            key="test",
            token_scope="project",
        )

        # Missing domain_name
        expected_msg = "Must provide domain_name argument"
        assertRaisesRegex(
            self,
            ValueError,
            expected_msg,
            OpenStackIdentity_3_0_Connection,
            auth_url="http://none",
            user_id="test",
            key="test",
            token_scope="domain",
            domain_name=None,
        )

        # Scope to project all ok
        OpenStackIdentity_3_0_Connection(
            auth_url="http://none",
            user_id="test",
            key="test",
            token_scope="project",
            tenant_name="test",
            domain_name="Default",
        )
        # Scope to domain
        OpenStackIdentity_3_0_Connection(
            auth_url="http://none",
            user_id="test",
            key="test",
            token_scope="domain",
            tenant_name=None,
            domain_name="Default",
        )

    def test_authenticate(self):
        auth = OpenStackIdentity_3_0_Connection(
            auth_url="http://none",
            user_id="test_user_id",
            key="test_key",
            token_scope="project",
            tenant_name="test_tenant",
            tenant_domain_id="test_tenant_domain_id",
            domain_name="test_domain",
            proxy_url="http://proxy:8080",
            timeout=10,
        )
        auth.authenticate()
        self.assertEqual(auth.proxy_url, "http://proxy:8080")

    def test_list_supported_versions(self):
        OpenStackIdentity_3_0_MockHttp.type = "v3"

        versions = self.auth_instance.list_supported_versions()
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].version, "v2.0")
        self.assertEqual(versions[0].url, "http://192.168.18.100:5000/v2.0/")
        self.assertEqual(versions[1].version, "v3.0")
        self.assertEqual(versions[1].url, "http://192.168.18.100:5000/v3/")

    def test_list_domains(self):
        domains = self.auth_instance.list_domains()
        self.assertEqual(len(domains), 1)
        self.assertEqual(domains[0].id, "default")
        self.assertEqual(domains[0].name, "Default")
        self.assertTrue(domains[0].enabled)

    def test_list_projects(self):
        projects = self.auth_instance.list_projects()
        self.assertEqual(len(projects), 4)
        self.assertEqual(projects[0].id, "a")
        self.assertEqual(projects[0].domain_id, "default")
        self.assertTrue(projects[0].enabled)
        self.assertEqual(projects[0].description, "Test project")

    def test_list_users(self):
        users = self.auth_instance.list_users()
        self.assertEqual(len(users), 12)
        self.assertEqual(users[0].id, "a")
        self.assertEqual(users[0].domain_id, "default")
        self.assertEqual(users[0].enabled, True)
        self.assertEqual(users[0].email, "openstack-test@localhost")

    def test_list_roles(self):
        roles = self.auth_instance.list_roles()
        self.assertEqual(len(roles), 2)
        self.assertEqual(roles[1].id, "b")
        self.assertEqual(roles[1].name, "admin")

    def test_list_user_projects(self):
        user = self.auth_instance.list_users()[0]
        projects = self.auth_instance.list_user_projects(user=user)
        self.assertEqual(len(projects), 0)

    def test_list_user_domain_roles(self):
        user = self.auth_instance.list_users()[0]
        domain = self.auth_instance.list_domains()[0]
        roles = self.auth_instance.list_user_domain_roles(domain=domain, user=user)
        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].name, "admin")

    def test_get_domain(self):
        domain = self.auth_instance.get_domain(domain_id="default")
        self.assertEqual(domain.name, "Default")

    def test_get_user(self):
        user = self.auth_instance.get_user(user_id="a")
        self.assertEqual(user.id, "a")
        self.assertEqual(user.domain_id, "default")
        self.assertEqual(user.enabled, True)
        self.assertEqual(user.email, "openstack-test@localhost")

    def test_get_user_without_email(self):
        user = self.auth_instance.get_user(user_id="b")
        self.assertEqual(user.id, "b")
        self.assertEqual(user.name, "userwithoutemail")
        self.assertIsNone(user.email)

    def test_get_user_without_enabled(self):
        user = self.auth_instance.get_user(user_id="c")
        self.assertEqual(user.id, "c")
        self.assertEqual(user.name, "userwithoutenabled")
        self.assertIsNone(user.enabled)

    def test_create_user(self):
        user = self.auth_instance.create_user(
            email="test2@localhost", password="test1", name="test2", domain_id="default"
        )

        self.assertEqual(user.id, "c")
        self.assertEqual(user.name, "test2")

    def test_enable_user(self):
        user = self.auth_instance.list_users()[0]
        result = self.auth_instance.enable_user(user=user)
        self.assertTrue(isinstance(result, OpenStackIdentityUser))

    def test_disable_user(self):
        user = self.auth_instance.list_users()[0]
        result = self.auth_instance.disable_user(user=user)
        self.assertTrue(isinstance(result, OpenStackIdentityUser))

    def test_grant_domain_role_to_user(self):
        domain = self.auth_instance.list_domains()[0]
        role = self.auth_instance.list_roles()[0]
        user = self.auth_instance.list_users()[0]

        result = self.auth_instance.grant_domain_role_to_user(domain=domain, role=role, user=user)
        self.assertTrue(result)

    def test_revoke_domain_role_from_user(self):
        domain = self.auth_instance.list_domains()[0]
        role = self.auth_instance.list_roles()[0]
        user = self.auth_instance.list_users()[0]

        result = self.auth_instance.revoke_domain_role_from_user(
            domain=domain, role=role, user=user
        )
        self.assertTrue(result)

    def test_grant_project_role_to_user(self):
        project = self.auth_instance.list_projects()[0]
        role = self.auth_instance.list_roles()[0]
        user = self.auth_instance.list_users()[0]

        result = self.auth_instance.grant_project_role_to_user(
            project=project, role=role, user=user
        )
        self.assertTrue(result)

    def test_revoke_project_role_from_user(self):
        project = self.auth_instance.list_projects()[0]
        role = self.auth_instance.list_roles()[0]
        user = self.auth_instance.list_users()[0]

        result = self.auth_instance.revoke_project_role_from_user(
            project=project, role=role, user=user
        )
        self.assertTrue(result)


class OpenStackIdentity_3_0_Connection_AppCredTests(unittest.TestCase):
    def setUp(self):
        mock_cls = OpenStackIdentity_3_0_AppCred_MockHttp
        mock_cls.type = None
        OpenStackIdentity_3_0_Connection_AppCred.conn_class = mock_cls

        self.auth_instance = OpenStackIdentity_3_0_Connection_AppCred(
            auth_url="http://none",
            user_id="appcred_id",
            key="appcred_secret",
            proxy_url="http://proxy:8080",
            timeout=10,
        )
        self.auth_instance.auth_token = "mock"

    def test_authenticate(self):
        auth = OpenStackIdentity_3_0_Connection_AppCred(
            auth_url="http://none",
            user_id="appcred_id",
            key="appcred_secret",
            proxy_url="http://proxy:8080",
            timeout=10,
        )
        auth.authenticate()


class OpenStackIdentity_3_0_Connection_OIDC_access_token_federation_projectsTests(
    unittest.TestCase
):
    def setUp(self):
        mock_cls = OpenStackIdentity_3_0_federation_projects_MockHttp
        mock_cls.type = None
        OpenStackIdentity_3_0_Connection_OIDC_access_token.conn_class = mock_cls

        self.auth_instance = OpenStackIdentity_3_0_Connection_OIDC_access_token(
            auth_url="http://none",
            user_id="idp",
            key="token",
            tenant_name="oidc",
            proxy_url="http://proxy:8080",
            timeout=10,
        )
        self.auth_instance.auth_token = "mock"

    def test_authenticate(self):
        auth = OpenStackIdentity_3_0_Connection_OIDC_access_token(
            auth_url="http://none",
            user_id="idp",
            key="token",
            token_scope="project",
            tenant_name="oidc",
            proxy_url="http://proxy:8080",
            timeout=10,
        )
        auth.authenticate()


class OpenStackIdentity_3_0_Connection_OIDC_access_tokenTests(unittest.TestCase):
    def setUp(self):
        mock_cls = OpenStackIdentity_3_0_MockHttp
        mock_cls.type = None
        OpenStackIdentity_3_0_Connection_OIDC_access_token.conn_class = mock_cls

        self.auth_instance = OpenStackIdentity_3_0_Connection_OIDC_access_token(
            auth_url="http://none",
            user_id="idp",
            key="token",
            tenant_name="oidc",
            domain_name="project_name2",
        )
        self.auth_instance.auth_token = "mock"

    def test_authenticate(self):
        auth = OpenStackIdentity_3_0_Connection_OIDC_access_token(
            auth_url="http://none",
            user_id="idp",
            key="token",
            token_scope="project",
            tenant_name="oidc",
            domain_name="project_name2",
        )
        auth.authenticate()


class OpenStackIdentity_3_0_Connection_OIDC_access_token_project_idTests(unittest.TestCase):
    def setUp(self):
        mock_cls = OpenStackIdentity_3_0_MockHttp
        mock_cls.type = None
        OpenStackIdentity_3_0_Connection_OIDC_access_token.conn_class = mock_cls

        self.auth_instance = OpenStackIdentity_3_0_Connection_OIDC_access_token(
            auth_url="http://none",
            user_id="idp",
            key="token",
            tenant_name="oidc",
            domain_name="project_id2",
        )
        self.auth_instance.auth_token = "mock"

    def test_authenticate_valid_project_id(self):
        auth = OpenStackIdentity_3_0_Connection_OIDC_access_token(
            auth_url="http://none",
            user_id="idp",
            key="token",
            token_scope="project",
            tenant_name="oidc",
            domain_name="project_id2",
        )
        auth.authenticate()

    def test_authenticate_invalid_project_id(self):
        auth = OpenStackIdentity_3_0_Connection_OIDC_access_token(
            auth_url="http://none",
            user_id="idp",
            key="token",
            token_scope="project",
            tenant_name="oidc",
            domain_name="project_id100",
        )

        expected_msg = "Project project_id100 not found"
        self.assertRaisesRegex(ValueError, expected_msg, auth.authenticate)


class OpenStackIdentity_2_0_Connection_VOMSTests(unittest.TestCase):
    def setUp(self):
        mock_cls = OpenStackIdentity_2_0_Connection_VOMSMockHttp
        mock_cls.type = None
        OpenStackIdentity_2_0_Connection_VOMS.conn_class = mock_cls

        self.auth_instance = OpenStackIdentity_2_0_Connection_VOMS(
            auth_url="http://none", user_id=None, key="/tmp/proxy.pem", tenant_name="VO"
        )
        self.auth_instance.auth_token = "mock"

    def test_authenticate(self):
        auth = OpenStackIdentity_2_0_Connection_VOMS(
            auth_url="http://none",
            user_id=None,
            key="/tmp/proxy.pem",
            token_scope="test",
            tenant_name="VO",
        )
        auth.authenticate()


class OpenStackServiceCatalogTestCase(unittest.TestCase):
    fixtures = ComputeFileFixtures("openstack")

    def test_parsing_auth_v1_1(self):
        data = self.fixtures.load("_v1_1__auth.json")
        data = json.loads(data)
        service_catalog = data["auth"]["serviceCatalog"]

        catalog = OpenStackServiceCatalog(service_catalog=service_catalog, auth_version="1.0")
        entries = catalog.get_entries()
        self.assertEqual(len(entries), 3)

        entry = [e for e in entries if e.service_type == "cloudFilesCDN"][0]
        self.assertEqual(entry.service_type, "cloudFilesCDN")
        self.assertIsNone(entry.service_name)
        self.assertEqual(len(entry.endpoints), 2)
        self.assertEqual(entry.endpoints[0].region, "ORD")
        self.assertEqual(entry.endpoints[0].url, "https://cdn2.clouddrive.com/v1/MossoCloudFS")
        self.assertEqual(entry.endpoints[0].endpoint_type, "external")
        self.assertEqual(entry.endpoints[1].region, "LON")
        self.assertEqual(entry.endpoints[1].endpoint_type, "external")

    def test_parsing_auth_v2(self):
        data = self.fixtures.load("_v2_0__auth.json")
        data = json.loads(data)
        service_catalog = data["access"]["serviceCatalog"]

        catalog = OpenStackServiceCatalog(service_catalog=service_catalog, auth_version="2.0")
        entries = catalog.get_entries()
        self.assertEqual(len(entries), 10)

        entry = [e for e in entries if e.service_name == "cloudServers"][0]
        self.assertEqual(entry.service_type, "compute")
        self.assertEqual(entry.service_name, "cloudServers")
        self.assertEqual(len(entry.endpoints), 1)
        self.assertIsNone(entry.endpoints[0].region)
        self.assertEqual(entry.endpoints[0].url, "https://servers.api.rackspacecloud.com/v1.0/1337")
        self.assertEqual(entry.endpoints[0].endpoint_type, "external")

    def test_parsing_auth_v3(self):
        data = self.fixtures.load("_v3__auth.json")
        data = json.loads(data)
        service_catalog = data["token"]["catalog"]

        catalog = OpenStackServiceCatalog(service_catalog=service_catalog, auth_version="3.x")
        entries = catalog.get_entries()
        self.assertEqual(len(entries), 6)
        entry = [e for e in entries if e.service_type == "volume"][0]
        self.assertEqual(entry.service_type, "volume")
        self.assertIsNone(entry.service_name)
        self.assertEqual(len(entry.endpoints), 3)
        self.assertEqual(entry.endpoints[0].region, "regionOne")
        self.assertEqual(entry.endpoints[0].endpoint_type, "external")
        self.assertEqual(entry.endpoints[1].region, "regionOne")
        self.assertEqual(entry.endpoints[1].endpoint_type, "admin")
        self.assertEqual(entry.endpoints[2].region, "regionOne")
        self.assertEqual(entry.endpoints[2].endpoint_type, "internal")

    def test_get_public_urls(self):
        data = self.fixtures.load("_v2_0__auth.json")
        data = json.loads(data)
        service_catalog = data["access"]["serviceCatalog"]

        catalog = OpenStackServiceCatalog(service_catalog=service_catalog, auth_version="2.0")

        public_urls = catalog.get_public_urls(service_type="object-store")
        expected_urls = [
            "https://storage101.lon1.clouddrive.com/v1/MossoCloudFS_11111-111111111-1111111111-1111111",
            "https://storage101.ord1.clouddrive.com/v1/MossoCloudFS_11111-111111111-1111111111-1111111",
        ]
        self.assertEqual(public_urls, expected_urls)

    def test_get_regions(self):
        data = self.fixtures.load("_v2_0__auth.json")
        data = json.loads(data)
        service_catalog = data["access"]["serviceCatalog"]

        catalog = OpenStackServiceCatalog(service_catalog=service_catalog, auth_version="2.0")

        regions = catalog.get_regions(service_type="object-store")
        self.assertEqual(regions, ["LON", "ORD"])

        regions = catalog.get_regions(service_type="invalid")
        self.assertEqual(regions, [])

    def test_get_service_types(self):
        data = self.fixtures.load("_v2_0__auth.json")
        data = json.loads(data)
        service_catalog = data["access"]["serviceCatalog"]

        catalog = OpenStackServiceCatalog(service_catalog=service_catalog, auth_version="2.0")
        service_types = catalog.get_service_types()
        self.assertEqual(
            service_types,
            [
                "compute",
                "image",
                "network",
                "object-store",
                "rax:object-cdn",
                "volumev2",
                "volumev3",
            ],
        )

        service_types = catalog.get_service_types(region="ORD")
        self.assertEqual(service_types, ["rax:object-cdn"])

    def test_get_service_names(self):
        data = self.fixtures.load("_v2_0__auth.json")
        data = json.loads(data)
        service_catalog = data["access"]["serviceCatalog"]

        catalog = OpenStackServiceCatalog(service_catalog=service_catalog, auth_version="2.0")

        service_names = catalog.get_service_names()
        self.assertEqual(
            service_names,
            [
                "cinderv2",
                "cinderv3",
                "cloudFiles",
                "cloudFilesCDN",
                "cloudServers",
                "cloudServersOpenStack",
                "cloudServersPreprod",
                "glance",
                "neutron",
                "nova",
            ],
        )

        service_names = catalog.get_service_names(service_type="compute")
        self.assertEqual(
            service_names,
            ["cloudServers", "cloudServersOpenStack", "cloudServersPreprod", "nova"],
        )


class OpenStackIdentity_2_0_MockHttp(MockHttp):
    fixtures = ComputeFileFixtures("openstack_identity/v2")
    json_content_headers = {"content-type": "application/json; charset=UTF-8"}

    def _v2_0_tenants(self, method, url, body, headers):
        if method == "GET":
            body = self.fixtures.load("v2_0_tenants.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()


class OpenStackIdentity_3_0_MockHttp(MockHttp):
    fixtures = ComputeFileFixtures("openstack_identity/v3")
    json_content_headers = {"content-type": "application/json; charset=UTF-8"}

    def _v3(self, method, url, body, headers):
        if method == "GET":
            body = self.fixtures.load("v3_versions.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_domains(self, method, url, body, headers):
        if method == "GET":
            body = self.fixtures.load("v3_domains.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_projects(self, method, url, body, headers):
        if method == "GET":
            body = self.fixtures.load("v3_projects.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_projects_UNAUTHORIZED(self, method, url, body, headers):
        if method == "GET":
            body = ComputeFileFixtures("openstack").load("_v3__auth.json")
            return (
                httplib.UNAUTHORIZED,
                body,
                self.json_content_headers,
                httplib.responses[httplib.UNAUTHORIZED],
            )
        raise NotImplementedError()

    def _v3_OS_FEDERATION_identity_providers_test_user_id_protocols_test_tenant_auth(
        self, method, url, body, headers
    ):
        if method == "GET":
            if "Authorization" not in headers:
                return (
                    httplib.UNAUTHORIZED,
                    "",
                    headers,
                    httplib.responses[httplib.OK],
                )

            if headers["Authorization"] == "Bearer test_key":
                response_body = ComputeFileFixtures("openstack").load("_v3__auth.json")
                response_headers = {
                    "Content-Type": "application/json",
                    "x-subject-token": "foo-bar",
                }
                return (
                    httplib.OK,
                    response_body,
                    response_headers,
                    httplib.responses[httplib.OK],
                )

            return (httplib.UNAUTHORIZED, "{}", headers, httplib.responses[httplib.OK])
        raise NotImplementedError()

    def _v3_auth_tokens(self, method, url, body, headers):
        if method == "GET":
            body = json.loads(ComputeFileFixtures("openstack").load("_v3__auth.json"))
            body["token"]["expires_at"] = TOMORROW.isoformat()
            headers = self.json_content_headers.copy()
            headers["x-subject-token"] = "00000000000000000000000000000000"
            return (
                httplib.OK,
                json.dumps(body),
                headers,
                httplib.responses[httplib.OK],
            )
        if method == "POST":
            status = httplib.OK
            data = json.loads(body)
            if "password" in data["auth"]["identity"]:
                if (
                    data["auth"]["identity"]["password"]["user"]["domain"]["name"] != "test_domain"
                    or data["auth"]["scope"]["project"]["domain"]["id"] != "test_tenant_domain_id"
                ):
                    status = httplib.UNAUTHORIZED

            body = ComputeFileFixtures("openstack").load("_v3__auth.json")
            headers = self.json_content_headers.copy()
            headers["x-subject-token"] = "00000000000000000000000000000000"
            return (status, body, headers, httplib.responses[httplib.OK])
        raise NotImplementedError()

    def _v3_auth_tokens_GET_UNAUTHORIZED_POST_OK(self, method, url, body, headers):
        if method == "GET":
            body = ComputeFileFixtures("openstack").load("_v3__auth_unauthorized.json")
            return (
                httplib.UNAUTHORIZED,
                body,
                self.json_content_headers,
                httplib.responses[httplib.UNAUTHORIZED],
            )
        if method == "POST":
            return self._v3_auth_tokens(method, url, body, headers)
        raise NotImplementedError()

    def _v3_users(self, method, url, body, headers):
        if method == "GET":
            # list users
            body = self.fixtures.load("v3_users.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        elif method == "POST":
            # create user
            body = self.fixtures.load("v3_create_user.json")
            return (
                httplib.CREATED,
                body,
                self.json_content_headers,
                httplib.responses[httplib.CREATED],
            )
        raise NotImplementedError()

    def _v3_users_a(self, method, url, body, headers):
        if method == "GET":
            # look up a user
            body = self.fixtures.load("v3_users_a.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        if method == "PATCH":
            # enable / disable user
            body = self.fixtures.load("v3_users_a.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_users_b(self, method, url, body, headers):
        if method == "GET":
            # look up a user
            body = self.fixtures.load("v3_users_b.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_users_c(self, method, url, body, headers):
        if method == "GET":
            # look up a user
            body = self.fixtures.load("v3_users_c.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_roles(self, method, url, body, headers):
        if method == "GET":
            body = self.fixtures.load("v3_roles.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_domains_default_users_a_roles_a(self, method, url, body, headers):
        if method == "PUT":
            # grant domain role
            body = ""
            return (
                httplib.NO_CONTENT,
                body,
                self.json_content_headers,
                httplib.responses[httplib.NO_CONTENT],
            )
        elif method == "DELETE":
            # revoke domain role
            body = ""
            return (
                httplib.NO_CONTENT,
                body,
                self.json_content_headers,
                httplib.responses[httplib.NO_CONTENT],
            )
        raise NotImplementedError()

    def _v3_projects_a_users_a_roles_a(self, method, url, body, headers):
        if method == "PUT":
            # grant project role
            body = ""
            return (
                httplib.NO_CONTENT,
                body,
                self.json_content_headers,
                httplib.responses[httplib.NO_CONTENT],
            )
        elif method == "DELETE":
            # revoke project role
            body = ""
            return (
                httplib.NO_CONTENT,
                body,
                self.json_content_headers,
                httplib.responses[httplib.NO_CONTENT],
            )
        raise NotImplementedError()

    def _v3_domains_default(self, method, url, body, headers):
        if method == "GET":
            # get domain
            body = self.fixtures.load("v3_domains_default.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_users_a_projects(self, method, url, body, headers):
        if method == "GET":
            # get user projects
            body = self.fixtures.load("v3_users_a_projects.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_domains_default_users_a_roles(self, method, url, body, headers):
        if method == "GET":
            # get user domain roles
            body = self.fixtures.load("v3_domains_default_users_a_roles.json")
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_OS_FEDERATION_identity_providers_idp_protocols_oidc_auth(
        self, method, url, body, headers
    ):
        if method == "GET":
            headers = self.json_content_headers.copy()
            headers["x-subject-token"] = "00000000000000000000000000000000"
            return (httplib.OK, body, headers, httplib.responses[httplib.OK])
        raise NotImplementedError()

    def _v3_OS_FEDERATION_projects(self, method, url, body, headers):
        if method == "GET":
            # get user projects
            body = json.dumps(
                {
                    "projects": [
                        {"id": "project_id", "name": "project_name"},
                        {"id": "project_id2", "name": "project_name2"},
                    ]
                }
            )
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_auth_projects(self, method, url, body, headers):
        if method == "GET":
            # get user projects
            body = json.dumps(
                {
                    "projects": [
                        {"id": "project_id", "name": "project_name"},
                        {"id": "project_id2", "name": "project_name2"},
                    ]
                }
            )
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()


class OpenStackIdentity_3_0_AppCred_MockHttp(OpenStackIdentity_3_0_MockHttp):
    def _v3_auth_tokens(self, method, url, body, headers):
        if method == "POST":
            status = httplib.OK
            data = json.loads(body)
            if "application_credential" not in data["auth"]["identity"]["methods"]:
                status = httplib.UNAUTHORIZED
            else:
                appcred = data["auth"]["identity"]["application_credential"]
                if appcred["id"] != "appcred_id" or appcred["secret"] != "appcred_secret":
                    status = httplib.UNAUTHORIZED

            body = ComputeFileFixtures("openstack").load("_v3__auth.json")
            headers = self.json_content_headers.copy()
            headers["x-subject-token"] = "00000000000000000000000000000000"
            return (status, body, headers, httplib.responses[httplib.OK])
        raise NotImplementedError()


class OpenStackIdentity_3_0_federation_projects_MockHttp(OpenStackIdentity_3_0_MockHttp):
    fixtures = ComputeFileFixtures("openstack_identity/v3")
    json_content_headers = {"content-type": "application/json; charset=UTF-8"}

    def _v3_OS_FEDERATION_projects(self, method, url, body, headers):
        if method == "GET":
            # get user projects
            body = json.dumps({"projects": [{"id": "project_id"}]})
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()

    def _v3_auth_projects(self, method, url, body, headers):
        return (
            httplib.INTERNAL_SERVER_ERROR,
            body,
            self.json_content_headers,
            httplib.responses[httplib.INTERNAL_SERVER_ERROR],
        )


class OpenStackIdentity_2_0_Connection_VOMSMockHttp(MockHttp):
    fixtures = ComputeFileFixtures("openstack_identity/v2")
    json_content_headers = {"content-type": "application/json; charset=UTF-8"}

    def _v2_0_tokens(self, method, url, body, headers):
        if method == "POST":
            status = httplib.UNAUTHORIZED
            data = json.loads(body)
            if "voms" in data["auth"] and data["auth"]["voms"] is True:
                status = httplib.OK

            body = ComputeFileFixtures("openstack").load("_v2_0__auth.json")
            headers = self.json_content_headers.copy()
            headers["x-subject-token"] = "00000000000000000000000000000000"
            return (status, body, headers, httplib.responses[httplib.OK])
        raise NotImplementedError()

    def _v2_0_tenants(self, method, url, body, headers):
        if method == "GET":
            # get user projects
            body = json.dumps({"tenant": [{"name": "tenant_name"}]})
            return (
                httplib.OK,
                body,
                self.json_content_headers,
                httplib.responses[httplib.OK],
            )
        raise NotImplementedError()


if __name__ == "__main__":
    sys.exit(unittest.main())
