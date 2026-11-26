# Copyright 2026 SAP SE
#
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

"""Tests for loading and running Converged Cloud Lifesaver."""

import base64
import copy
import http.client
from types import SimpleNamespace
from unittest import mock

from cc.keystone.middleware import lifesaver
from cc.keystone.middleware import lifesaver_utils
from cc.keystone.middleware import score
import webob

from keystone.common import provider_api
from keystone.server.flask import core
from keystone.server.flask.request_processing.middleware import auth_context
from keystone.tests import unit
from keystone.tests.unit import test_v3

PROVIDERS = provider_api.ProviderAPIs


class LifesaverLoaderTests(unit.TestCase):
    def _request(self, phase_aware):
        calls = []

        @webob.dec.wsgify
        def backend(request):
            calls.append(('api', request.path))
            return webob.Response(json_body={'ok': True})

        def factory(global_conf, **local_conf):
            def wrap(app):
                phase = local_conf.get('phase', 'post_auth')

                @webob.dec.wsgify
                def middleware(request):
                    name = phase if phase_aware else 'legacy'
                    calls.append((name, request.path))
                    return request.get_response(app)

                # Older factories accept local_conf but ignore phase.
                if phase_aware:
                    middleware.phase = phase
                return middleware

            return wrap

        with (
            mock.patch.object(core, '_APP_MIDDLEWARE', ()),
            mock.patch.object(
                core,
                '_CC_MIDDLEWARE',
                (core._Middleware('lifesaver.middleware', 'lifesaver', {}),),
            ),
            mock.patch.object(
                core.stevedore,
                'DriverManager',
                return_value=SimpleNamespace(
                    driver=SimpleNamespace(factory=factory)
                ),
            ),
            mock.patch.object(
                auth_context.AuthContextMiddleware,
                'process_request',
                side_effect=lambda request: calls.append(
                    ('auth', request.path)
                ),
            ),
        ):
            app = core.setup_app_middleware(SimpleNamespace(wsgi_app=backend))
            result = webob.Request.blank(
                '/v3/s3tokens/',
                method='POST',
                json_body={'credentials': {'access': 'test-key'}},
            ).get_response(app.wsgi_app)
        self.assertEqual(http.client.OK, result.status_int)
        self.assertEqual({'ok': True}, result.json)
        return calls

    def test_legacy_filter_runs_once_after_authentication(self):
        self.assertEqual(
            [(name, '/v3/s3tokens') for name in ('auth', 'legacy', 'api')],
            self._request(phase_aware=False),
        )

    def test_native_phases_surround_authentication_after_normalization(self):
        self.assertEqual(
            [
                (name, '/v3/s3tokens')
                for name in ('pre_auth', 'auth', 'post_auth', 'api')
            ],
            self._request(phase_aware=True),
        )


