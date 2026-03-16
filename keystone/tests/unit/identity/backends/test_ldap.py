# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from unittest import mock

from oslo_config import fixture as config_fixture

from keystone.common import driver_hints
from keystone.identity.backends import ldap
from keystone.tests.unit import core
from keystone.tests.unit.identity.backends import test_base
from keystone.tests.unit.ksfixtures import ldapdb


class TestIdentityDriver(core.BaseTestCase, test_base.IdentityDriverTests):
    allows_name_update = False
    allows_self_service_change_password = False
    expected_is_domain_aware = False
    expected_default_assignment_driver = 'sql'
    expected_is_sql = False
    expected_generates_uuids = False

    def setUp(self):
        super().setUp()

        config_fixture_ = self.useFixture(config_fixture.Config())
        config_fixture_.config(
            group='ldap',
            url='fake://memory',
            user='cn=Admin',
            password='password',
            suffix='cn=example,cn=com',
        )

        self.useFixture(ldapdb.LDAPDatabase())

        self.driver = ldap.Identity()

    def test_delete_user(self):
        self.skip_test_overrides('N/A: LDAP has no write support')

    def test_delete_user_no_user_exc(self):
        self.skip_test_overrides('N/A: LDAP has no write support')

    def test_delete_group(self):
        self.skip_test_overrides('N/A: LDAP has no write support')

    def test_delete_group_doesnt_exist_exc(self):
        self.skip_test_overrides('N/A: LDAP has no write support')

    def test_remove_user_from_group(self):
        self.skip_test_overrides('N/A: LDAP has no write support')

    def test_remove_user_from_group_not_in_group(self):
        self.skip_test_overrides('N/A: LDAP has no write support')

    def test_remove_user_from_group_no_user(self):
        self.skip_test_overrides('N/A: LDAP has no write support')

    def test_remove_user_from_group_no_group(self):
        self.skip_test_overrides('N/A: LDAP has no write support')

    def test_list_users_in_group_uses_batched_queries(self):
        group = self.create_group()
        users = []
        for _ in range(5):
            user = self.create_user()
            self.driver.add_user_to_group(user['id'], group['id'])
            users.append(user)

        # Track calls to user.get_filtered (the old per-user approach)
        original_get_filtered = self.driver.user.get_filtered
        get_filtered_calls = []

        def tracking_get_filtered(user_id):
            get_filtered_calls.append(user_id)
            return original_get_filtered(user_id)

        with mock.patch.object(
            self.driver.user, 'get_filtered', side_effect=tracking_get_filtered
        ):
            result = self.driver.list_users_in_group(
                group['id'], driver_hints.Hints()
            )

        self.assertEqual(5, len(result))
        result_ids = {u['id'] for u in result}
        expected_ids = {u['id'] for u in users}
        self.assertEqual(expected_ids, result_ids)

        # After batching, get_filtered should NOT be called per-user.
        # It should be 0 calls (batch uses get_all instead).
        self.assertEqual(0, len(get_filtered_calls))
