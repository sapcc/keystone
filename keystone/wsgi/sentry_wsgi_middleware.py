import logging
import os

from keystone.server.wsgi import initialize_public_application

import sentry_sdk
from sentry_sdk.integrations import wsgi


logger = logging.getLogger(__name__)

# get exceptions list as comma separated string from environment
sentry_exclusion_list_string = os.environ.get("SENTRY_EXCLUSIONS_LIST", "")
sentry_exclusion_list = sentry_exclusion_list_string.split(",")
# ["Unauthorized", "LDAPInvalidCredentialsError"]

# check for SENTRY_DSN
# make sure to use the old lagacy DSN fromat
sentry_dsn = os.environ.get("SENTRY_DSN", None)
if sentry_dsn is None:
    logger.warning("SENTRY_DSN not found in Environment")


def before_send(event, _):
    if "exception" in event:
        if "values" in event["exception"]:
            for value in event["exception"]["values"]:
                if "type" in value:
                    exception_type = value["type"]
                    if exception_type in sentry_exclusion_list:
                        logger.info("[-] filtered out: %s", exception_type)
                        return None
    return event


sentry_sdk.init(dsn=sentry_dsn, debug=False, before_send=before_send)

def sentry_wsgi_public_wrapper():
    application = initialize_public_application()
    sentry_wsgi_public_app = wsgi.SentryWsgiMiddleware(application)
    return sentry_wsgi_public_app

sentry_wsgi_admin_wrapper = sentry_wsgi_public_wrapper
