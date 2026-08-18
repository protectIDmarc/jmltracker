"""Drop the old text column and make the department link required."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0003_populate_departments"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="employee",
            name="department",
        ),
        migrations.RenameField(
            model_name="employee",
            old_name="department_ref",
            new_name="department",
        ),
        migrations.AlterField(
            model_name="employee",
            name="department",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="employees",
                to="tracker.department",
            ),
        ),
    ]
