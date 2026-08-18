"""Copy the free-text departments into the new table.

Runs against historical model state, not the current classes, so it keeps
working after the models move on.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    Department = apps.get_model("tracker", "Department")
    Employee = apps.get_model("tracker", "Employee")

    for employee in Employee.objects.all():
        # An empty department was never valid, but a migration that crashes on
        # unexpected data is worse than one that parks it somewhere visible.
        name = (employee.department or "").strip() or "Unassigned"
        department, _ = Department.objects.get_or_create(name=name)
        employee.department_ref = department
        employee.save(update_fields=["department_ref"])


def backwards(apps, schema_editor):
    Employee = apps.get_model("tracker", "Employee")

    for employee in Employee.objects.select_related("department_ref"):
        employee.department = (
            employee.department_ref.name if employee.department_ref else ""
        )
        employee.save(update_fields=["department"])


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0002_department"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
