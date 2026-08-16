"""Create, edit, submit and withdraw — and who is allowed to do them."""

import datetime

from django.test import TestCase
from django.urls import reverse

from tracker.models import AccessRequest

from .factories import make_employee, make_request, make_system, make_user


class CreateTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.employee = make_employee()
        self.system = make_system()

    def _payload(self, **overrides):
        payload = {
            "employee": self.employee.pk,
            "request_type": "joiner",
            "requested_date": "2026-08-01",
            "systems": [self.system.pk],
            "notes": "Because access is needed.",
        }
        payload.update(overrides)
        return payload

    def test_create_saves_a_draft(self):
        response = self.client.post(reverse("request_create"), self._payload())
        request = AccessRequest.objects.get()
        self.assertRedirects(response, reverse("request_detail", args=[request.pk]))
        self.assertEqual(request.status, AccessRequest.Status.DRAFT)

    def test_requested_by_comes_from_the_session_not_the_post_data(self):
        """Fails if the view ever trusts submitted data for ownership."""
        impostor = make_user()
        self.client.post(
            reverse("request_create"),
            self._payload(requested_by=impostor.pk),
        )
        request = AccessRequest.objects.get()
        self.assertEqual(request.requested_by, self.user)

    def test_status_cannot_be_set_through_the_form(self):
        """Status moves only through defined actions, never a form field."""
        self.client.post(
            reverse("request_create"),
            self._payload(status=AccessRequest.Status.APPROVED),
        )
        self.assertEqual(AccessRequest.objects.get().status,
                         AccessRequest.Status.DRAFT)

    def test_a_request_must_name_at_least_one_system(self):
        response = self.client.post(
            reverse("request_create"), self._payload(systems=[])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("systems", response.context["form"].errors)
        self.assertFalse(AccessRequest.objects.exists())

    def test_retired_systems_are_not_offered(self):
        retired = make_system(name="Retired thing", is_active=False)
        response = self.client.get(reverse("request_create"))
        offered = response.context["form"].fields["systems"].queryset
        self.assertNotIn(retired, offered)

    def test_a_user_cannot_nominate_themselves_as_approver(self):
        response = self.client.get(reverse("request_create"))
        offered = response.context["form"].fields["approver"].queryset
        self.assertNotIn(self.user, offered)


class EditPermissionTests(TestCase):
    """Own drafts and pending only — the M4 write guard."""

    def setUp(self):
        self.owner = make_user()
        self.stranger = make_user()
        self.request = make_request(requested_by=self.owner)

    def test_owner_can_edit_a_draft(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("request_edit", args=[self.request.pk]))
        self.assertEqual(response.status_code, 200)

    def test_a_stranger_cannot_edit(self):
        """Fails if the ownership half of the guard is removed."""
        self.client.force_login(self.stranger)
        response = self.client.get(reverse("request_edit", args=[self.request.pk]))
        self.assertEqual(response.status_code, 403)

    def test_a_decided_request_cannot_be_edited_even_by_its_author(self):
        """Fails if the status half of the guard is removed."""
        self.request.status = AccessRequest.Status.APPROVED
        self.request.save()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("request_edit", args=[self.request.pk]))
        self.assertEqual(response.status_code, 403)

    def test_a_stranger_cannot_withdraw(self):
        self.client.force_login(self.stranger)
        response = self.client.post(
            reverse("request_withdraw", args=[self.request.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, AccessRequest.Status.DRAFT)


class WithdrawTests(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.client.force_login(self.owner)
        self.request = make_request(requested_by=self.owner)

    def test_withdraw_cancels_without_deleting_the_row(self):
        """The record is the audit evidence; withdrawing must not destroy it."""
        before = AccessRequest.objects.count()
        self.client.post(reverse("request_withdraw", args=[self.request.pk]))
        self.request.refresh_from_db()

        self.assertEqual(self.request.status, AccessRequest.Status.CANCELLED)
        self.assertEqual(AccessRequest.objects.count(), before)

    def test_get_on_withdraw_changes_nothing(self):
        """State changes are POST-only; a GET only renders the confirmation."""
        response = self.client.get(reverse("request_withdraw", args=[self.request.pk]))
        self.request.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.request.status, AccessRequest.Status.DRAFT)


class SubmitTests(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.approver = make_user()
        self.client.force_login(self.owner)

    def test_submitting_a_draft_makes_it_pending(self):
        request = make_request(requested_by=self.owner, approver=self.approver)
        self.client.post(reverse("request_submit", args=[request.pk]))
        request.refresh_from_db()
        self.assertEqual(request.status, AccessRequest.Status.PENDING)

    def test_a_draft_without_an_approver_cannot_be_submitted(self):
        """A pending request with no approver is invisible to whoever must act."""
        request = make_request(requested_by=self.owner, approver=None)
        response = self.client.post(reverse("request_submit", args=[request.pk]))
        request.refresh_from_db()

        self.assertRedirects(response, reverse("request_edit", args=[request.pk]))
        self.assertEqual(request.status, AccessRequest.Status.DRAFT)

    def test_get_on_submit_changes_nothing(self):
        request = make_request(requested_by=self.owner, approver=self.approver)
        self.client.get(reverse("request_submit", args=[request.pk]))
        request.refresh_from_db()
        self.assertEqual(request.status, AccessRequest.Status.DRAFT)


class RetiredSystemTests(TestCase):
    def test_editing_keeps_a_retired_system_that_is_already_referenced(self):
        """Excluding it would silently drop it on save and rewrite history."""
        owner = make_user()
        retired = make_system(name="Legacy thing", is_active=False)
        request = make_request(requested_by=owner, systems=[retired])

        self.client.force_login(owner)
        response = self.client.get(reverse("request_edit", args=[request.pk]))
        offered = response.context["form"].fields["systems"].queryset
        self.assertIn(retired, offered)
