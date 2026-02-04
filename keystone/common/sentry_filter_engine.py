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

from collections import defaultdict
from collections import deque
import logging
import re
import secrets
import time
from typing import Any
from typing import Dict
from typing import List

LOG = logging.getLogger(__name__)


class SentryFilterEngine:
    """Engine for filtering Sentry events based on configurable rules."""

    def __init__(
        self, rules: List[Dict[str, Any]], debug_logging: bool = False
    ):
        """Initialize the filter engine with rules.

        Args:
            rules: List of validated rule dictionaries
            debug_logging: Enable detailed debug logging
            for filtering decisions
        """
        self.rules = rules
        self.debug_logging = debug_logging
        self._rate_limit_tracker: Dict[str, deque] = defaultdict(deque)
        self._compiled_regexes: Dict[str, re.Pattern] = {}

        LOG.info("Initialized Sentry filter engine with %d rules", len(rules))
        self.debug_log("Debug logging enabled for Sentry filtering")

    def should_filter_event(self, hint: Dict[str, Any]) -> bool:
        """Determine if an event should be filtered out.

        Args:
            hint: Holds the original exception information

        Returns:
            True if event should be filtered out (not sent to Sentry)
            False if event should be sent to Sentry
        """
        if not self.rules:
            self.debug_log("No rules configured, allowing event")
            return False

        for rule in self.rules:
            if self._rule_matches(rule, hint):
                rule_name = rule.get('name', 'unnamed')
                self.debug_log("Rule '%s' matched, filtering event", rule_name)
                LOG.info("Filtered Sentry event by rule: %s", rule_name)
                return True

        self.debug_log("No rules matched, allowing event")
        return False

    def _rule_matches(
        self, rule: Dict[str, Any], hint: Dict[str, Any]
    ) -> bool:
        """Check if all conditions in a rule match the event.

        Each condition present in the rule must match the event. If any
        condition does not match the event, the rule does not apply.
        """
        rule_name = rule.get('name', 'unnamed')

        # exception_type
        if 'exception_type' in rule:
            ok = self._match_exception_type(rule['exception_type'], hint)
            if ok:
                self.debug_log(
                    "Rule '%s': exception_type condition matched", rule_name
                )
            else:
                self.debug_log(
                    "Rule '%s': exception_type condition did not match",
                    rule_name,
                )
                return False

        # exception_type_prefix
        if 'exception_type_prefix' in rule:
            ok = self._match_exception_type_prefix(
                rule['exception_type_prefix'], hint
            )
            if ok:
                self.debug_log(
                    "Rule '%s': exception_type_prefix condition matched",
                    rule_name,
                )
            else:
                self.debug_log(
                    "Rule '%s': exception_type_prefix condition did not match",
                    rule_name,
                )
                return False

        # exception_type_suffix
        if 'exception_type_suffix' in rule:
            ok = self._match_exception_type_suffix(
                rule['exception_type_suffix'], hint
            )
            if ok:
                self.debug_log(
                    "Rule '%s': exception_type_suffix condition matched",
                    rule_name,
                )
            else:
                self.debug_log(
                    "Rule '%s': exception_type_suffix condition did not match",
                    rule_name,
                )
                return False

        # message_pattern
        if 'message_pattern' in rule:
            ok = self._match_message_pattern(rule['message_pattern'], hint)
            if ok:
                self.debug_log(
                    "Rule '%s': message_pattern condition matched", rule_name
                )
            else:
                self.debug_log(
                    "Rule '%s': message_pattern condition did not match",
                    rule_name,
                )
                return False

        # message_contains
        if 'message_contains' in rule:
            ok = self._match_message_contains(rule['message_contains'], hint)
            if ok:
                self.debug_log(
                    "Rule '%s': message_contains condition matched", rule_name
                )
            else:
                self.debug_log(
                    "Rule '%s': message_contains condition did not match",
                    rule_name,
                )
                return False

        # rate_limit
        if 'rate_limit' in rule:
            ok = self._check_rate_limit(rule)
            if ok:
                self.debug_log(
                    "Rule '%s': rate_limit condition matched", rule_name
                )
            else:
                self.debug_log(
                    "Rule '%s': rate_limit condition did not match", rule_name
                )
                return False

        # sample_rate
        if 'sample_rate' in rule:
            sample_rate = rule['sample_rate']
            rand_value = secrets.SystemRandom().random()
            if rand_value > sample_rate:
                self.debug_log(
                    "Rule '%s': sample_rate condition"
                    " matched (%.4f <= %.4f)",
                    rule_name,
                    rand_value,
                    sample_rate,
                )
            else:
                self.debug_log(
                    "Rule '%s': sample_rate condition"
                    " did not match (%.4f > %.4f)",
                    rule_name,
                    rand_value,
                    sample_rate,
                )
                return False

        return True

    def _match_exception_type(
        self, rule_type: str, hint: Dict[str, Any]
    ) -> bool:
        """Check if event exception type matches rule.

        Args:
            rule_type: Exception type from rule
            event: Sentry event dictionary

        Returns:
            True if exception type matches
        """
        if 'exc_info' not in hint:
            return False

        exception_instance = hint['exc_info'][1]

        if exception_instance is None:
            return False

        type_name = type(exception_instance).__name__
        return type_name == rule_type

    def _match_exception_type_prefix(
        self, prefix: str, hint: Dict[str, Any]
    ) -> bool:
        """Check if event exception type starts with prefix.

        Args:
            prefix: Prefix string to match
            hint: Sentry event hint dictionary

        Returns:
            True if exception type starts with prefix
        """
        if 'exc_info' not in hint:
            return False

        exception_instance = hint['exc_info'][1]

        if exception_instance is None:
            return False

        type_name = type(exception_instance).__name__
        return type_name.startswith(prefix)

    def _match_exception_type_suffix(
        self, suffix: str, hint: Dict[str, Any]
    ) -> bool:
        """Check if event exception type ends with suffix.

        Args:
            suffix: Suffix string to match
            hint: Sentry event hint dictionary

        Returns:
            True if exception type ends with suffix
        """
        if 'exc_info' not in hint:
            return False

        exception_instance = hint['exc_info'][1]

        if exception_instance is None:
            return False

        type_name = type(exception_instance).__name__
        return type_name.endswith(suffix)

    def _match_message_pattern(
        self, pattern: str, hint: Dict[str, Any]
    ) -> bool:
        """Check if event exception message matches regex pattern.

        Args:
            pattern: Regex pattern string
            hint: Sentry event hint dictionary

        Returns:
            True if message matches pattern
        """
        if 'exc_info' not in hint:
            return False

        exception_instance = hint['exc_info'][1]

        if exception_instance is None:
            return False

        # Cache compiled regex for performance
        if pattern not in self._compiled_regexes:
            self._compiled_regexes[pattern] = re.compile(pattern)

        regex = self._compiled_regexes[pattern]

        message = str(exception_instance)

        return bool(regex.search(message))

    def _match_message_contains(
        self, search_string: str, hint: Dict[str, Any]
    ) -> bool:
        """Check if event exception message contains string.

        Args:
            search_string: String to search for
            event: Sentry event dictionary

        Returns:
            True if message contains string
        """
        if 'exc_info' not in hint:
            return False

        exception_instance = hint['exc_info'][1]

        if exception_instance is None:
            return False

        message = str(exception_instance)

        return search_string in message

    def _check_rate_limit(self, rule: Dict[str, Any]) -> bool:
        """Check if rule should apply based on rate limiting.

        Args:
            rule: Rule dictionary with rate limiting parameters

        Returns:
            True if rule should apply (event should be filtered)
            False if not at rate limit yet (event should not be filtered)
        """
        rule_name = rule.get('name', 'unnamed')
        current_time = time.time()

        rate_limit = rule['rate_limit']
        occurrences = self._rate_limit_tracker[rule_name]
        cutoff_time = current_time - rate_limit['time_window']

        # Clean old entries
        removed_count = 0
        while occurrences and occurrences[0] < cutoff_time:
            occurrences.popleft()
            removed_count += 1

        if self.debug_logging and removed_count > 0:
            LOG.debug(
                "Rule '%s': cleaned %d old occurrences",
                rule_name,
                removed_count,
            )

        # Check if we've hit the limit
        current_count = len(occurrences)
        max_occurrences = rate_limit['max_occurrences']

        if current_count >= max_occurrences:
            if self.debug_logging:
                LOG.debug(
                    "Rule '%s': rate limit reached (%d >= %d)",
                    rule_name,
                    current_count,
                    max_occurrences,
                )
            return True  # Rule applies - filter this event

        # Add current occurrence
        occurrences.append(current_time)

        if self.debug_logging:
            LOG.debug(
                "Rule '%s': added occurrence (%d/%d in %ds window)",
                rule_name,
                current_count + 1,
                max_occurrences,
                rate_limit['time_window'],
            )

        return False  # Not at limit yet - don't filter

    def debug_log(self, *args: Any) -> None:
        """Log a debug message if debug logging is enabled.

        Args:
            message: Message to log
        """
        if self.debug_logging:
            LOG.debug(*args)
