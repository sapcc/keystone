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

import datetime
import uuid
from unittest import mock

from keystone.common import provider_api
from keystone.tests import unit
from keystone.tests.unit import default_fixtures
from keystone.tests.unit.ksfixtures import database

PROVIDERS = provider_api.ProviderAPIs


class FederatedGroupCacheTest(unit.TestCase):
    """Test federated group membership cache invalidation."""

    def setUp(self):
        # Mock LDAP to avoid environment-specific errors
        ldap_patcher = mock.patch('ldap.initialize')
        self.addCleanup(ldap_patcher.stop)
        ldap_patcher.start()

        # Mock LDAP options that are checked during setup
        with mock.patch('ldap.get_option', return_value=None):
            with mock.patch('ldap.set_option'):
                super(FederatedGroupCacheTest, self).setUp()
        self.useFixture(database.Database())
        self.load_backends()

        # Create domain
        PROVIDERS.resource_api.create_domain(
            default_fixtures.ROOT_DOMAIN['id'], default_fixtures.ROOT_DOMAIN)

        # Create IDP, mapping, and protocol
        self.idp = {
            'id': uuid.uuid4().hex,
            'enabled': True,
            'description': uuid.uuid4().hex
        }
        self.mapping = {
            'id': uuid.uuid4().hex,
        }
        self.protocol = {
            'id': uuid.uuid4().hex,
            'idp_id': self.idp['id'],
            'mapping_id': self.mapping['id']
        }

        PROVIDERS.federation_api.create_idp(self.idp['id'], self.idp)
        PROVIDERS.federation_api.create_mapping(
            self.mapping['id'], self.mapping
        )
        PROVIDERS.federation_api.create_protocol(
            self.idp['id'], self.protocol['id'], self.protocol)

        self.domain_id = (
            PROVIDERS.federation_api.get_idp(self.idp['id'])['domain_id'])

        # Create a federated user
        self.federated_user = {
            'idp_id': self.idp['id'],
            'protocol_id': self.protocol['id'],
            'unique_id': uuid.uuid4().hex,
            'display_name': uuid.uuid4().hex
        }
        self.user = PROVIDERS.shadow_users_api.create_federated_user(
            self.domain_id, self.federated_user)

        # Create groups
        self.group1 = unit.new_group_ref(domain_id=self.domain_id)
        self.group1 = PROVIDERS.identity_api.create_group(self.group1)

        self.group2 = unit.new_group_ref(domain_id=self.domain_id)
        self.group2 = PROVIDERS.identity_api.create_group(self.group2)

        # Create a project
        self.project = unit.new_project_ref(domain_id=self.domain_id)
        self.project = PROVIDERS.resource_api.create_project(
            self.project['id'], self.project)

        # Create a role
        self.role = unit.new_role_ref()
        self.role = PROVIDERS.role_api.create_role(
            self.role['id'], self.role)

    def test_add_user_to_group_expires_returns_true_for_new_membership(self):
        """Test that add_user_to_group_expires returns True for new membership."""
        # Add user to group for the first time
        result = PROVIDERS.shadow_users_api.add_user_to_group_expires(
            self.user['id'], self.group1['id'])

        # Should return True indicating a new membership was added
        self.assertTrue(result)

    def test_add_user_to_group_expires_returns_false_for_renewal(self):
        """Test that add_user_to_group_expires returns False when renewing."""
        # Add user to group for the first time
        PROVIDERS.shadow_users_api.add_user_to_group_expires(
            self.user['id'], self.group1['id'])

        # Add the same membership again (simulating renewal)
        result = PROVIDERS.shadow_users_api.add_user_to_group_expires(
            self.user['id'], self.group1['id'])

        # Should return False indicating just a renewal, not a change
        self.assertFalse(result)

    @mock.patch('keystone.notifications.invalidate_token_cache_notification')
    def test_invalidate_user_role_assignments_cache(self, mock_notification):
        """Test the invalidate_user_role_assignments_cache method."""
        # Call the new method
        PROVIDERS.assignment_api.invalidate_user_role_assignments_cache(
            self.user['id'])

        # Verify that token cache invalidation notification was called
        mock_notification.assert_called_once()

        # Verify the notification message contains the user_id
        call_args = mock_notification.call_args[0][0]
        self.assertIn(self.user['id'], call_args)
        self.assertIn('federated group membership changes', call_args)

    def test_shadow_federated_user_invalidates_cache_on_new_membership(self):
        """Test that cache is invalidated when group membership changes."""
        with mock.patch.object(
                PROVIDERS.assignment_api,
                'invalidate_user_role_assignments_cache') as mock_invalidate:

            # Create user dict for shadowing
            user_dict = {
                'id': self.federated_user['unique_id'],
                'name': self.federated_user['display_name'],
                'domain': {'id': self.domain_id}
            }

            # Shadow the user with new group membership
            PROVIDERS.identity_api.shadow_federated_user(
                self.idp['id'],
                self.protocol['id'],
                user_dict,
                group_ids=[self.group1['id']]
            )

            # Verify that cache invalidation was called
            mock_invalidate.assert_called_once_with(self.user['id'])

    def test_shadow_federated_user_does_not_invalidate_on_only_renewal(self):
        """Test that cache is NOT invalidated when just renewing membership.

        Note: This test uses mocking at the add_user_to_group_expires level
        to simulate a pure renewal without any membership changes.
        """
        with mock.patch.object(
                PROVIDERS.shadow_users_api,
                'add_user_to_group_expires',
                return_value=False):  # Simulate renewal only
            with mock.patch.object(
                    PROVIDERS.shadow_users_api,
                    'remove_expired_group_memberships',
                    return_value=False):  # No expired memberships
                with mock.patch.object(
                        PROVIDERS.assignment_api,
                        'invalidate_user_role_assignments_cache') as mock_invalidate:

                    # Create user dict for shadowing
                    user_dict = {
                        'id': self.federated_user['unique_id'],
                        'name': self.federated_user['display_name'],
                        'domain': {'id': self.domain_id}
                    }

                    # Shadow the user with group (simulated as renewal only)
                    PROVIDERS.identity_api.shadow_federated_user(
                        self.idp['id'],
                        self.protocol['id'],
                        user_dict,
                        group_ids=[self.group1['id']]
                    )

                    # Verify that cache invalidation was NOT called
                    mock_invalidate.assert_not_called()

    def test_shadow_federated_user_invalidates_on_additional_group(self):
        """Test that cache is invalidated when adding additional groups."""
        # Add user to first group
        PROVIDERS.shadow_users_api.add_user_to_group_expires(
            self.user['id'], self.group1['id'])

        with mock.patch.object(
                PROVIDERS.assignment_api,
                'invalidate_user_role_assignments_cache') as mock_invalidate:

            # Create user dict for shadowing
            user_dict = {
                'id': self.federated_user['unique_id'],
                'name': self.federated_user['display_name'],
                'domain': {'id': self.domain_id}
            }

            # Shadow the user with both groups (adding a new one)
            PROVIDERS.identity_api.shadow_federated_user(
                self.idp['id'],
                self.protocol['id'],
                user_dict,
                group_ids=[self.group1['id'], self.group2['id']]
            )

            # Verify that cache invalidation was called (because of new group)
            mock_invalidate.assert_called_once_with(self.user['id'])

    def test_cache_invalidation_method_callable(self):
        """Test that the cache invalidation method can be called successfully."""
        # This is a simple test to verify the method exists and is callable
        # The actual cache invalidation logic is tested in other tests
        try:
            PROVIDERS.assignment_api.invalidate_user_role_assignments_cache(
                self.user['id'])
            # If we get here without exception, the test passes
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"Cache invalidation method raised exception: {e}")

    def test_multiple_group_changes_trigger_invalidation(self):
        """Test that multiple membership changes each trigger invalidation."""
        with mock.patch.object(
                PROVIDERS.assignment_api,
                'invalidate_user_role_assignments_cache') as mock_invalidate:

            # Create user dict for shadowing
            user_dict = {
                'id': self.federated_user['unique_id'],
                'name': self.federated_user['display_name'],
                'domain': {'id': self.domain_id}
            }

            # First group addition
            PROVIDERS.identity_api.shadow_federated_user(
                self.idp['id'],
                self.protocol['id'],
                user_dict,
                group_ids=[self.group1['id']]
            )

            # Should have been called once
            self.assertEqual(1, mock_invalidate.call_count)

            # Second group addition (adding another group)
            PROVIDERS.identity_api.shadow_federated_user(
                self.idp['id'],
                self.protocol['id'],
                user_dict,
                group_ids=[self.group1['id'], self.group2['id']]
            )

            # Should have been called twice total
            self.assertEqual(2, mock_invalidate.call_count)

    def test_empty_group_list_does_not_invalidate(self):
        """Test that shadowing with empty group list doesn't invalidate cache."""
        with mock.patch.object(
                PROVIDERS.assignment_api,
                'invalidate_user_role_assignments_cache') as mock_invalidate:

            # Create user dict for shadowing
            user_dict = {
                'id': self.federated_user['unique_id'],
                'name': self.federated_user['display_name'],
                'domain': {'id': self.domain_id}
            }

            # Shadow user with no groups
            PROVIDERS.identity_api.shadow_federated_user(
                self.idp['id'],
                self.protocol['id'],
                user_dict,
                group_ids=[]
            )

            # Cache invalidation should not have been called
            mock_invalidate.assert_not_called()
