"""
Seed reference and demonstration data.

A management command rather than a data migration: a data migration would
re-run this against production on every deploy, and fixtures need fixed primary
keys that collide on re-seed. This is idempotent — get_or_create means running
it twice changes nothing — so it is safe to re-run and is what M9's reset_demo
will call.

All data here is synthetic: invented names and example.com addresses only.
"""

import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tracker.models import AccessRequest, Employee, System

User = get_user_model()

# The systems access can be requested against, spread across every category so
# the list and detail views have something varied to render.
SYSTEMS = [
    ("CRM Platform", System.Category.BUSINESS_APP),
    ("ERP System", System.Category.BUSINESS_APP),
    ("Helpdesk Portal", System.Category.BUSINESS_APP),
    ("HR Self-Service", System.Category.BUSINESS_APP),
    ("VPN Gateway", System.Category.INFRASTRUCTURE),
    ("Production Servers (SSH)", System.Category.INFRASTRUCTURE),
    ("Backup Console", System.Category.INFRASTRUCTURE),
    ("Email and Calendar", System.Category.COLLABORATION),
    ("Document Store", System.Category.COLLABORATION),
    ("Chat Workspace", System.Category.COLLABORATION),
    ("Payroll System", System.Category.FINANCE),
    ("Expense Portal", System.Category.FINANCE),
    ("Banking Portal", System.Category.FINANCE),
    ("Identity Provider", System.Category.SECURITY),
    ("SIEM Console", System.Category.SECURITY),
    ("Password Vault", System.Category.SECURITY),
    # Retired, but kept for the historic requests that reference it. Exercises
    # the is_active filter in the wizard's system picker.
    ("Legacy Timesheets", System.Category.BUSINESS_APP, False),
]

# (first, last, department, job title, months since start, status)
EMPLOYEES = [
    ("Amara", "Okonkwo", "Finance", "Financial Analyst", 14, Employee.Status.ACTIVE),
    ("Bram", "Visser", "Engineering", "Backend Engineer", 26, Employee.Status.ACTIVE),
    ("Carla", "Mendes", "People", "HR Business Partner", 8, Employee.Status.ACTIVE),
    ("Dmitri", "Volkov", "Engineering", "Platform Engineer", 3, Employee.Status.ACTIVE),
    ("Eleni", "Papadakis", "Sales", "Account Executive", 19, Employee.Status.ACTIVE),
    ("Farid", "Haddad", "IT Operations", "Service Desk Analyst", 5, Employee.Status.ACTIVE),
    ("Greta", "Lindqvist", "Legal", "Contracts Counsel", 31, Employee.Status.ACTIVE),
    ("Hugo", "Barrett", "Engineering", "QA Engineer", 11, Employee.Status.ON_NOTICE),
    ("Ines", "Ferreira", "Marketing", "Content Lead", 22, Employee.Status.ACTIVE),
    ("Jonas", "Weber", "Finance", "Accounts Payable Clerk", 7, Employee.Status.ACTIVE),
    ("Kiona", "Whitefeather", "Security", "Security Analyst", 16, Employee.Status.ACTIVE),
    ("Liang", "Chen", "Engineering", "Data Engineer", 1, Employee.Status.ACTIVE),
    ("Marta", "Nowak", "Sales", "Sales Development Rep", 28, Employee.Status.LEFT),
    ("Nikolai", "Petrov", "IT Operations", "Systems Administrator", 40, Employee.Status.LEFT),
]