class LifesaverCoreBase(test_v3.RestfulTestCase):
    phase_aware = True

    def config_overrides(self):
        super().config_overrides()
        # Mock Memcached and StatsD only. Use the real Flask middleware,
        # token validation and SQL credential lookup.
        self.scores = {}
        client = mock.Mock()
        client.cas_ids = {}
        client.get.side_effect = lambda key: copy.deepcopy(
            self.scores.get(key)
        )
        client.gets.side_effect = client.get.side_effect

        def store(key, value, *args, **kwargs):
            self.scores[key] = copy.deepcopy(value)
            return True

        client.set.side_effect = store
        client.add.side_effect = store
        client.cas.side_effect = store
        for patcher in (
            mock.patch.object(
                lifesaver_utils.memcache, 'Client', return_value=client
            ),
            mock.patch.object(lifesaver, 'DogStatsd', create=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.lifesaver_utils = lifesaver_utils.LifesaverUtils({})
        self.config_fixture.config(
            group='lifesaver',
            enabled='true',
            initial_credit=10,
            refill_seconds=600,
            domain_allowlist='',
            user_allowlist='',
        )
        extension = lifesaver.LifesaverMiddleware.factory(
            {}, phase='pre_auth'
        )(webob.Response())
        # Run each integration test with the extension version it needs.
        # The loader tests above always check both old and new factories.
        native = getattr(extension, 'phase', None) == 'pre_auth'
        if native != self.phase_aware:
            self.skipTest(
                'Requires a phase-aware Lifesaver extension'
                if self.phase_aware
                else 'Requires a legacy Lifesaver extension'
            )

    def _missing_credential(self):
        return {
            'credentials': {
                'access': 'missing-access-key',
                'signature': base64.b64encode(b'invalid').decode('ascii'),
                'token': base64.b64encode(b'string to sign').decode('ascii'),
            }
        }


class S3LifesaverCore(LifesaverCoreBase):
    def test_missing_s3_key_is_throttled_before_authentication(self):
        token = self.get_scoped_token()
        with (
            mock.patch.object(
                PROVIDERS.token_provider_api,
                'validate_token',
                wraps=PROVIDERS.token_provider_api.validate_token,
            ) as validate_token,
            mock.patch.object(
                PROVIDERS.credential_api,
                'get_credential',
                wraps=PROVIDERS.credential_api.get_credential,
            ) as get_credential,
        ):
            self.post(
                '/s3tokens',
                token=token,
                body=self._missing_credential(),
                expected_status=http.client.NOT_FOUND,
            )
            validate_token.assert_called_once()
            get_credential.assert_called_once()
            validate_token.reset_mock()
            get_credential.reset_mock()
            self.post(
                '/s3tokens/',
                token=token,
                body=self._missing_credential(),
                expected_status=http.client.TOO_MANY_REQUESTS,
            )
            validate_token.assert_not_called()
            get_credential.assert_not_called()

    def test_exhausted_s3_key_skips_even_invalid_caller_token(self):
        state = score.Score(10, 600, 5)
        state.reduce(10)
        key = self.lifesaver_utils.get_memcache_key(
            'S3CREDS-MISSING-ACCESS-KEY'
        )
        self.scores[key] = state
        with mock.patch.object(
            PROVIDERS.token_provider_api,
            'validate_token',
            wraps=PROVIDERS.token_provider_api.validate_token,
        ) as validate_token:
            self.post(
                '/s3tokens/',
                token='invalid-service-token',
                body=self._missing_credential(),
                expected_status=http.client.TOO_MANY_REQUESTS,
            )
            validate_token.assert_not_called()

    def test_caller_authentication_failure_is_charged_early(self):
        self.post(
            '/s3tokens',
            token='invalid-service-token',
            body=self._missing_credential(),
            expected_status=http.client.UNAUTHORIZED,
        )
        key = self.lifesaver_utils.get_memcache_key(
            'S3CREDS-MISSING-ACCESS-KEY'
        )
        self.assertIn(key, self.scores)
        self.assertEqual(0, self.scores[key].get())
        with mock.patch.object(
            PROVIDERS.token_provider_api,
            'validate_token',
            wraps=PROVIDERS.token_provider_api.validate_token,
        ) as validate_token:
            self.post(
                '/s3tokens',
                token='invalid-service-token',
                body=self._missing_credential(),
                expected_status=http.client.TOO_MANY_REQUESTS,
            )
            validate_token.assert_not_called()


class LegacyS3LifesaverCore(LifesaverCoreBase):
    phase_aware = False

    def test_exhausted_key_is_rejected_after_caller_authentication(self):
        token = self.get_scoped_token()
        state = score.Score(10, 600, 5)
        state.reduce(10)
        key = self.lifesaver_utils.get_memcache_key(
            'S3CREDS-MISSING-ACCESS-KEY'
        )
        self.scores[key] = state
        with (
            mock.patch.object(
                PROVIDERS.token_provider_api,
                'validate_token',
                wraps=PROVIDERS.token_provider_api.validate_token,
            ) as validate_token,
            mock.patch.object(
                PROVIDERS.credential_api,
                'get_credential',
                wraps=PROVIDERS.credential_api.get_credential,
            ) as get_credential,
        ):
            # The older extension encodes its error body as JSON twice.
            # Check its status directly, then check when token validation ran.
            self.public_app.post_json(
                '/v3/s3tokens/',
                self._missing_credential(),
                headers={'X-Auth-Token': token},
                status=http.client.TOO_MANY_REQUESTS,
            )
            validate_token.assert_called_once()
            get_credential.assert_not_called()
