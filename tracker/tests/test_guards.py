"""
The approval guards.

Each test here is written so that it fails if its guard is removed — that is
the point of them. A guard with no test is a guard that will quietly stop
working.
"""

from django.test import TestCase
from django.urls import reverse

from tracker.models import AccessRequest

from .factories import make_request, make_user


class SelfApprovalTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def test_a_user_cannot_approve_their_own_request(self):
        """Fails if the requested_by check is removed from request_decide."""
        request = make_request(
            requested_by=self.user,
            approver=self.user,               # nominated themselves
            status=AccessRequest.Status.PENDING,
        )
        response = self.client.post(
            reverse("request_decide", args=[request.pk]), {"decision": "approve"}
        )
        request.refresh_from_db()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(request.status, AccessRequest.Status.PENDING)
        self.assertIsNone(request.decided_at)


class NominatedApproverTests(TestCase):
    def test_only_the_nominated_approver_may_decide(self):
        """Fails if the approver check is removed.

        Without it, nominating an approver would mean nothing and the
        dashboard's awaiting panel would have no basis.
        """
        requester, nominated, bystander = make_user(), make_user(), make_user()
        request = make_request(
            requested_by=requester,
            approver=nominated,
            status=AccessRequest.Status.PENDING,
        )

        self.client.force_login(bystander)
        response = self.client.post(
            reverse("request_decide", args=[request.pk]), {"decision": "approve"}
        )
        request.refresh_from_db()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(request.status, AccessRequest.Status.PENDING)


class DoubleApprovalTests(TestCase):
    def setUp(self):
        self.requester = make_user()
        self.approver = make_user()
        self.request = make_request(
            requested_by=self.requester,
            approver=self.approver,
            status=AccessRequest.Status.PENDING,
        )
        self.client.force_login(self.approver)

    def test_a_decided_request_cannot_be_decided_again(self):
        """Fails if the status re-check is removed."""
        self.client.post(
            reverse("request_decide", args=[self.request.pk]),
            {"decision": "approve"},
        )
        self.request.refresh_from_db()
        first_decision = self.request.decided_at

        response = self.client.post(
            reverse("request_decide", args=[self.request.pk]),
            {"decision": "reject"},
        )
        self.request.refresh_from_db()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.request.status, AccessRequest.Status.APPROVED)
        self.assertEqual(self.request.decided_at, first_decision)


class DecisionStampTests(TestCase):
    """Every decision records who took it and when."""

    def setUp(self):
        self.requester = make_user()
        self.approver = make_user()
        self.client.force_login(self.approver)

    def _pending(self):
        return make_request(
            requested_by=self.requester,
            approver=self.approver,
            status=AccessRequest.Status.PENDING,
        )

    def test_approving_stamps_approver_and_decided_at(self):
        request = self._pending()
        self.client.post(
            reverse("request_decide", args=[request.pk]), {"decision": "approve"}
        )
        request.refresh_from_db()

        self.assertEqual(request.status, AccessRequest.Status.APPROVED)
        self.assertEqual(request.approver, self.approver)
        self.assertIsNotNone(request.decided_at)

    def test_rejecting_stamps_approver_and_decided_at(self):
        request = self._pending()
        self.client.post(
            reverse("request_decide", args=[request.pk]), {"decision": "reject"}
        )
        request.refresh_from_db()

        self.assertEqual(request.status, AccessRequest.Status.REJECTED)
        self.assertEqual(request.approver, self.approver)
        self.assertIsNotNone(request.decided_at)

    def test_a_get_does_not_decide_anything(self):
        request = self._pending()
        response = self.client.get(reverse("request_decide", args=[request.pk]))
        request.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.status, AccessRequest.Status.PENDING)
        self.assertIsNone(request.decided_at)

    def test_an_unrecognised_decision_value_changes_nothing(self):
        request = self._pending()
        self.client.post(
            reverse("request_decide", args=[request.pk]), {"decision": "maybe"}
        )
        request.refresh_from_db()
        self.assertEqual(request.status, AccessRequest.Status.PENDING)


class MarkCompletedTests(TestCase):
    """Completion is explicit, and only from approved."""

    def setUp(self):
        self.requester = make_user()
        self.approver = make_user()
        self.request = make_request(
            requested_by=self.requester,
            approver=self.approver,
            status=AccessRequest.Status.APPROVED,
        )

    def test_the_approver_can_mark_completed(self):
        self.client.force_login(self.approver)
        self.client.post(reverse("request_complete", args=[self.request.pk]))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, AccessRequest.Status.COMPLETED)

    def test_an_administrator_can_mark_completed(self):
        admin = make_user(is_staff=True)
        self.client.force_login(admin)
        self.client.post(reverse("request_complete", args=[self.request.pk]))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, AccessRequest.Status.COMPLETED)

    def test_the_requester_cannot_mark_completed(self):
        self.client.force_login(self.requester)
        response = self.client.post(
            reverse("request_complete", args=[self.request.pk])
        )
        self.request.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.request.status, AccessRequest.Status.APPROVED)

    def test_a_pending_request_cannot_be_completed(self):
        """Approval is a decision; provisioning is separate work."""
        self.request.status = AccessRequest.Status.PENDING
        self.request.save()
        self.client.force_login(self.approver)
        response = self.client.post(
            reverse("request_complete", args=[self.request.pk])
        )
        self.request.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.request.status, AccessRequest.Status.PENDING)

    def test_completing_twice_is_refused(self):
        self.client.force_login(self.approver)
        self.client.post(reverse("request_complete", args=[self.request.pk]))
        response = self.client.post(
            reverse("request_complete", args=[self.request.pk])
        )
        self.assertEqual(response.status_code, 403)
