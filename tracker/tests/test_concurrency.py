"""
The concurrency half of the double-approval guard.

The cheap check in the view body reads a row that may already be stale by the
time the POST is handled. The check that actually counts re-reads the row under
select_for_update inside the transaction. These tests cover that specifically —
the sequential double-approval test in test_guards.py is caught by the cheap
check and so proves nothing about the deep one.

TransactionTestCase, not TestCase: TestCase wraps each test in a transaction
that is rolled back, so a second connection would never see the first's writes
and the race could not happen at all.
"""

import threading
from unittest import mock

from django.db import connection
from django.test import Client

from django.urls import reverse

from tracker.models import AccessRequest

from .base import AppTransactionTestCase
from .factories import PASSWORD, make_request, make_user


class ConcurrentDecisionTests(AppTransactionTestCase):
    def setUp(self):
        self.requester = make_user("requester")
        # Real password: the threads sign in through the login view, because
        # force_login would not give each thread its own session.
        self.approver = make_user("approver", password=PASSWORD)
        self.request = make_request(
            requested_by=self.requester,
            approver=self.approver,
            status=AccessRequest.Status.PENDING,
        )

    def test_two_simultaneous_decisions_produce_exactly_one(self):
        """The invariant that must never break, whichever guard catches it."""
        barrier = threading.Barrier(2)
        responses = {}

        def decide(label, decision):
            client = Client()
            client.login(username=self.approver.username, password=PASSWORD)
            barrier.wait()          # release both threads together
            try:
                response = client.post(
                    reverse("request_decide", args=[self.request.pk]),
                    {"decision": decision},
                )
                responses[label] = response.status_code
            finally:
                # Each thread gets its own connection; leaving it open would
                # hold a lock and hang the test database teardown.
                connection.close()

        threads = [
            threading.Thread(target=decide, args=("a", "approve")),
            threading.Thread(target=decide, args=("b", "reject")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.request.refresh_from_db()

        # Exactly one decision, and it stuck.
        self.assertIn(
            self.request.status,
            {AccessRequest.Status.APPROVED, AccessRequest.Status.REJECTED},
        )
        self.assertIsNotNone(self.request.decided_at)
        self.assertEqual(self.request.approver, self.approver)
        self.assertEqual(len(responses), 2)

    def test_the_in_transaction_check_refuses_on_its_own(self):
        """Deterministic proof that the deep check is not decoration.

        The cheap pre-check is patched to wave everything through, so the only
        thing standing between the POST and a second decision is the re-read
        inside the transaction. If that re-read is removed, this test fails.
        """
        self.request.status = AccessRequest.Status.APPROVED
        self.request.save(update_fields=["status"])

        client = Client()
        client.login(username=self.approver.username, password=PASSWORD)

        with mock.patch("tracker.views._may_decide", return_value=True):
            response = client.post(
                reverse("request_decide", args=[self.request.pk]),
                {"decision": "reject"},
            )

        self.request.refresh_from_db()
        # Redirected with an error rather than 403: it got past the pre-check.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.request.status, AccessRequest.Status.APPROVED)

    def test_the_in_transaction_check_refuses_a_non_nominated_approver(self):
        """The deep half of the nominated-approver guard, in isolation.

        Added after mutation testing: removing only this check, leaving the
        render-time one intact, was caught by nothing. Every layer needs a test
        that pins it on its own, or defence in depth quietly becomes defence in
        one layer.
        """
        bystander = make_user("bystander", password=PASSWORD)
        client = Client()
        client.login(username="bystander", password=PASSWORD)

        with mock.patch("tracker.views._may_decide", return_value=True):
            response = client.post(
                reverse("request_decide", args=[self.request.pk]),
                {"decision": "approve"},
            )

        self.request.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.request.status, AccessRequest.Status.PENDING)
        self.assertIsNone(self.request.decided_at)

    def test_the_in_transaction_check_refuses_self_approval(self):
        """Same again for the self-approval half of the guard."""
        own = make_request(
            requested_by=self.approver,
            approver=self.approver,
            status=AccessRequest.Status.PENDING,
        )
        client = Client()
        client.login(username=self.approver.username, password=PASSWORD)

        with mock.patch("tracker.views._may_decide", return_value=True):
            response = client.post(
                reverse("request_decide", args=[own.pk]), {"decision": "approve"}
            )

        own.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(own.status, AccessRequest.Status.PENDING)
