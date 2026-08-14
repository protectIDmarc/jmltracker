"""
Domain model for the JML access request tracker.

Three tables: the systems access can be granted to, the people it is granted
for, and the request that ties them together. The AccessRequest row is the
audit evidence — who asked for what, when, and who approved it — so the schema
favours preserving history over tidiness.
"""

from django.conf import settings
from django.db import models


class System(models.Model):
    """An application or entitlement that access can be requested for."""

    class Category(models.TextChoices):
        BUSINESS_APP = "business_app", "Business application"
        INFRASTRUCTURE = "infrastructure", "Infrastructure"
        COLLABORATION = "collaboration", "Collaboration"
        FINANCE = "finance", "Finance"
        SECURITY = "security", "Security"

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.BUSINESS_APP,
    )
    # Retired systems are deactivated rather than deleted: historic requests
    # must keep naming the system they were actually raised against.
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Employee(models.Model):
    """The person access is being requested for."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_NOTICE = "on_notice", "On notice"
        LEFT = "left", "Left"

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    # Unique because email is the practical identity key for an employee and
    # the join key to upstream HR systems.
    email = models.EmailField(unique=True)
    department = models.CharField(max_length=100)
    job_title = models.CharField(max_length=100)
    start_date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class AccessRequest(models.Model):
    """A request to grant, change or revoke access — the audit record."""

    class RequestType(models.TextChoices):
        JOINER = "joiner", "Joiner"
        MOVER = "mover", "Mover"
        LEAVER = "leaver", "Leaver"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    # PROTECT: deleting an employee who has access history must fail loudly.
    # Losing the request record would destroy the audit trail it exists to be.
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="access_requests",
    )
    systems = models.ManyToManyField(System, related_name="access_requests")
    request_type = models.CharField(max_length=10, choices=RequestType.choices)
    requested_date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    # Both point at the user model via settings.AUTH_USER_MODEL rather than a
    # direct import, so swapping in a custom user model stays a config change.
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requests_raised",
    )
    # Null until a decision is made; PROTECT thereafter so an approver cannot
    # be deleted out from under the decisions they signed off.
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requests_approved",
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_request_type_display()} — {self.employee} ({self.get_status_display()})"
