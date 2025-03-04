from keystone.server.wsgi import initialize_public_application

import sentry_sdk
from sentry_sdk.integrations import wsgi

import logging
import os
import sys

LOG = logging.getLogger(__name__)

handler = logging.StreamHandler(sys.stdout)
LOG.addHandler(handler)

# get exceptions list as comma separated string from environment
sentry_exclusion_list_string = os.environ.get("SENTRY_EXCLUSIONS_LIST", "")
sentry_exclusion_list = sentry_exclusion_list_string.split(",")
# filtered_exceptions_names = ["Unauthorized", "LDAPInvalidCredentialsError"]

# check for SENTRY_DSN
# make sure to use the old lagacy DSN fromat because Sentry Instance is version 9.1.2
sentry_dsn = os.environ.get("SENTRY_DSN", None)
if sentry_dsn is None:
    LOG.warning("SENTRY_DSN not found in Environment")


def before_send(event, _):
    if "exception" in event:
        for value in event["exception"]["values"]:
            exception_type = value["type"]
            if exception_type in sentry_exclusion_list:
                LOG.info(f"[-] filtered out: {exception_type}")
                return None
    LOG.info("[+] send event")
    return event


sentry_sdk.init(dsn=sentry_dsn, debug=False, before_send=before_send)

application = initialize_public_application()
application = wsgi.SentryWsgiMiddleware(application)
