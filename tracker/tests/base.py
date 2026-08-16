"""
Base test cases that pin the deployment settings the suite depends on.

The test client speaks plain HTTP. On the deployed box SECURE_SSL_REDIRECT is
true, so SecurityMiddleware answers every test request with a 301 to https://
before it ever reaches a view, and all seventy-five tests fail on the status
code. That is the application behaving correctly and the tests asserting
against a configuration that deployment had changed underneath them.

Pinning it here rather than in settings.py keeps the fix out of production
config: settings.py stays purely environment-driven with no "if running tests"
branch, and the suite states its own assumptions instead of inheriting whatever
the current .env happens to say. Any test that genuinely needs the redirect can
override it back.
"""

from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings

# HSTS goes too: it is harmless in tests but would put a
# Strict-Transport-Security header on every response, which any test asserting
# on the exact header set would then have to know about.
TEST_SETTINGS = {
    "SECURE_SSL_REDIRECT": False,
    "SECURE_HSTS_SECONDS": 0,
}


@override_settings(**TEST_SETTINGS)
class AppTestCase(TestCase):
    """Standard case: each test runs in a transaction that is rolled back."""


@override_settings(**TEST_SETTINGS)
class AppTransactionTestCase(TransactionTestCase):
    """For tests that need real commits — the concurrency ones."""