# (employee index, request type, status, systems, days ago, notes)
# Deliberately covers every status in the lifecycle and every request type, so
# the list view, status filters and dashboard counts all have real data.
REQUESTS = [
    (11, "joiner", AccessRequest.Status.PENDING,
     ["Email and Calendar", "Chat Workspace", "Document Store", "VPN Gateway"], 2,
     "New starter in Engineering. Standard onboarding bundle."),
    (3, "joiner", AccessRequest.Status.APPROVED,
     ["Email and Calendar", "VPN Gateway", "Production Servers (SSH)", "Password Vault"], 21,
     "Platform engineer. Production access approved by team lead."),
    (5, "joiner", AccessRequest.Status.COMPLETED,
     ["Email and Calendar", "Helpdesk Portal", "Chat Workspace"], 45,
     "Service desk onboarding. Provisioned by IT on the same day."),
    (2, "joiner", AccessRequest.Status.COMPLETED,
     ["Email and Calendar", "HR Self-Service", "Document Store"], 60,
     "HR business partner onboarding."),
    (9, "joiner", AccessRequest.Status.REJECTED,
     ["Payroll System", "Expense Portal", "Banking Portal"], 30,
     "Payroll access declined — not required for accounts payable duties."),
    (0, "mover", AccessRequest.Status.APPROVED,
     ["ERP System", "Expense Portal"], 12,
     "Moving from Accounts Payable into Financial Analysis."),
    (4, "mover", AccessRequest.Status.PENDING,
     ["CRM Platform", "ERP System"], 4,
     "Promotion to senior account executive; needs forecasting access."),
    (10, "mover", AccessRequest.Status.COMPLETED,
     ["SIEM Console", "Password Vault", "Identity Provider"], 75,
     "Moved into the security operations rota."),
    (8, "mover", AccessRequest.Status.DRAFT,
     ["Document Store"], 1,
     "Draft — awaiting confirmation of new reporting line."),
    (12, "leaver", AccessRequest.Status.COMPLETED,
     ["Email and Calendar", "CRM Platform", "Chat Workspace", "VPN Gateway"], 90,
     "Resignation. All access revoked on last working day."),
    (13, "leaver", AccessRequest.Status.COMPLETED,
     ["Email and Calendar", "Production Servers (SSH)", "VPN Gateway",
      "Backup Console", "Password Vault", "Legacy Timesheets"], 120,
     "Retirement. Privileged access revoked ahead of final day."),
    (7, "leaver", AccessRequest.Status.PENDING,
     ["Email and Calendar", "Document Store", "Chat Workspace"], 3,
     "Serving notice. Revocation scheduled for end of month."),
    (6, "mover", AccessRequest.Status.CANCELLED,
     ["ERP System"], 18,
     "Withdrawn — the reorganisation was postponed."),
    (1, "mover", AccessRequest.Status.DRAFT,
     ["SIEM Console", "Production Servers (SSH)"], 6,
     "Draft raised ahead of the on-call rota change."),
]

DECIDED = {
    AccessRequest.Status.APPROVED,
    AccessRequest.Status.REJECTED,
    AccessRequest.Status.COMPLETED,
}


