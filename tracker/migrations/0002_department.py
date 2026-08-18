"""Add the Department lookup table and a nullable link from Employee.

Split across three migrations on purpose: this one creates the table and adds
the foreign key as nullable, 0003 copies the existing free-text values into it,
and 0004 drops the old column and makes the key required. Doing it in one step
would either lose every recorded department or fail on the not-null constraint.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name="ID",
                )),
                ("name", models.CharField(max_length=100, unique=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="employee",
            name="department_ref",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="employees",
                to="tracker.department",
            ),
        ),
    ]
