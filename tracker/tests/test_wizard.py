"""
The joiner wizard: step guards, preserved answers, and the atomic commit.

The commit test is the one that matters — "both rows or neither" is a claim
about failure, so it has to be tested by making it fail.
"""

from unittest import mock

from django.urls import reverse

from tracker.models import AccessRequest, Employee

from .base import AppTestCase
from .factories import make_employee, make_system, make_user

NEW_EMPLOYEE = {
    "mode": "new",
    "first_name": "Wanda",
    "last_name": "Newstarter",
    "email": "wanda.newstarter@example.com",
    "department": "Finance",
    "job_title": "Analyst",
    "start_date": "2026-09-01",
}


class WizardFlowTests(AppTestCase):
    def setUp(self):
        self.user = make_user()
        self.approver = make_user()
        self.client.force_login(self.user)
        self.employee = make_employee()
        self.system = make_system()

    # --- helpers ---

    def _step1_existing(self):
        return self.client.post(
            reverse("wizard_employee"),
            {"mode": "existing", "employee": self.employee.pk},
        )

    def _step2(self, request_type="joiner"):
        return self.client.post(
            reverse("wizard_details"),
            {"request_type": request_type, "requested_date": "2026-08-01"},
        )

    def _step3(self):
        return self.client.post(
            reverse("wizard_systems"), {"systems": [self.system.pk]}
        )

    def _step4(self):
        return self.client.post(
            reverse("wizard_review"),
            {"approver": self.approver.pk, "notes": "Needed for onboarding."},
        )

    # --- step guards ---

    def test_later_steps_redirect_to_the_first_unanswered_one(self):
        self.client.get(reverse("wizard_start"))
        for step in ["wizard_details", "wizard_systems", "wizard_review"]:
            with self.subTest(step=step):
                response = self.client.get(reverse(step))
                self.assertRedirects(response, reverse("wizard_employee"))

    def test_step_three_redirects_back_when_only_step_one_is_done(self):
        self.client.get(reverse("wizard_start"))
        self._step1_existing()
        response = self.client.get(reverse("wizard_review"))
        self.assertRedirects(response, reverse("wizard_details"))

    # --- nothing is written until the end ---

    def test_no_rows_are_written_before_the_final_confirm(self):
        before = (Employee.objects.count(), AccessRequest.objects.count())
        self.client.get(reverse("wizard_start"))
        self.client.post(reverse("wizard_employee"), NEW_EMPLOYEE)
        self._step2()
        self._step3()
        self.assertEqual(
            (Employee.objects.count(), AccessRequest.objects.count()), before
        )

    def test_an_abandoned_wizard_leaves_nothing_behind(self):
        before = (Employee.objects.count(), AccessRequest.objects.count())
        self.client.get(reverse("wizard_start"))
        self.client.post(reverse("wizard_employee"), NEW_EMPLOYEE)
        self._step2()
        self._step3()
        self.client.get(reverse("wizard_cancel"))
        self.assertEqual(
            (Employee.objects.count(), AccessRequest.objects.count()), before
        )

    # --- back navigation ---

    def test_going_back_preserves_earlier_answers(self):
        self.client.get(reverse("wizard_start"))
        self._step1_existing()
        self._step2(request_type="leaver")
        self._step3()

        step2 = self.client.get(reverse("wizard_details"))
        self.assertEqual(step2.context["form"].initial["request_type"], "leaver")

        step1 = self.client.get(reverse("wizard_employee"))
        self.assertEqual(step1.context["form"].initial["employee"], self.employee.pk)

        step3 = self.client.get(reverse("wizard_systems"))
        self.assertEqual(step3.context["form"].initial["systems"], [self.system.pk])

    # --- step three wording ---

    def test_the_systems_label_follows_the_request_type(self):
        expected = {
            "joiner": "Systems to grant",
            "leaver": "Systems to revoke",
            "mover": "Systems affected",
        }
        for request_type, label in expected.items():
            with self.subTest(request_type=request_type):
                self.client.get(reverse("wizard_start"))
                self._step1_existing()
                self._step2(request_type=request_type)
                response = self.client.get(reverse("wizard_systems"))
                self.assertEqual(
                    response.context["form"].fields["systems"].label, label
                )

    # --- the commit ---

    def test_confirming_creates_a_pending_request(self):
        self.client.get(reverse("wizard_start"))
        self._step1_existing()
        self._step2()
        self._step3()
        self._step4()

        request = AccessRequest.objects.get()
        self.assertEqual(request.status, AccessRequest.Status.PENDING)
        self.assertEqual(request.requested_by, self.user)
        self.assertEqual(request.approver, self.approver)
        self.assertEqual(list(request.systems.all()), [self.system])

    def test_confirming_creates_the_new_employee_and_the_request_together(self):
        self.client.get(reverse("wizard_start"))
        self.client.post(reverse("wizard_employee"), NEW_EMPLOYEE)
        self._step2()
        self._step3()
        self._step4()

        employee = Employee.objects.get(email=NEW_EMPLOYEE["email"])
        request = AccessRequest.objects.get()
        self.assertEqual(request.employee, employee)

    def test_the_session_is_cleared_after_a_successful_commit(self):
        self.client.get(reverse("wizard_start"))
        self._step1_existing()
        self._step2()
        self._step3()
        self._step4()
        self.assertNotIn("joiner_wizard", self.client.session)

    def test_a_failure_rolls_back_the_employee_too(self):
        """Both rows commit or neither.

        The employee is created first, so a failure creating the request must
        take the employee with it — a person with no request is a half-record
        nobody asked for.
        """
        self.client.get(reverse("wizard_start"))
        self.client.post(reverse("wizard_employee"), NEW_EMPLOYEE)
        self._step2()
        self._step3()

        with mock.patch.object(
            AccessRequest.objects, "create", side_effect=ValueError("boom")
        ):
            self._step4()

        self.assertFalse(
            Employee.objects.filter(email=NEW_EMPLOYEE["email"]).exists()
        )
        self.assertFalse(AccessRequest.objects.exists())

    # --- validation ---

    def test_a_duplicate_email_is_caught_at_step_one(self):
        """Not at the commit, four steps later, as an IntegrityError."""
        make_employee(email=NEW_EMPLOYEE["email"])
        self.client.get(reverse("wizard_start"))
        response = self.client.post(reverse("wizard_employee"), NEW_EMPLOYEE)

        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)

    def test_choosing_existing_without_picking_anyone_is_refused(self):
        self.client.get(reverse("wizard_start"))
        response = self.client.post(reverse("wizard_employee"), {"mode": "existing"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("employee", response.context["form"].errors)

    def test_a_new_employee_needs_every_field(self):
        self.client.get(reverse("wizard_start"))
        response = self.client.post(
            reverse("wizard_employee"), {"mode": "new", "first_name": "Only"}
        )
        self.assertEqual(response.status_code, 200)
        for field in ["last_name", "email", "department", "job_title", "start_date"]:
            self.assertIn(field, response.context["form"].errors)

    def test_the_user_cannot_nominate_themselves_at_the_review_step(self):
        self.client.get(reverse("wizard_start"))
        self._step1_existing()
        self._step2()
        self._step3()
        response = self.client.get(reverse("wizard_review"))
        offered = response.context["form"].fields["approver"].queryset
        self.assertNotIn(self.user, offered)

    def test_a_system_removed_mid_wizard_sends_the_user_back(self):
        """The session is re-checked at commit, not trusted blindly."""
        self.client.get(reverse("wizard_start"))
        self._step1_existing()
        self._step2()
        self._step3()

        self.system.delete()
        response = self._step4()

        self.assertRedirects(response, reverse("wizard_systems"))
        self.assertFalse(AccessRequest.objects.exists())
