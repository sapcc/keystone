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

from keystone.common.sentry_filter_engine import SentryFilterEngine
from keystone.tests import unit


class SentryFilterEngineTestCase(unit.BaseTestCase):
    """Test suite for Sentry filter engine functionality."""

    def setUp(self):
        """Set up test fixtures."""
        super(SentryFilterEngineTestCase, self).setUp()
    
    def _create_hint_with_exception(self, exception_type_name, message):
        """Create a hint structure with a mock exception for testing."""
        # Create a custom exception class with the desired name
        class CustomException(Exception):
            pass
        
        CustomException.__name__ = exception_type_name
        mock_exception = CustomException(message)
        
        return {
            'exc_info': (CustomException, mock_exception, None)
        }

    def test_no_rules_allows_all_events(self):
        """Test that engine with no rules allows all events."""
        engine = SentryFilterEngine([])
        
        hint = self._create_hint_with_exception('TestError', 'test message')

        result = engine.should_filter_event(hint)
        self.assertFalse(result)

    def test_exception_type_matching(self):
        """Test basic exception type matching."""
        rules = [{'name': 'test_rule', 'exception_type': 'TestError'}]
        engine = SentryFilterEngine(rules)

        # Matching hint should be filtered
        matching_hint = self._create_hint_with_exception('TestError', 'test')
        result = engine.should_filter_event(matching_hint)
        self.assertTrue(result)

        # Non-matching hint should not be filtered
        non_matching_hint = self._create_hint_with_exception('OtherError', 'test')
        result = engine.should_filter_event(non_matching_hint)
        self.assertFalse(result)

    def test_message_contains_matching(self):
        """Test basic message contains matching."""
        rules = [{'name': 'test_rule', 'message_contains': 'timeout'}]
        engine = SentryFilterEngine(rules)

        # Matching hint should be filtered
        matching_hint = self._create_hint_with_exception('Error', 'connection timeout error')
        result = engine.should_filter_event(matching_hint)
        self.assertTrue(result)

        # Non-matching hint should not be filtered
        non_matching_hint = self._create_hint_with_exception('Error', 'other error')
        result = engine.should_filter_event(non_matching_hint)
        self.assertFalse(result)

    def test_message_pattern_matching(self):
        """Test basic regex pattern matching."""
        rules = [{'name': 'test_rule', 'message_pattern': 'error.*\\d+'}]
        engine = SentryFilterEngine(rules)

        # Matching hint should be filtered
        matching_hint = self._create_hint_with_exception('Error', 'error code 500')
        result = engine.should_filter_event(matching_hint)
        self.assertTrue(result)

        # Non-matching hint should not be filtered
        non_matching_hint = self._create_hint_with_exception('Error', 'error without number')
        result = engine.should_filter_event(non_matching_hint)
        self.assertFalse(result)

    def test_rate_limiting_basic_functionality(self):
        """Test basic rate limiting functionality."""
        rules = [{
            'name': 'rate_limited_rule',
            'exception_type': 'TestError',
            'rate_limit': {'max_occurrences': 2, 'time_window': 60}
        }]
        engine = SentryFilterEngine(rules)
        hint = self._create_hint_with_exception('TestError', 'test')

        # First occurrence should not be filtered (not at limit yet)
        result = engine.should_filter_event(hint)
        self.assertFalse(result)

        # Second occurrence should not be filtered (not at limit yet)
        result = engine.should_filter_event(hint)
        self.assertFalse(result)

        # Third occurrence should be filtered (at limit)
        result = engine.should_filter_event(hint)
        self.assertTrue(result)

    @mock.patch('time.time')
    def test_rate_limiting_time_window(self, mock_time):
        """Test that rate limiting respects time windows."""
        rules = [{
            'name': 'rate_limited_rule',
            'exception_type': 'TestError',
            'rate_limit': {'max_occurrences': 1, 'time_window': 10}
        }]
        engine = SentryFilterEngine(rules)
        hint = self._create_hint_with_exception('TestError', 'test')

        # First occurrence at time 0
        mock_time.return_value = 0
        result = engine.should_filter_event(hint)
        self.assertFalse(result)

        # Second occurrence at time 5 (within window) should be filtered
        mock_time.return_value = 5
        result = engine.should_filter_event(hint)
        self.assertTrue(result)

        # Third occurrence at time 15 (outside window) should not be filtered
        mock_time.return_value = 15
        result = engine.should_filter_event(hint)
        self.assertFalse(result)

    def test_multiple_conditions_must_all_match(self):
        """Test that rules with multiple conditions require all to match."""
        rules = [{
            'name': 'multi_condition_rule',
            'exception_type': 'TestError',
            'message_contains': 'timeout'
        }]
        engine = SentryFilterEngine(rules)

        # Hint matching both conditions should be filtered
        matching_hint = self._create_hint_with_exception('TestError', 'timeout error')
        result = engine.should_filter_event(matching_hint)
        self.assertTrue(result)

        # Hint matching only one condition should not be filtered
        partial_match_hint = self._create_hint_with_exception('TestError', 'other error')
        result = engine.should_filter_event(partial_match_hint)
        self.assertFalse(result)

    def test_empty_event_handling(self):
        """Test handling of malformed or empty hints."""
        rules = [{'name': 'test_rule', 'exception_type': 'TestError'}]
        engine = SentryFilterEngine(rules)

        # Empty hint should not be filtered
        empty_hint = {}
        result = engine.should_filter_event(empty_hint)
        self.assertFalse(result)

        # Hint without exc_info should not be filtered
        no_exception_hint = {'other_field': 'value'}
        result = engine.should_filter_event(no_exception_hint)
        self.assertFalse(result)
