from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import AccessRequestForm
from .models import AccessRequest

# How many requests appear on one page of the list.
PAGE_SIZE = 10

# A request can still be changed by its author while it is a draft or is
# waiting for a decision. Once decided or cancelled it is history, and history
# is not edited.
EDITABLE_STATUSES = {AccessRequest.Status.DRAFT, AccessRequest.Status.PENDING}

# Not finished yet: still needs someone to do something.
OPEN_STATUSES = {
    AccessRequest.Status.DRAFT,
    AccessRequest.Status.PENDING,
    AccessRequest.Status.APPROVED,
}


# --- Permission helpers ---------------------------------------------------
#
# These decide what to *render*. They are re-checked inside the transaction on
# every write path, because a page can be seconds out of date by the time its
# button is clicked.

def _may_modify(user, access_request):
    """Own drafts and pending only."""
    return (
        access_request.requested_by_id == user.pk
        and access_request.status in EDITABLE_STATUSES
    )


def _may_decide(user, access_request):
    """The nominated approver, on a pending request they did not raise."""
    return (
        access_request.status == AccessRequest.Status.PENDING
        and access_request.approver_id == user.pk
        and access_request.requested_by_id != user.pk
    )


def _may_complete(user, access_request):
    """Marking provisioning done: the approver, or an administrator.

    Completion means "IT has granted the access", which happens outside this
    system — so it is an explicit action, never an automatic consequence of
    approval.
    """
    return access_request.status == AccessRequest.Status.APPROVED and (
        access_request.approver_id == user.pk or user.is_staff
    )


def _get_modifiable(user, pk):
    """Fetch a request the user is allowed to change, or refuse."""
    access_request = get_object_or_404(AccessRequest, pk=pk)
    if not _may_modify(user, access_request):
        raise PermissionDenied(
            "You can only change your own requests, and only before a decision."
        )
    return access_request


# --- Dashboard ------------------------------------------------------------

@login_required
def dashboard(request):
    """Counts by status, plus what the signed-in user has to act on."""
    # One query for every count: conditional aggregation rather than a query
    # per status. Adding a status here costs nothing extra at runtime.
    stats = AccessRequest.objects.aggregate(
        total=Count("id"),
        draft=Count("id", filter=Q(status=AccessRequest.Status.DRAFT)),
        pending=Count("id", filter=Q(status=AccessRequest.Status.PENDING)),
        approved=Count("id", filter=Q(status=AccessRequest.Status.APPROVED)),
        completed=Count("id", filter=Q(status=AccessRequest.Status.COMPLETED)),
        rejected=Count("id", filter=Q(status=AccessRequest.Status.REJECTED)),
        cancelled=Count("id", filter=Q(status=AccessRequest.Status.CANCELLED)),
    )
    stats["open"] = stats["draft"] + stats["pending"] + stats["approved"]

    # Excluding own requests mirrors the no-self-approval guard: showing a
    # request here that the user is forbidden to decide would be a dead end.
    awaiting = (
        AccessRequest.objects
        .filter(status=AccessRequest.Status.PENDING, approver=request.user)
        .exclude(requested_by=request.user)
        .select_related("employee__department")
        .prefetch_related("systems")
    )

    mine = (
        AccessRequest.objects
        .filter(requested_by=request.user, status__in=OPEN_STATUSES)
        .select_related("employee__department", "approver")
    )

    return render(request, "tracker/dashboard.html", {
        "stats": stats,
        "awaiting": awaiting,
        "mine": mine,
    })


# --- Read paths -----------------------------------------------------------

