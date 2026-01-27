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

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations import wsgi
from sentry_sdk.scrubber import DEFAULT_DENYLIST
from sentry_sdk.scrubber import EventScrubber
from sentry_sdk.utils import BadDsn

from keystone.common.sentry_filter_engine import SentryFilterEngine
from keystone.common.sentry_rule_loader import load_rules_from_file
from keystone.common.sentry_rule_loader import RuleValidationError
from keystone.server.wsgi import initialize_public_application


logger = logging.getLogger(__name__)

filter_engine = None
denylist = (
    DEFAULT_DENYLIST
    + [
        'old_password',
        'new_password',
        'password',
        'cred',
        'secret',
        'passwd',
        'credentials',
        'x_auth_token',
        'x_subject_token',
    ]
)

# Environment variable configuration
# SENTRY_FILTER_CONFIG_FILE: Path to YAML file with filtering rules
# SENTRY_DEBUG_FILTERING: Enable debug logging for filtering (true/false)
# SENTRY_DSN: Sentry DSN for error reporting


def _initialize_sentry_filtering():
    """Initialize the Sentry filtering engine using environment variables.

    This reads SENTRY_FILTER_CONFIG_FILE and SENTRY_DEBUG_FILTERING from the
    environment and sets up the global filter engine accordingly.
    """
    global filter_engine

    sentry_filter_config = os.environ.get("SENTRY_FILTER_CONFIG_FILE")
    debug_filtering_str = os.environ.get(
        "SENTRY_DEBUG_FILTERING", "false"
    ).lower()
    debug_filtering = debug_filtering_str in ("true", "1", "yes", "on")

    if not sentry_filter_config:
        logger.info(
            "SENTRY_FILTER_CONFIG_FILE not set, Sentry filtering disabled"
        )
        return

    if not os.path.exists(sentry_filter_config):
        logger.warning(
            "Sentry filter config file not found at %s, filtering disabled",
            sentry_filter_config,
        )
        return

    try:
        rules = load_rules_from_file(sentry_filter_config)
        filter_engine = SentryFilterEngine(
            rules, debug_logging=debug_filtering
        )
        logger.info(
            "Loaded %d Sentry filter rules from %s",
            len(rules),
            sentry_filter_config,
        )

    except RuleValidationError as e:
        logger.error("Failed to load Sentry filter config: %s", e)
        logger.warning(
            "Sentry filtering disabled due to configuration error"
        )
    except Exception as e:
        logger.error("Unexpected error loading Sentry filter config: %s", e)
        logger.warning(
            "Sentry filtering disabled due to unexpected error"
        )


def before_send(event, hint):
    """Sentry before_send hook to filter events based on configured rules."""
    if filter_engine and filter_engine.should_filter_event(hint):
        return None
    return event


def _initialize_sentry_sdk():
    """Initialize Sentry SDK with config from environment variables."""
    sentry_dsn = os.environ.get("SENTRY_DSN")
    if not sentry_dsn:
        logger.warning(
            "SENTRY_DSN not found in environment, Sentry disabled"
        )
        return
    if sentry_dsn.startswith("requests+"):
        sentry_dsn = sentry_dsn[len("requests+") :]
    release_tag = os.environ.get("IMAGE_TAG", "unknown")

    try:
        sentry_sdk.init(
            dsn=sentry_dsn,
            send_default_pii=False,
            release=release_tag,
            event_scrubber=EventScrubber(denylist=denylist),
            before_send=before_send,
            integrations=[
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR,
                ),
            ],
            debug=False,
        )

        logger.info("Sentry SDK initialized successfully")
    except BadDsn as e:
        logger.error("Bad SENTRY_DSN format: %s", e)
    except Exception as e:
        logger.error("Exception while initializing Sentry SDK: %s", e)


def sentry_wsgi_public_wrapper():
    """Create WSGI application wrapped with Sentry middleware."""
    _initialize_sentry_filtering()
    _initialize_sentry_sdk()

    application = initialize_public_application()
    sentry_wsgi_public_app = wsgi.SentryWsgiMiddleware(application)
    return sentry_wsgi_public_app


sentry_wsgi_admin_wrapper = sentry_wsgi_public_wrapper
