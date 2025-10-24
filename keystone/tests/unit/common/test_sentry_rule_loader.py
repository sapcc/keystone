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

import os
import tempfile
import yaml

from keystone.common.sentry_rule_loader import load_rules_from_file
from keystone.common.sentry_rule_loader import RuleValidationError
from keystone.tests import unit


class SentryRuleLoaderTestCase(unit.BaseTestCase):
    """Test suite for Sentry rule loader functionality."""

    def setUp(self):
        """Set up test fixtures."""
        super(SentryRuleLoaderTestCase, self).setUp()
        self.temp_files = []

    def tearDown(self):
        """Clean up temporary files."""
        for temp_file in self.temp_files:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
        super(SentryRuleLoaderTestCase, self).tearDown()

    def _create_temp_config(self, config_data):
        """Create a temporary configuration file with given data."""
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', delete=False
        )
        yaml.dump(config_data, temp_file, default_flow_style=False)
        temp_file.close()
        self.temp_files.append(temp_file.name)
        return temp_file.name

    def test_load_valid_config(self):
        """Test that valid configuration can be loaded without errors."""
        config_data = {
            'rules': [
                {'name': 'test_rule', 'exception_type': 'TestError'}
            ]
        }
        config_file = self._create_temp_config(config_data)

        # Should not raise any exceptions
        rules = load_rules_from_file(config_file)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]['name'], 'test_rule')

    def test_empty_rules_list(self):
        """Test configuration with empty rules list."""
        config_data = {'rules': []}
        config_file = self._create_temp_config(config_data)

        rules = load_rules_from_file(config_file)
        self.assertEqual(len(rules), 0)

    def test_missing_rules_section(self):
        """Test configuration without 'rules' section."""
        config_data = {'other_section': []}
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_nonexistent_file(self):
        """Test loading from non-existent file."""
        config_file = '/nonexistent/path/config.yaml'
        rules = load_rules_from_file(config_file)
        self.assertEqual(len(rules), 0)

    def test_invalid_yaml_format(self):
        """Test handling of malformed YAML."""
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', delete=False
        )
        temp_file.write("invalid: yaml: content: [unclosed")
        temp_file.close()
        self.temp_files.append(temp_file.name)

        self.assertRaises(yaml.YAMLError, load_rules_from_file, temp_file.name)

    def test_rule_not_dictionary(self):
        """Test validation fails when rule is not a dictionary."""
        config_data = {
            'rules': ["not_a_dict"]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rule_missing_name(self):
        """Test validation fails when rule has no 'name' field."""
        config_data = {
            'rules': [{'exception_type': 'TestError'}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rule_name_not_string(self):
        """Test validation fails when rule name is not a string."""
        config_data = {
            'rules': [{'name': 123, 'exception_type': 'TestError'}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rule_name_empty_string(self):
        """Test validation fails when rule name is empty."""
        config_data = {
            'rules': [{'name': '', 'exception_type': 'TestError'}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rule_name_whitespace_only(self):
        """Test validation fails when rule name is only whitespace."""
        config_data = {
            'rules': [{'name': '   ', 'exception_type': 'TestError'}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rule_no_conditions(self):
        """Test validation fails when rule has no filtering conditions."""
        config_data = {
            'rules': [{'name': 'test_rule'}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_exception_type_not_string(self):
        """Test validation fails when exception_type is not a string."""
        config_data = {
            'rules': [{'name': 'test_rule', 'exception_type': 123}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_message_pattern_not_string(self):
        """Test validation fails when message_pattern is not a string."""
        config_data = {
            'rules': [{'name': 'test_rule', 'message_pattern': 123}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_message_pattern_invalid_regex(self):
        """Test validation fails when message_pattern is invalid regex."""
        config_data = {
            'rules': [{'name': 'test_rule', 'message_pattern': '[unclosed'}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_message_contains_not_string(self):
        """Test validation fails when message_contains is not a string."""
        config_data = {
            'rules': [{'name': 'test_rule', 'message_contains': 123}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rate_limit_not_dictionary(self):
        """Test validation fails when rate_limit is not a dictionary."""
        config_data = {
            'rules': [{'name': 'test_rule',
                       'exception_type': 'TestError',
                       'rate_limit': 'not_dict'}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rate_limit_missing_max_occurrences(self):
        """Test validation fails when rate_limit missing max_occurrences."""
        config_data = {
            'rules': [{'name': 'test_rule',
                       'exception_type': 'TestError',
                       'rate_limit': {'time_window': 300}}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(RuleValidationError,
                          load_rules_from_file,
                          config_file)

    def test_rate_limit_missing_time_window(self):
        """Test validation fails when rate_limit missing time_window."""
        config_data = {
            'rules': [{'name': 'test_rule',
                       'exception_type': 'TestError',
                       'rate_limit': {'max_occurrences': 5}}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rate_limit_max_occurrences_not_int(self):
        """Test validation fails when max_occurrences is not an integer."""
        config_data = {
            'rules': [{'name': 'test_rule', 'exception_type': 'TestError',
                      'rate_limit': {
                          'max_occurrences': 'five',
                          'time_window': 300}}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rate_limit_max_occurrences_zero(self):
        """Test validation fails when max_occurrences is zero."""
        config_data = {
            'rules': [{'name': 'test_rule', 'exception_type': 'TestError',
                       'rate_limit': {
                           'max_occurrences': 0,
                           'time_window': 300}}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rate_limit_max_occurrences_negative(self):
        """Test validation fails when max_occurrences is negative."""
        config_data = {
            'rules': [{'name': 'test_rule', 'exception_type': 'TestError',
                      'rate_limit': {
                          'max_occurrences': -1,
                          'time_window': 300}}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rate_limit_time_window_not_number(self):
        """Test validation fails when time_window is not a number."""
        config_data = {
            'rules': [{'name': 'test_rule',
                       'exception_type': 'TestError',
                       'rate_limit': {
                           'max_occurrences': 5,
                           'time_window': 'five_minutes'}}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rate_limit_time_window_zero(self):
        """Test validation fails when time_window is zero."""
        config_data = {
            'rules': [{'name': 'test_rule', 'exception_type': 'TestError',
                       'rate_limit': {
                           'max_occurrences': 5,
                           'time_window': 0}}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rate_limit_time_window_negative(self):
        """Test validation fails when time_window is negative."""
        config_data = {
            'rules': [{'name': 'test_rule', 'exception_type': 'TestError',
                       'rate_limit': {
                           'max_occurrences': 5,
                           'time_window': -300}}]
        }
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )

    def test_rate_limit_time_window_float(self):
        """Test validation succeeds when time_window is a float."""
        config_data = {
            'rules': [{'name': 'test_rule', 'exception_type': 'TestError',
                       'rate_limit': {
                           'max_occurrences': 5,
                           'time_window': 300.5}}]
        }
        config_file = self._create_temp_config(config_data)

        # Should not raise any exceptions
        rules = load_rules_from_file(config_file)
        self.assertEqual(len(rules), 1)

    def test_valid_message_pattern(self):
        """Test validation succeeds with valid regex pattern."""
        config_data = {
            'rules': [{'name': 'test_rule',
                       'message_pattern': 'Connection.*refused.*port\s+\d+'}]  # noqa: W605,E501
        }
        config_file = self._create_temp_config(config_data)

        # Should not raise any exceptions
        rules = load_rules_from_file(config_file)
        self.assertEqual(len(rules), 1)

    def test_valid_message_contains(self):
        """Test validation succeeds with message_contains."""
        config_data = {
            'rules': [{'name': 'test_rule', 'message_contains': 'timeout'}]
        }
        config_file = self._create_temp_config(config_data)

        # Should not raise any exceptions
        rules = load_rules_from_file(config_file)
        self.assertEqual(len(rules), 1)

    def test_complex_valid_rule(self):
        """Test succeeds with complex rule having multiple conditions."""
        config_data = {
            'rules': [{
                'name': 'complex_rule',
                'exception_type': 'DatabaseError',
                'message_contains': 'deadlock',
                'rate_limit': {
                    'max_occurrences': 3,
                    'time_window': 180
                }
            }]
        }
        config_file = self._create_temp_config(config_data)

        # Should not raise any exceptions
        rules = load_rules_from_file(config_file)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]['name'], 'complex_rule')

    def test_config_not_dictionary(self):
        """Test validation fails when config root is not a dictionary."""
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', delete=False
        )
        temp_file.write("- not_a_dict")
        temp_file.close()
        self.temp_files.append(temp_file.name)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, temp_file.name
        )

    def test_rules_not_list(self):
        """Test validation fails when 'rules' is not a list."""
        config_data = {'rules': 'not_a_list'}
        config_file = self._create_temp_config(config_data)

        self.assertRaises(
            RuleValidationError, load_rules_from_file, config_file
        )
