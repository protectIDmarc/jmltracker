"""
Demo hardening: the reset command and the banner.

reset_demo deletes every row in the application. The guard that stops it
running outside a demo is the most safety-critical line in the project, so it
gets the most direct test.
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse

from tracker.models import AccessRequest, Employee, System

from .base import AppTestCase
from .factories import make_request, make_user


class ResetDemoGuardTests(AppTestCase):
    @override_settings(DEMO_MODE=False)
    def test_it_refuses_to_run_when_demo_mode_is_off(self):
        """Fails if the DEMO_MODE guard is removed.

        Without it, a stray cron entry on a real deployment deletes every
        access request in the system.
        """
        user = make_user()
        make_request(requested_by=user)
        before = AccessRequest.objects.count()

        with self.assertRaises(CommandError):
            call_command("reset_demo", verbosity=0)

        self.assertEqual(AccessRequest.objects.count(), before)

    @override_settings(DEMO_MODE=False)
    def test_force_overrides_the_guard(self):
        """The escape hatch exists, but has to be asked for explicitly."""
        call_command("reset_demo", force=True, verbosity=0, stdout=StringIO())
        self.assertTrue(System.objects.exists())

    @override_settings(DEMO_MODE=True)
    def test_it_runs_when_demo_mode_is_on(self):
        call_command("reset_demo", verbosity=0, stdout=StringIO())
        self.assertTrue(System.objects.exists())
        self.assertTrue(Employee.objects.exists())
        self.assertTrue(AccessRequest.objects.exists())


@override_settings(DEMO_MODE=True)
class ResetDemoEffectTests(AppTestCase):
    def test_it_discards_visitor_changes(self):
        """A request created by a visitor does not survive the reset."""
        user = make_user()
        visitor_request = make_request(requested_by=user, notes="visitor edit")
        self.assertTrue(
            AccessRequest.objects.filter(pk=visitor_request.pk).exists()
        )

        call_command("reset_demo", verbosity=0, stdout=StringIO())

        self.assertFalse(
            AccessRequest.objects.filter(pk=visitor_request.pk).exists()
        )
        self.assertFalse(AccessRequest.objects.filter(notes="visitor edit").exists())

    def test_it_leaves_a_consistent_spread(self):
        """The point of resetting is to restore something worth looking at."""
        call_command("reset_demo", verbosity=0, stdout=StringIO())

        statuses = set(AccessRequest.objects.values_list("status", flat=True))
        self.assertGreaterEqual(len(statuses), 5)

        # The guards must still hold against the restored data, or the demo
        # shows a state the application would refuse to create.
        decided = {"approved", "rejected", "completed"}
        self.assertEqual(
            AccessRequest.objects.filter(status__in=decided, approver__isnull=True).count(), 0
        )
        self.assertEqual(
            AccessRequest.objects.filter(status="pending", approver__isnull=True).count(), 0
        )
        self.assertEqual(
            sum(1 for r in AccessRequest.objects.all()
                if r.approver_id and r.approver_id == r.requested_by_id), 0
        )

    def test_the_demo_accounts_stay_non_staff(self):
        """Admin must remain closed to shared, publicly published logins."""
        from django.contrib.auth import get_user_model
        call_command("reset_demo", verbosity=0, stdout=StringIO())

        for username in ["requester.demo", "approver.demo"]:
            account = get_user_model().objects.get(username=username)
            self.assertFalse(account.is_staff, f"{username} must not be staff")
            self.assertFalse(account.is_superuser)

    def test_it_is_repeatable(self):
        """Running twice leaves the same shape — it is a scheduled job."""
        call_command("reset_demo", verbosity=0, stdout=StringIO())
        first = (AccessRequest.objects.count(), Employee.objects.count(),
                 System.objects.count())
        call_command("reset_demo", verbosity=0, stdout=StringIO())
        self.assertEqual(
            (AccessRequest.objects.count(), Employee.objects.count(),
             System.objects.count()),
            first,
        )


class DemoBannerTests(AppTestCase):
    @override_settings(DEMO_MODE=True)
    def test_the_banner_shows_on_the_login_page_when_demo_mode_is_on(self):
        """Anonymous visitors should know before they start changing things."""
        body = self.client.get(reverse("login")).content.decode()
        self.assertIn("Demonstration site", body)

    @override_settings(DEMO_MODE=False)
    def test_no_banner_when_demo_mode_is_off(self):
        body = self.client.get(reverse("login")).content.decode()
        self.assertNotIn("Demonstration site", body)

    @override_settings(DEMO_MODE=True)
    def test_the_banner_shows_when_signed_in(self):
        self.client.force_login(make_user())
        body = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Demonstration site", body)

    @override_settings(DEMO_MODE=True)
    def test_the_banner_carries_no_credentials(self):
        """The README is the only place the demo logins are published."""
        body = self.client.get(reverse("login")).content.decode().lower()
        for needle in ["requester.demo", "approver.demo", "demopassword"]:
            self.assertNotIn(needle, body)
