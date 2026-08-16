"""Dashboard aggregation and the awaiting-my-approval panel."""

from django.urls import reverse

from tracker.models import AccessRequest

from .base import AppTestCase
from .factories import make_request, make_user


class DashboardCountTests(AppTestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user()
        self.client.force_login(self.user)

        for status in [
            AccessRequest.Status.DRAFT,
            AccessRequest.Status.PENDING,
            AccessRequest.Status.PENDING,
            AccessRequest.Status.APPROVED,
            AccessRequest.Status.COMPLETED,
            AccessRequest.Status.REJECTED,
            AccessRequest.Status.CANCELLED,
        ]:
            make_request(
                requested_by=self.other,
                approver=self.user if status != AccessRequest.Status.DRAFT else None,
                status=status,
            )

    def test_counts_match_the_data(self):
        stats = self.client.get(reverse("dashboard")).context["stats"]
        self.assertEqual(stats["total"], 7)
        self.assertEqual(stats["draft"], 1)
        self.assertEqual(stats["pending"], 2)
        self.assertEqual(stats["approved"], 1)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["rejected"], 1)
        self.assertEqual(stats["cancelled"], 1)

    def test_open_means_not_finished(self):
        """draft + pending + approved: everything still needing someone."""
        stats = self.client.get(reverse("dashboard")).context["stats"]
        self.assertEqual(stats["open"], 4)

    def test_all_counts_come_from_one_query(self):
        """Conditional aggregation, not a query per status.

        Fails if someone replaces the aggregate with per-status .count() calls.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("dashboard"))

        aggregates = [
            q for q in ctx.captured_queries
            if "COUNT" in q["sql"].upper() and "FROM" in q["sql"].upper()
        ]
        self.assertEqual(len(aggregates), 1, "expected a single aggregate query")


class AwaitingApprovalTests(AppTestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user()
        self.client.force_login(self.user)

    def test_panel_shows_pending_requests_nominated_to_me(self):
        mine = make_request(
            requested_by=self.other,
            approver=self.user,
            status=AccessRequest.Status.PENDING,
        )
        response = self.client.get(reverse("dashboard"))
        self.assertIn(mine, response.context["awaiting"])

    def test_panel_excludes_requests_nominated_to_someone_else(self):
        make_request(
            requested_by=self.other,
            approver=self.other,
            status=AccessRequest.Status.PENDING,
        )
        self.assertEqual(len(self.client.get(reverse("dashboard")).context["awaiting"]), 0)

    def test_panel_excludes_my_own_requests(self):
        """Mirrors the self-approval guard: listing it would be a dead end."""
        make_request(
            requested_by=self.user,
            approver=self.user,
            status=AccessRequest.Status.PENDING,
        )
        self.assertEqual(len(self.client.get(reverse("dashboard")).context["awaiting"]), 0)

    def test_panel_excludes_already_decided_requests(self):
        make_request(
            requested_by=self.other,
            approver=self.user,
            status=AccessRequest.Status.APPROVED,
        )
        self.assertEqual(len(self.client.get(reverse("dashboard")).context["awaiting"]), 0)

    def test_my_open_requests_panel_lists_only_my_unfinished_ones(self):
        open_one = make_request(
            requested_by=self.user, status=AccessRequest.Status.DRAFT
        )
        make_request(requested_by=self.user, status=AccessRequest.Status.COMPLETED)
        make_request(requested_by=self.other, status=AccessRequest.Status.DRAFT)

        mine = self.client.get(reverse("dashboard")).context["mine"]
        self.assertEqual(list(mine), [open_one])
