"""Departments are a curated lookup, not free text.

The point of the table is that "Finance", "finance" and "Finance Dept" cannot
all exist as separate groups, so these tests pin the two halves of that: the
database refuses duplicates and refuses to lose a department someone is
recorded against, and the wizard only ever offers the active ones.
"""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.urls import reverse

from tracker.models import Department, Employee

from .base import AppTestCase
from .factories import make_department, make_employee, make_system, make_user


class DepartmentModelTests(AppTestCase):
    def test_duplicate_name_is_rejected(self):
        Department.objects.create(name="Finance")
        with self.assertRaises(IntegrityError):
            # atomic() so the broken transaction does not poison the rest of
            # the test - Postgres refuses further queries after an error.
            with transaction.atomic():
                Department.objects.create(name="Finance")

    def test_protect_blocks_deleting_a_department_with_employees(self):
        department = make_department("Finance")
        make_employee(department=department)

        # Fails if on_delete is loosened to CASCADE or SET_NULL.
        with self.assertRaises(ProtectedError):
            department.delete()

        self.assertTrue(Department.objects.filter(pk=department.pk).exists())

    def test_an_empty_department_can_be_deleted(self):
        """PROTECT guards recorded history, it does not freeze the catalogue."""
        department = make_department("Typo Deptartment")
        department.delete()
        self.assertFalse(Department.objects.filter(pk=department.pk).exists())

    def test_deactivating_keeps_existing_employees_intact(self):
        """Retirement is a flag, not a deletion: the people stay where they are."""
        department = make_department("Print Services")
        employee = make_employee(department=department)

        department.is_active = False
        department.save(update_fields=["is_active"])

        employee.refresh_from_db()
        self.assertEqual(employee.department, department)


class DepartmentPickerTests(AppTestCase):
    """Step 1 of the wizard offers active departments and only those."""

    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.active = make_department("Engineering")
        self.retired = make_department("Print Services", is_active=False)
        self.system = make_system()

    def _payload(self, department):
        return {
            "mode": "new",
            "first_name": "Wanda",
            "last_name": "Newstarter",
            "email": "wanda.newstarter@example.com",
            "department": department.pk,
            "job_title": "Analyst",
            "start_date": "2026-09-01",
        }

    def test_retired_department_is_not_offered(self):
        response = self.client.get(reverse("wizard_employee"))
        choices = response.context["form"].fields["department"].queryset
        self.assertIn(self.active, choices)
        self.assertNotIn(self.retired, choices)

    def test_retired_department_is_refused_even_if_posted(self):
        """The queryset is the control, not the rendered options.

        Fails if the filter is moved into the template or the widget: a posted
        key for a retired department has to be rejected by validation.
        """
        response = self.client.post(
            reverse("wizard_employee"), self._payload(self.retired)
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["department"])
        self.assertFalse(
            Employee.objects.filter(email="wanda.newstarter@example.com").exists()
        )

    def test_a_new_employee_is_recorded_against_the_chosen_department(self):
        self.client.post(reverse("wizard_employee"), self._payload(self.active))
        self.client.post(reverse("wizard_details"), {
            "request_type": "joiner",
            "requested_date": "2026-09-01",
        })
        self.client.post(reverse("wizard_systems"), {"systems": [self.system.pk]})
        self.client.post(reverse("wizard_review"), {
            "approver": make_user().pk,
            "notes": "New starter.",
        })

        employee = Employee.objects.get(email="wanda.newstarter@example.com")
        self.assertEqual(employee.department, self.active)

    def test_a_department_retired_mid_wizard_stops_the_commit(self):
        """Four page loads is long enough for the catalogue to change.

        The session holds a key, so without the re-read at commit the employee
        would be created against a department nobody can choose any more.
        """
        self.client.post(reverse("wizard_employee"), self._payload(self.active))
        self.client.post(reverse("wizard_details"), {
            "request_type": "joiner",
            "requested_date": "2026-09-01",
        })
        self.client.post(reverse("wizard_systems"), {"systems": [self.system.pk]})

        self.active.is_active = False
        self.active.save(update_fields=["is_active"])

        response = self.client.post(reverse("wizard_review"), {
            "approver": make_user().pk,
            "notes": "New starter.",
        })

        self.assertRedirects(response, reverse("wizard_employee"))
        self.assertFalse(
            Employee.objects.filter(email="wanda.newstarter@example.com").exists()
        )