class Command(BaseCommand):
    help = "Seed synthetic reference and demonstration data. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing requests, employees and systems before seeding.",
        )
        parser.add_argument(
            "--requester",
            default="requester.demo",
            help="Username to record as requested_by (created if absent).",
        )
        parser.add_argument(
            "--approver",
            default="approver.demo",
            help="Username to record as approver (created if absent).",
        )

    def _say(self, message, style=None):
        """Respect --verbosity.

        Management commands are called programmatically as well as typed, and
        a command that prints unconditionally makes its caller's output - or a
        test run - unreadable.
        """
        if self.verbosity >= 1:
            self.stdout.write(style(message) if style else message)

    @transaction.atomic
    def handle(self, *args, **options):
        self.verbosity = options["verbosity"]

        if options["clear"]:
            self._clear()

        requester = self._get_actor(options["requester"])
        approver = self._get_actor(options["approver"])

        systems = self._seed_systems()
        employees = self._seed_employees()
        created = self._seed_requests(systems, employees, requester, approver)

        self._say(
            f"Seeded: {System.objects.count()} systems, "
            f"{Employee.objects.count()} employees, "
            f"{AccessRequest.objects.count()} requests "
            f"({created} created this run).",
            style=self.style.SUCCESS,
        )

    def _clear(self):
        # Requests first: employees are PROTECTed by them, so the reverse order
        # would raise ProtectedError.
        counts = (
            AccessRequest.objects.count(),
            Employee.objects.count(),
            System.objects.count(),
        )
        AccessRequest.objects.all().delete()
        Employee.objects.all().delete()
        System.objects.all().delete()
        self._say(
            f"Cleared {counts[0]} requests, {counts[1]} employees, {counts[2]} systems."
        )

    def _get_actor(self, username):
        """Fetch or create a seed actor, and sync its password to config.

        These two accounts exist so seeded requests have a requester and an
        approver who are different people — the no-self-approval guard depends
        on that. They are also the published demo logins.

        The password comes from settings.DEMO_PASSWORD, never from this file:
        the credential is published deliberately in the README, but a working
        password committed to a tracked .py file would be published by
        accident. Unset (the default everywhere but the demo host) leaves the
        accounts with unusable passwords, so a fresh clone cannot be logged
        into until someone opts in.
        """
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@example.com", "is_staff": False},
        )

        # Re-applied on every run, not only on creation, so rotating
        # DEMO_PASSWORD and re-seeding is all it takes to change the demo
        # logins — and so an existing inert account picks the password up.
        if settings.DEMO_PASSWORD:
            user.set_password(settings.DEMO_PASSWORD)
            state = "password set from DEMO_PASSWORD"
        else:
            user.set_unusable_password()
            state = "no usable password (DEMO_PASSWORD unset)"
        user.save(update_fields=["password"])

        self._say(f"{'Created' if created else 'Updated'} {username} — {state}.")
        return user

    def _seed_systems(self):
        systems = {}
        for entry in SYSTEMS:
            name, category = entry[0], entry[1]
            is_active = entry[2] if len(entry) > 2 else True
            obj, _ = System.objects.get_or_create(
                name=name,
                defaults={"category": category, "is_active": is_active},
            )
            systems[name] = obj
        return systems

    def _seed_employees(self):
        today = timezone.localdate()
        employees = []
        for first, last, dept, title, months_ago, status in EMPLOYEES:
            email = f"{first.lower()}.{last.lower()}@example.com"
            obj, _ = Employee.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "department": dept,
                    "job_title": title,
                    # Approximate months as 30 days: exact dates carry no
                    # meaning in synthetic data, only relative age does.
                    "start_date": today - datetime.timedelta(days=months_ago * 30),
                    "status": status,
                },
            )
            employees.append(obj)
        return employees

    def _seed_requests(self, systems, employees, requester, approver):
        today = timezone.localdate()
        created_count = 0

        for emp_idx, req_type, status, system_names, days_ago, notes in REQUESTS:
            employee = employees[emp_idx]
            requested_date = today - datetime.timedelta(days=days_ago)

            # No natural key on AccessRequest, so identity for idempotency is
            # the employee + type + date the request was raised on.
            existing = AccessRequest.objects.filter(
                employee=employee,
                request_type=req_type,
                requested_date=requested_date,
            ).first()
            if existing:
                continue

            request = AccessRequest(
                employee=employee,
                request_type=req_type,
                requested_date=requested_date,
                status=status,
                requested_by=requester,
                notes=notes,
            )
            # An approver is nominated as soon as a request leaves draft, not
            # only once it is decided. The dashboard's "awaiting my approval"
            # panel filters pending requests by approver, so a pending request
            # with no approver would be invisible to the very person who has
            # to act on it. Drafts have none yet — nominating one is what the
            # submit step requires.
            if status != AccessRequest.Status.DRAFT:
                request.approver = approver

            if status in DECIDED:
                # A decision additionally stamps when it was taken.
                request.decided_at = timezone.now() - datetime.timedelta(
                    days=max(days_ago - 1, 0)
                )
            request.save()

            resolved = [systems[n] for n in system_names if n in systems]
            missing = [n for n in system_names if n not in systems]
            if missing:
                self.stderr.write(
                    self.style.WARNING(
                        f"Unknown system(s) skipped for {employee}: {', '.join(missing)}"
                    )
                )
            request.systems.set(resolved)
            created_count += 1

        return created_count
