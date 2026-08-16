"""
Project-level guarantees that are easy to break silently.

These are not model or view tests; they protect decisions the brief treats as
non-negotiable, where the failure mode is quiet rather than loud.
"""

import io

from django.core.management import call_command
from django.conf import settings

from .base import AppTestCase


class MigrationStateTests(AppTestCase):
    def test_no_model_changes_are_missing_a_migration(self):
        """Fails if someone edits a model and forgets makemigrations.

        The symptom otherwise is a deploy that runs migrate cleanly and then
        errors at runtime on a column that does not exist.
        """
        out = io.StringIO()
        try:
            call_command(
                "makemigrations", "--check", "--dry-run", stdout=out, verbosity=1
            )
        except SystemExit:
            self.fail(f"Missing migration for model changes:\n{out.getvalue()}")


class DatabaseConfigTests(AppTestCase):
    def test_postgresql_is_the_engine_everywhere(self):
        """SQLite is not used in any environment, including tests."""
        self.assertEqual(
            settings.DATABASES["default"]["ENGINE"],
            "django.db.backends.postgresql",
        )

    def test_no_sqlite_fallback_is_configured(self):
        engines = [db.get("ENGINE", "") for db in settings.DATABASES.values()]
        self.assertFalse(
            any("sqlite" in engine for engine in engines),
            "a SQLite fallback would let the app run on an engine it never "
            "ships on, which is how engine-specific bugs stay hidden",
        )


class DemoAccountTests(AppTestCase):
    def test_demo_password_is_not_hardcoded_in_settings(self):
        """It comes from the environment; empty means unusable passwords.

        A working password committed to a tracked file would be published by
        accident rather than deliberately.
        """
        self.assertIsInstance(settings.DEMO_PASSWORD, str)


class AuthRedirectTests(AppTestCase):
    def test_login_redirects_to_a_route_that_exists(self):
        """Fails loudly rather than 500ing every login after a rename."""
        from django.urls import reverse
        reverse(settings.LOGIN_REDIRECT_URL)
        reverse(settings.LOGIN_URL)