@login_required
def request_list(request):
    """Paginated list of every access request.

    select_related/prefetch_related matter here: without them the template's
    per-row access to employee and systems would fire two extra queries per
    row, so a ten-row page would cost twenty-one queries instead of three.
    """
    queryset = (
        AccessRequest.objects
        .select_related("employee__department", "approver")
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

    return render(request, "tracker/request_list.html", {
        "page_obj": page_obj,
        "total_count": paginator.count,
    })


@login_required
def request_detail(request, pk):
    """One access request in full — the audit record for that decision."""
    access_request = get_object_or_404(
        AccessRequest.objects.select_related(
            "employee__department", "requested_by", "approver"
        ).prefetch_related("systems"),
        pk=pk,
    )
    return render(request, "tracker/request_detail.html", {
        "access_request": access_request,
        "may_modify": _may_modify(request.user, access_request),
        "may_decide": _may_decide(request.user, access_request),
        "may_complete": _may_complete(request.user, access_request),
    })


# --- Write paths ----------------------------------------------------------

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


# --- Guarded decisions ----------------------------------------------------

@login_required
def request_decide(request, pk):
    """Approve or reject — the guarded decision.

    The guards are checked twice on purpose. Once here, to decide what to
    render and to fail fast. Then again inside the transaction against a
    locked row, because that is the only check that can actually be trusted:
    between rendering the page and handling the POST, someone else — or a
    second click — may already have decided it.
    """
    access_request = get_object_or_404(
        AccessRequest.objects.select_related(
            "employee__department", "requested_by", "approver"
        ).prefetch_related("systems"),
        pk=pk,
    )

    if not _may_decide(request.user, access_request):
        raise PermissionDenied(
            "Only the nominated approver can decide this request, it must "
            "still be pending, and you cannot approve your own request."
        )

    if request.method == "POST":
        decision = request.POST.get("decision")
        if decision not in {"approve", "reject"}:
            messages.error(request, "Choose approve or reject.")
            return redirect("request_decide", pk=pk)

        with transaction.atomic():
            # select_for_update takes a row lock held until this transaction
            # ends. A concurrent decide on the same row blocks here, then
            # re-reads a status that is no longer pending and is refused.
            locked = AccessRequest.objects.select_for_update().get(pk=pk)

            if locked.status != AccessRequest.Status.PENDING:
                # The double-approval guard. This is the check that counts:
                # the one in the view above read a row that is now stale.
                messages.error(
                    request,
                    f"That request has already been "
                    f"{locked.get_status_display().lower()}.",
                )
                return redirect("request_detail", pk=pk)

            if locked.requested_by_id == request.user.pk:
                raise PermissionDenied("You cannot approve your own request.")

            if locked.approver_id != request.user.pk:
                raise PermissionDenied(
                    "Only the nominated approver can decide this request."
                )

            locked.status = (
                AccessRequest.Status.APPROVED if decision == "approve"
                else AccessRequest.Status.REJECTED
            )
            # Every decision stamps who took it and when.
            locked.approver = request.user
            locked.decided_at = timezone.now()
            locked.save(update_fields=[
                "status", "approver", "decided_at", "updated_at"
            ])

        messages.success(
            request,
            f"Request {locked.get_status_display().lower()}.",
        )
        return redirect("request_detail", pk=pk)

    return render(request, "tracker/request_decide.html", {
        "access_request": access_request,
    })


@login_required
def request_complete(request, pk):
    """Mark an approved request as provisioned.

    Never automatic: approval is a decision, provisioning is work that happens
    outside this system, and conflating them would record access as granted
    that nobody has actually granted.
    """
    access_request = get_object_or_404(
        AccessRequest.objects.select_related("employee__department", "approver"), pk=pk
    )

    if not _may_complete(request.user, access_request):
        raise PermissionDenied(
            "Only the approver or an administrator can mark an approved "
            "request as completed."
        )

    if request.method == "POST":
        with transaction.atomic():
            locked = AccessRequest.objects.select_for_update().get(pk=pk)

            if locked.status != AccessRequest.Status.APPROVED:
                messages.error(
                    request,
                    "Only an approved request can be marked completed.",
                )
                return redirect("request_detail", pk=pk)

            if not (locked.approver_id == request.user.pk or request.user.is_staff):
                raise PermissionDenied(
                    "Only the approver or an administrator can do that."
                )

            locked.status = AccessRequest.Status.COMPLETED
            locked.save(update_fields=["status", "updated_at"])

        messages.success(request, "Request marked completed.")
        return redirect("request_detail", pk=pk)

    return render(request, "tracker/request_confirm.html", {
        "access_request": access_request,
        "heading": "Mark as completed?",
        "body": "This records that IT has provisioned the access. It does not "
                "grant anything itself.",
        "submit_label": "Mark completed",
        "action_url": "request_complete",
    })
