"""
Small object builders for the tests.

Deliberately plain functions rather than a factory library: one fewer
dependency, and the whole thing is short enough to read in one sitting. Every
test builds the data it needs, so no test depends on the seed command having
been run or on another test's leftovers.
"""

import datetime
import itertools

from django.contrib.auth import get_user_model

from tracker.models import AccessRequest, Department, Employee, System

User = get_user_model()

# Employee.email and System.name are unique, so anything built in bulk needs a
# distinct value each time.
_counter = itertools.count(1)

PASSWORD = "test-pass-9x7q"


def make_user(username=None, password=None, **kwargs):
    """Create a user.

    No password by default. Django hashes with PBKDF2 at a deliberately high
    work factor, and paying that for every user in the suite dominated the
    runtime — while almost every test signs in with force_login(), which never
    checks one. Pass password=PASSWORD only in the few tests that post real
    credentials to the login view.
    """
    n = next(_counter)
    return User.objects.create_user(
        username=username or f"user{n}",
        password=password,
        **kwargs,
    )


def make_employee(**kwargs):
    n = next(_counter)
    defaults = {
        "first_name": "Test",
        "last_name": f"Person{n}",
        "email": f"person{n}@example.com",
        "department": kwargs.pop("department", None) or make_department(),
        "job_title": "Engineer",
        "start_date": datetime.date(2026, 1, 1),
    }
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


def make_department(name=None, **kwargs):
    """Departments are get_or_create'd by name: most tests want the same one,
    and a unique constraint makes a blind create fail on the second call."""
    department, _ = Department.objects.get_or_create(
        name=name or "Engineering", defaults=kwargs
    )
    return department


def make_system(name=None, **kwargs):
    n = next(_counter)
    return System.objects.create(name=name or f"System {n}", **kwargs)


def make_request(requested_by, systems=None, **kwargs):
    """Build a request. Pass status/approver explicitly when they matter."""
    defaults = {
        "employee": kwargs.pop("employee", None) or make_employee(),
        "request_type": AccessRequest.RequestType.JOINER,
        "requested_date": datetime.date(2026, 8, 1),
        "status": AccessRequest.Status.DRAFT,
        "requested_by": requested_by,
    }
    defaults.update(kwargs)
    access_request = AccessRequest.objects.create(**defaults)
    access_request.systems.set(systems or [make_system()])
    return access_request
