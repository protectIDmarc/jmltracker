from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import AccessRequest, System

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
