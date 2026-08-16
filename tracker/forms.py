from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import AccessRequest, Employee, System

User = get_user_model()


class AccessRequestForm(forms.ModelForm):
    """The plain create/edit path.

    Deliberately does not expose `status` or `decided_at`: status moves only
    through defined actions (submit, withdraw, decide), never by someone typing
    a value into a form. `requested_by` is taken from the session, not the
    request body, so it cannot be forged.
    """

    class Meta:
        model = AccessRequest
        fields = ["employee", "request_type", "requested_date", "systems",
                  "approver", "notes"]
        widgets = {
            "requested_date": forms.DateInput(attrs={"type": "date"}),
            "systems": forms.CheckboxSelectMultiple,
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "approver": "Who should decide this request. You cannot approve your own.",
            "notes": "Why the access is needed. This is part of the audit record.",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Only active systems can be picked. A request already referencing a
        # retired system keeps it, though: excluding it outright would silently
        # drop the system on the next save, rewriting history to match today's
        # catalogue.
        systems = System.objects.filter(is_active=True)
        if self.instance.pk:
            systems = System.objects.filter(
                Q(is_active=True) | Q(access_requests=self.instance)
            ).distinct()
        self.fields["systems"].queryset = systems

        # A requester cannot be their own approver. The guard that actually
        # enforces this lives in the view layer at M6 - keeping the name out of
        # the dropdown is a courtesy, not the control.
        approvers = User.objects.filter(is_active=True)
        if user is not None:
            approvers = approvers.exclude(pk=user.pk)
        self.fields["approver"].queryset = approvers.order_by("username")

        # Optional at draft stage: a request can be saved before the approver
        # is known. The wizard requires one before it commits to pending.
        self.fields["approver"].required = False
        self.fields["notes"].required = False

        # systems is required by the model, so the field's own required check
        # fires before any clean_systems() would - overriding the message here
        # is what actually reaches the user, rather than "This field is
        # required." on a field whose label gives no hint why.
        self.fields["systems"].error_messages["required"] = (
            "Select at least one system - a request that grants nothing "
            "records no intent."
        )


# --------------------------------------------------------------------------
# Wizard forms
#
# One form per step. They are plain forms rather than ModelForms because no
# step saves anything: the wizard holds every answer in the session and writes
# both rows in one transaction at the end. Each form validates its own step, so
# an invalid answer cannot be carried forward.
# --------------------------------------------------------------------------


class WizardEmployeeForm(forms.Form):
    """Step 1 — pick an existing employee, or capture a new one."""

    MODE_EXISTING = "existing"
    MODE_NEW = "new"
    MODE_CHOICES = [
        (MODE_EXISTING, "An existing employee"),
        (MODE_NEW, "Someone new"),
    ]

    mode = forms.ChoiceField(
        choices=MODE_CHOICES,
        widget=forms.RadioSelect,
        initial=MODE_EXISTING,
        label="Who is this request for?",
    )
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.all(),
        required=False,
        label="Employee",
    )

    first_name = forms.CharField(max_length=50, required=False)
    last_name = forms.CharField(max_length=50, required=False)
    email = forms.EmailField(required=False)
    department = forms.CharField(max_length=100, required=False)
    job_title = forms.CharField(max_length=100, required=False)
    start_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    # Which fields matter when capturing someone new.
    NEW_FIELDS = ["first_name", "last_name", "email", "department",
                  "job_title", "start_date"]

    def clean(self):
        """Validate whichever branch was chosen, and only that branch.

        Making the new-employee fields unconditionally required would break the
        existing-employee path, and vice versa — so both sets are optional at
        the field level and required here, conditionally.
        """
        cleaned = super().clean()
        mode = cleaned.get("mode")

        if mode == self.MODE_EXISTING:
            if not cleaned.get("employee"):
                self.add_error("employee", "Choose an employee.")
            # Discard any half-typed new-employee data so it cannot leak into
            # the session and be written later.
            for field in self.NEW_FIELDS:
                cleaned[field] = None

        elif mode == self.MODE_NEW:
            cleaned["employee"] = None
            for field in self.NEW_FIELDS:
                if not cleaned.get(field):
                    self.add_error(field, "Required for a new employee.")

            # Employee.email is unique. Catching it here gives a usable message
            # on the field instead of an IntegrityError at the final commit,
            # four steps later.
            email = cleaned.get("email")
            if email and Employee.objects.filter(email__iexact=email).exists():
                self.add_error(
                    "email",
                    "An employee with this email already exists — choose "
                    "them as an existing employee instead.",
                )

        return cleaned


class WizardTypeDateForm(forms.Form):
    """Step 2 — what kind of request, and when."""

    request_type = forms.ChoiceField(
        choices=AccessRequest.RequestType.choices,
        widget=forms.RadioSelect,
        label="Request type",
    )
    requested_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Requested date",
    )


class WizardSystemsForm(forms.Form):
    """Step 3 — which systems.

    One form, three framings: the label reflects the request type without
    changing what is recorded. A conscious simplification — the request
    captures intent, not a provisioning diff.
    """

    LABELS = {
        "joiner": "Systems to grant",
        "leaver": "Systems to revoke",
        "mover": "Systems affected",
    }

    systems = forms.ModelMultipleChoiceField(
        queryset=System.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, request_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Retired systems cannot be chosen for a new request.
        self.fields["systems"].queryset = System.objects.filter(is_active=True)
        self.fields["systems"].label = self.LABELS.get(
            request_type, "Systems affected"
        )
        self.fields["systems"].error_messages["required"] = (
            "Select at least one system - a request that grants nothing "
            "records no intent."
        )


class WizardApproverForm(forms.Form):
    """Step 4 — who decides, plus any supporting note."""

    approver = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Approver",
        help_text="Who should decide this request. You cannot approve your own.",
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
        help_text="Why the access is needed. This is part of the audit record.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        approvers = User.objects.filter(is_active=True)
        if user is not None:
            approvers = approvers.exclude(pk=user.pk)
        self.fields["approver"].queryset = approvers.order_by("username")
        # Required here, unlike the draft form: the wizard commits straight to
        # pending, and a pending request with no approver is invisible to the
        # person who has to act on it.
        self.fields["approver"].required = True
