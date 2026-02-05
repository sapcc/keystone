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

import logging
import os
import re
import yaml

from typing import Any
from typing import Dict
from typing import List

LOG = logging.getLogger(__name__)


class RuleValidationError(Exception):
    """Raised when a rule fails validation."""

    pass


def load_rules_from_file(config_file: str) -> List[Dict[str, Any]]:
    """Load and validate Sentry filtering rules from YAML file.

    Args:
        config_file: Path to the YAML configuration file

    Returns:
        List of validated rule dictionaries

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML parsing fails
        RuleValidationError: If rule validation fails
    """
    LOG.info("Loading Sentry filter rules from: %s", config_file)

    if not os.path.exists(config_file):
        # return empty list if config file does not exist
        LOG.warning("Sentry filter config file not found: %s", config_file)
        return []

    try:
        with open(config_file) as f:
            config_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(
            f"Failed to parse YAML config file {config_file}: {e}"
        )

    if not isinstance(config_data, dict):
        raise RuleValidationError("Config file must contain a YAML dictionary")

    if 'rules' not in config_data:
        raise RuleValidationError("Config file must contain a 'rules' section")

    rules = config_data['rules']
    if not isinstance(rules, dict):
        raise RuleValidationError("'rules' section must be a dictionary")

    validated_rules = []
    for rule_name, rule_config in rules.items():
        try:
            if not isinstance(rule_config, dict):
                raise RuleValidationError(
                    f"Rule '{rule_name}' configuration must be a dictionary, got {type(rule_config).__name__}"
                )
            # Inject the rule name into the config
            rule_with_name = {'name': rule_name, **rule_config}
            validated_rule = _validate_rule(rule_with_name, rule_name)
            validated_rules.append(validated_rule)
        except RuleValidationError as e:
            LOG.error("Rule validation failed for rule '%s': %s", rule_name, e)
            raise RuleValidationError(
                f"Rule '{rule_name}' validation failed: {e}"
            )

    LOG.info(
        "Successfully loaded %d Sentry filter rules", len(validated_rules)
    )
    return validated_rules


def _validate_rule(rule: Dict[str, Any], rule_name: str) -> Dict[str, Any]:
    """Validate a single filtering rule.

    Args:
        rule: Rule dictionary to validate
        rule_name: Name of rule for error reporting

    Returns:
        Validated rule dictionary

    Raises:
        RuleValidationError: If rule validation fails
    """
    if not isinstance(rule, dict):
        raise RuleValidationError(
            f"Rule must be a dictionary, got {type(rule)}"
        )

    # Rule name is required for logging and rate limiting identification
    if 'name' not in rule:
        raise RuleValidationError("Rule must have a 'name' field")

    if not isinstance(rule['name'], str) or not rule['name'].strip():
        raise RuleValidationError("Rule 'name' must be a non-empty string")

    # At least one filtering condition must be specified
    has_condition = any(
        field in rule
        for field in [
            'exception_type',
            'exception_type_prefix',
            'exception_type_suffix',
            'message_pattern',
            'message_contains',
        ]
    )

    if not has_condition:
        raise RuleValidationError(
            "Rule must specify at least one condition: "
            "'exception_type', 'exception_type_prefix', 'exception_type_suffix', "
            "'message_pattern', or 'message_contains'"
        )

    # Validate exception_type
    if 'exception_type' in rule:
        if not isinstance(rule['exception_type'], str):
            raise RuleValidationError("'exception_type' must be a string")

    # Validate exception_type_prefix
    if 'exception_type_prefix' in rule:
        if not isinstance(rule['exception_type_prefix'], str):
            raise RuleValidationError(
                "'exception_type_prefix' must be a string"
            )

    # Validate exception_type_suffix
    if 'exception_type_suffix' in rule:
        if not isinstance(rule['exception_type_suffix'], str):
            raise RuleValidationError(
                "'exception_type_suffix' must be a string"
            )

    # Validate message_pattern (regex)
    if 'message_pattern' in rule:
        if not isinstance(rule['message_pattern'], str):
            raise RuleValidationError("'message_pattern' must be a string")

        # Test regex compilation
        try:
            re.compile(rule['message_pattern'])
        except re.error as e:
            raise RuleValidationError(
                f"Invalid regex in 'message_pattern': {e}"
            )

    # Validate message_contains
    if 'message_contains' in rule:
        if not isinstance(rule['message_contains'], str):
            raise RuleValidationError("'message_contains' must be a string")

    # Validate rate limiting parameters
    if 'rate_limit' in rule:
        rate_limit = rule['rate_limit']

        if not isinstance(rate_limit, dict):
            raise RuleValidationError("'rate_limit' must be a dictionary")

        if (
            'max_occurrences' not in rate_limit
            or 'time_window' not in rate_limit
        ):
            raise RuleValidationError(
                "Rate limiting requires both 'max_occurrences'"
                " and 'time_window'"
            )

        if (
            not isinstance(rate_limit['max_occurrences'], int)
            or rate_limit['max_occurrences'] <= 0
        ):
            raise RuleValidationError(
                "'rate_limit.max_occurrences' must be a positive integer"
            )

        if (
            not isinstance(rate_limit['time_window'], (int, float))
            or rate_limit['time_window'] <= 0
        ):
            raise RuleValidationError(
                "'rate_limit.time_window' must be a positive number"
            )
    # Validate sample parameters
    if 'sample_rate' in rule:
        sample_rate = rule['sample_rate']
        if not isinstance(sample_rate, (int, float)):
            raise RuleValidationError("'sample_rate' must be a number")

        if not (0.0 < sample_rate <= 1.0):
            raise RuleValidationError("'sample_rate' must be between 0 and 1")

    return rule


def create_example_config_file(output_file: str) -> None:
    """Create an example configuration file with common filtering rules.

    Args:
        output_file: Path where to write the example config
    """
    example_config = {
        'rules': {
            'exclude_unauthorized': {'exception_type': 'Unauthorized'},
            'exclude_ldap_credentials': {
                'exception_type': 'LDAPInvalidCredentialsError'
            },
            'rate_limit_ldap_connection': {
                'exception_type': 'LDAPServerConnectionError',
                'rate_limit': {'max_occurrences': 5, 'time_window': 300},
            },
            'filter_timeout_messages': {
                'message_contains': 'timeout',
                'sample_rate': 0.5,
            },
            'filter_connection_refused': {
                'message_pattern': r'Connection.*refused.*port\s+\d+'
            },
            'complex_database_rule': {
                'exception_type': 'DatabaseError',
                'message_contains': 'deadlock',
                'rate_limit': {'max_occurrences': 3, 'time_window': 180},
            },
        }
    }

    with open(output_file, 'w') as f:
        yaml.dump(example_config, f, default_flow_style=False, indent=2)

    LOG.info("Created example Sentry filter config at: %s", output_file)
