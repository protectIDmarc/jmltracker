from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .models import AccessRequest

# How many requests appear on one page of the list.
PAGE_SIZE = 10


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
        {"access_request": access_request},
    )
