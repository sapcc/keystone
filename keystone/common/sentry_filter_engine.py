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

import re
import time
import logging
from collections import defaultdict, deque
from typing import Dict, List, Any, Optional

LOG = logging.getLogger(__name__)


class SentryFilterEngine:
    """Engine for filtering Sentry events based on configurable rules."""
    
    def __init__(self, rules: List[Dict[str, Any]], debug_logging: bool = False):
        """Initialize the filter engine with rules.
        
        Args:
            rules: List of validated rule dictionaries
            debug_logging: Enable detailed debug logging for filtering decisions
        """
        self.rules = rules
        self.debug_logging = debug_logging
        self._rate_limit_tracker = defaultdict(deque)
        self._compiled_regexes = {}
        
        LOG.info("Initialized Sentry filter engine with %d rules", len(rules))
        self.debug_log("Debug logging enabled for Sentry filtering")
    
    def should_filter_event(self, event: Dict[str, Any]) -> bool:
        """Determine if an event should be filtered out.
        
        Args:
            event: Sentry event dictionary
            
        Returns:
            True if event should be filtered out (not sent to Sentry)
            False if event should be sent to Sentry
        """
        if not self.rules:
            self.debug_log("No rules configured, allowing event")
            return False
        
        for rule in self.rules:
            if self._rule_matches(rule, event):
                rule_name = rule.get('name', 'unnamed')
                self.debug_log("Rule '%s' matched, filtering event", rule_name)
                LOG.info("Filtered Sentry event by rule: %s", rule_name)
                return True

        self.debug_log("No rules matched, allowing event")
        return False
    
    def _rule_matches(self, rule: Dict[str, Any], event: Dict[str, Any]) -> bool:
        """Check if all conditions in a rule match the event."""
        rule_name = rule.get('name', 'unnamed')
        
        conditions = [
            ('exception_type', lambda: self._match_exception_type(rule['exception_type'], event)),
            ('message_pattern', lambda: self._match_message_pattern(rule['message_pattern'], event)),
            ('message_contains', lambda: self._match_message_contains(rule['message_contains'], event)),
            ('rate_limit', lambda: self._check_rate_limit(rule, event)),
        ]
        
        for condition_key, checker in conditions:
            if condition_key in rule:
                if checker():
                    self.debug_log("Rule '%s': %s condition matched", rule_name, condition_key)
                else:
                    self.debug_log("Rule '%s': %s condition did not match", rule_name, condition_key)
                    return False
        
        return True 
    
    def _match_exception_type(self, rule_type: str, event: Dict[str, Any]) -> bool:
        """Check if event exception type matches rule.
        
        Args:
            rule_type: Exception type from rule
            event: Sentry event dictionary
            
        Returns:
            True if exception type matches
        """
        exception_values = event.get('exception', {}).get('values', [])
        for exc_value in exception_values:
            if exc_value.get('type') == rule_type:
                return True
        return False
    
    def _match_message_pattern(self, pattern: str, event: Dict[str, Any]) -> bool:
        """Check if event exception message matches regex pattern.
        
        Args:
            pattern: Regex pattern string
            event: Sentry event dictionary
            
        Returns:
            True if message matches pattern
        """
        # Cache compiled regex for performance
        if pattern not in self._compiled_regexes:
            self._compiled_regexes[pattern] = re.compile(pattern)
        
        regex = self._compiled_regexes[pattern]
        exception_values = event.get('exception', {}).get('values', [])
        
        for exc_value in exception_values:
            message = exc_value.get('value', '')
            if regex.search(message):
                return True
        return False
    
    def _match_message_contains(self, search_string: str, event: Dict[str, Any]) -> bool:
        """Check if event exception message contains string.
        
        Args:
            search_string: String to search for
            event: Sentry event dictionary
            
        Returns:
            True if message contains string
        """
        exception_values = event.get('exception', {}).get('values', [])
        for exc_value in exception_values:
            message = exc_value.get('value', '')
            if search_string in message:
                return True
        return False
    
    def _check_rate_limit(self, rule: Dict[str, Any], event: Dict[str, Any]) -> bool:
        """Check if rule should apply based on rate limiting.
        
        Args:
            rule: Rule dictionary with rate limiting parameters
            event: Sentry event dictionary
            
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
            LOG.debug("Rule '%s': cleaned %d old occurrences", rule_name, removed_count)
        
        # Check if we've hit the limit
        current_count = len(occurrences)
        max_occurrences = rate_limit['max_occurrences']
        
        if current_count >= max_occurrences:
            if self.debug_logging:
                LOG.debug("Rule '%s': rate limit reached (%d >= %d)", 
                         rule_name, current_count, max_occurrences)
            return True  # Rule applies - filter this event
        
        # Add current occurrence
        occurrences.append(current_time)
        
        if self.debug_logging:
            LOG.debug("Rule '%s': added occurrence (%d/%d in %ds window)", 
                     rule_name, current_count + 1, max_occurrences, rate_limit['time_window'])
        
        return False  # Not at limit yet - don't filter


    def debug_log(self, *args: Any) -> None:
        """Log a debug message if debug logging is enabled.
        
        Args:
            message: Message to log
        """
        if self.debug_logging:
            LOG.debug(*args)
