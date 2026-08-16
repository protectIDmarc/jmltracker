"""
Reset the public demo to its seeded state.

The demo logins are published in the README, so anyone can create, edit and
withdraw requests. Without a periodic reset the data drifts from "a realistic
spread of access requests" to whatever visitors last left behind, and the
dashboard stops demonstrating anything.

This deletes every request, employee and system and re-seeds. It is destructive
by design, which is why it refuses to run anywhere that is not flagged as a
demo.
"""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from tracker.models import AccessRequest, Employee, System


class Command(BaseCommand):
    help = (
        "Wipe and re-seed the demo data. Refuses to run unless DEMO_MODE is on."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Run even when DEMO_MODE is off. For tests and local use only "
                "— this deletes all tracker data."
            ),
        )

    def handle(self, *args, **options):
        # The whole safety of a scheduled destructive command rests here. On a
        # real deployment DEMO_MODE is false, so a stray cron entry or a
        # copy-pasted command deletes nothing. Guarding on the setting rather
        # than on a hostname means it travels correctly to any environment.
        if not settings.DEMO_MODE and not options["force"]:
            raise CommandError(
                "DEMO_MODE is off, so this is not a demo deployment and this "
                "command would destroy real data. Use --force only if you are "
                "certain."
            )

        before = (
            AccessRequest.objects.count(),
            Employee.objects.count(),
            System.objects.count(),
        )

        # Delegates rather than reimplements: seed_data already knows the
        # deletion order that PROTECT requires and holds the synthetic data.
        # Two copies of that would drift.
        call_command("seed_data", clear=True, verbosity=0)

        after = (
            AccessRequest.objects.count(),
            Employee.objects.count(),
            System.objects.count(),
        )

        self.stdout.write(self.style.SUCCESS(
            f"Demo reset: {before[0]}→{after[0]} requests, "
            f"{before[1]}→{after[1]} employees, "
            f"{before[2]}→{after[2]} systems."
        ))
