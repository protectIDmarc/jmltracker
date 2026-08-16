"""Model-level integrity: the constraints the audit trail depends on."""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from tracker.models import AccessRequest, Employee

from .factories import make_employee, make_request, make_user


class EmployeeProtectionTests(TestCase):
    """Deleting a person with access history must fail loudly."""

    def test_protect_blocks_deleting_an_employee_with_requests(self):
        user = make_user()
        employee = make_employee()
        make_request(requested_by=user, employee=employee)

        # Fails if on_delete is loosened to CASCADE or SET_NULL.
        with self.assertRaises(ProtectedError):
            employee.delete()

        self.assertTrue(Employee.objects.filter(pk=employee.pk).exists())

    def test_an_employee_with_no_requests_can_be_deleted(self):
        """PROTECT guards history, it does not make employees undeletable."""
        employee = make_employee()
        employee.delete()
        self.assertFalse(Employee.objects.filter(pk=employee.pk).exists())

    def test_requester_is_protected_too(self):
        """A user who raised a request cannot be deleted out from under it."""
        user = make_user()
        make_request(requested_by=user)
        with self.assertRaises(ProtectedError):
            user.delete()


class EmployeeEmailTests(TestCase):
    """Email is the practical identity key, so duplicates are refused."""

    def test_duplicate_email_is_rejected(self):
        make_employee(email="taken@example.com")
        with self.assertRaises(IntegrityError):
            # atomic() so the broken transaction does not poison the rest of
            # the test - Postgres refuses further queries after an error.
            with transaction.atomic():
                make_employee(email="taken@example.com")

    def test_emails_differing_only_in_case_are_currently_allowed(self):
        """Documents actual behaviour, which is not what most people assume.

        Postgres unique indexes are case-sensitive, so Taken@ and taken@ are two
        rows. The wizard's step-1 check uses iexact and so does catch this, but
        the database itself would not. If case-insensitive identity is wanted it
        needs a functional unique index, not a plain unique=True.
        """
        make_employee(email="Person@example.com")
        make_employee(email="person@example.com")
        self.assertEqual(Employee.objects.filter(
            email__iexact="person@example.com").count(), 2)


class DefaultsTests(TestCase):
    def test_a_new_request_starts_as_a_draft(self):
        user = make_user()
        request = make_request(requested_by=user)
        self.assertEqual(request.status, AccessRequest.Status.DRAFT)

    def test_a_new_request_has_no_approver_or_decision_time(self):
        user = make_user()
        request = make_request(requested_by=user)
        self.assertIsNone(request.approver)
        self.assertIsNone(request.decided_at)
