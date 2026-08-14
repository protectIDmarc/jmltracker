from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AccessRequestForm
from .models import AccessRequest

# How many requests appear on one page of the list.
PAGE_SIZE = 10

# A request can still be changed by its author while it is a draft or is
# waiting for a decision. Once decided or cancelled it is history, and history
# is not edited.
EDITABLE_STATUSES = {AccessRequest.Status.DRAFT, AccessRequest.Status.PENDING}


def _may_modify(user, access_request):
    """Own drafts and pending only.

    Two conditions, both required: you raised it, and it has not been decided.
    Checked in the view layer on every write path rather than trusted from the
    template, because hiding a button is not access control.
    """
    return (
        access_request.requested_by_id == user.pk
        and access_request.status in EDITABLE_STATUSES
    )


def _get_modifiable(user, pk):
    """Fetch a request the user is allowed to change, or refuse.

    Not-yours is a 403. Already-decided is also a 403 rather than a 404: the
    record exists and the user may read it, they simply cannot change it.
    """
    access_request = get_object_or_404(AccessRequest, pk=pk)
    if not _may_modify(user, access_request):
        raise PermissionDenied(
            "You can only change your own requests, and only before a decision."
        )
    return access_request


@login_required
def home(request):
    """Landing slot.

    Redirects to the request list for now. M6 replaces the body of this view
    with the dashboard; keeping the route here means no URL has to move then.
    """
    return redirect("request_list")


@login_required
def request_list(request):
    """Paginated list of every access request.

    select_related/prefetch_related matter here: without them the template's
    per-row access to employee and systems would fire two extra queries per
    row, so a ten-row page would cost twenty-one queries instead of three.
    """
    queryset = (
        AccessRequest.objects
        .select_related("employee", "approver")
        .prefetch_related("systems")
    )

    paginator = Paginator(queryset, PAGE_SIZE)
    page_number = request.GET.get("page")
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        # No ?page= at all, or a non-numeric one — start at the beginning.
        page_obj = paginator.page(1)
    except EmptyPage:
        # ?page=999 on a three-page list. Showing the last page is friendlier
        # than a 404 and stops a stale bookmark from breaking.
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "page_obj": page_obj,
        "total_count": paginator.count,
    }
    return render(request, "tracker/request_list.html", context)


@login_required
def request_detail(request, pk):
    """One access request in full — the audit record for that decision."""
    access_request = get_object_or_404(
        AccessRequest.objects.select_related(
            "employee", "requested_by", "approver"
        ).prefetch_related("systems"),
        pk=pk,
    )
    return render(
        request,
        "tracker/request_detail.html",
        {
            "access_request": access_request,
            "may_modify": _may_modify(request.user, access_request),
        },
    )


@login_required
def request_create(request):
    """Create a request through the plain ModelForm path.

    Saves as a draft. The wizard is the route that commits straight to
    pending; this path exists so a request can be captured and finished later.
    """
    if request.method == "POST":
        form = AccessRequestForm(request.POST, user=request.user)
        if form.is_valid():
            access_request = form.save(commit=False)
            # Taken from the session, never from the submitted data.
            access_request.requested_by = request.user
            access_request.status = AccessRequest.Status.DRAFT
            access_request.save()
            form.save_m2m()
            messages.success(request, "Draft request created.")
            return redirect("request_detail", pk=access_request.pk)
    else:
        form = AccessRequestForm(user=request.user)

    return render(request, "tracker/request_form.html", {
        "form": form,
        "heading": "New access request",
        "submit_label": "Save draft",
    })


@login_required
def request_edit(request, pk):
    """Edit an existing request — own drafts and pending only."""
    access_request = _get_modifiable(request.user, pk)

    if request.method == "POST":
        form = AccessRequestForm(
            request.POST, instance=access_request, user=request.user
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Request updated.")
            return redirect("request_detail", pk=access_request.pk)
    else:
        form = AccessRequestForm(instance=access_request, user=request.user)

    return render(request, "tracker/request_form.html", {
        "form": form,
        "access_request": access_request,
        "heading": "Edit request",
        "submit_label": "Save changes",
    })


@login_required
def request_submit(request, pk):
    """Move a draft to pending, putting it in front of the approver."""
    access_request = _get_modifiable(request.user, pk)

    if access_request.status != AccessRequest.Status.DRAFT:
        messages.info(request, "That request has already been submitted.")
        return redirect("request_detail", pk=pk)

    if request.method == "POST":
        if access_request.approver is None:
            messages.error(
                request, "Nominate an approver before submitting the request."
            )
            return redirect("request_edit", pk=pk)
        access_request.status = AccessRequest.Status.PENDING
        access_request.save(update_fields=["status", "updated_at"])
        messages.success(request, "Request submitted for approval.")
        return redirect("request_detail", pk=pk)

    return render(request, "tracker/request_confirm.html", {
        "access_request": access_request,
        "heading": "Submit for approval?",
        "body": "The approver will be able to decide it. You can still "
                "withdraw it afterwards.",
        "submit_label": "Submit",
        "action_url": "request_submit",
    })


@login_required
def request_withdraw(request, pk):
    """Withdraw a request.

    A status change to cancelled, never a row delete: the record is the audit
    evidence, and evidence that disappears when someone changes their mind is
    not evidence.
    """
    access_request = _get_modifiable(request.user, pk)

    if request.method == "POST":
        access_request.status = AccessRequest.Status.CANCELLED
        access_request.save(update_fields=["status", "updated_at"])
        messages.success(request, "Request withdrawn.")
        return redirect("request_detail", pk=pk)

    return render(request, "tracker/request_confirm.html", {
        "access_request": access_request,
        "heading": "Withdraw this request?",
        "body": "The request is marked cancelled and kept on record. Nothing "
                "is deleted, and this cannot be undone from here.",
        "submit_label": "Withdraw request",
        "action_url": "request_withdraw",
        "destructive": True,
    })
