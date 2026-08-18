"""
The joiner wizard — a hand-rolled, session-backed, four-step create flow.

Deliberately not django-formtools / SessionWizardView. The state machine here
is about twenty lines of dictionary handling, and owning it means the session
contract, the step guards and the final transaction are all visible in one
file rather than inherited from a base class.

The shape of the flow:

    1 employee   pick an existing person, or capture a new one
    2 details    request type + requested date
    3 systems    which systems (label adapts to the request type)
    4 review     approver, review everything, confirm

Nothing touches the database until step 4 is confirmed. An abandoned wizard
therefore leaves no rows at all — there is nothing to clean up, because
nothing was ever written.
"""

import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import (
    WizardApproverForm,
    WizardEmployeeForm,
    WizardSystemsForm,
    WizardTypeDateForm,
)
from .models import AccessRequest, Department, Employee, System

User = get_user_model()

# One key holds the whole flow. Django's session serialiser is JSON, so every
# value stored here must be JSON-safe — dates go in as ISO strings, objects as
# primary keys.
SESSION_KEY = "joiner_wizard"

TOTAL_STEPS = 4


# --- Session state --------------------------------------------------------

def _get_state(request):
    return request.session.get(SESSION_KEY, {})


def _save_state(request, state):
    # Reassigning the whole key rather than mutating in place: Django only
    # notices top-level assignment, and a mutated nested dict would silently
    # fail to persist.
    request.session[SESSION_KEY] = state


def _clear_state(request):
    request.session.pop(SESSION_KEY, None)


def _completed_through(state):
    """How many consecutive steps have usable answers.

    Used to stop someone deep-linking to step 3 with an empty session, and to
    send them back to the first step that still needs an answer.
    """
    if not (state.get("employee_id") or state.get("new_employee")):
        return 0
    if not (state.get("request_type") and state.get("requested_date")):
        return 1
    if not state.get("system_ids"):
        return 2
    return 3


def _redirect_to_first_gap(state, needed):
    """Bounce back to the earliest unanswered step, or None if we may proceed."""
    done = _completed_through(state)
    if done >= needed:
        return None
    return redirect(["wizard_employee", "wizard_details", "wizard_systems"][done])


def _context(state, step, **extra):
    context = {"step": step, "total_steps": TOTAL_STEPS, "state": state}
    context.update(extra)
    return context


# --- Steps ----------------------------------------------------------------

@login_required
def wizard_start(request):
    """Begin a new run, discarding anything left from a previous one."""
    _clear_state(request)
    return redirect("wizard_employee")


@login_required
def wizard_cancel(request):
    _clear_state(request)
    messages.info(request, "Wizard cancelled. Nothing was saved.")
    return redirect("request_list")


@login_required
def wizard_employee(request):
    """Step 1 — existing employee, or a new one."""
    state = _get_state(request)

    if request.method == "POST":
        form = WizardEmployeeForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            if data["mode"] == WizardEmployeeForm.MODE_EXISTING:
                state["employee_id"] = data["employee"].pk
                state["new_employee"] = None
            else:
                state["employee_id"] = None
                state["new_employee"] = {
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "email": data["email"],
                    # The session is JSON, so the department is held as a key
                    # and resolved back to a row at commit.
                    "department": data["department"].pk,
                    "job_title": data["job_title"],
                    # ISO string: the session is JSON, which has no date type.
                    "start_date": data["start_date"].isoformat(),
                }
            _save_state(request, state)
            return redirect("wizard_details")
    else:
        # Back-navigation: repopulate from whatever the session already holds.
        initial = {}
        if state.get("employee_id"):
            initial["mode"] = WizardEmployeeForm.MODE_EXISTING
            initial["employee"] = state["employee_id"]
        elif state.get("new_employee"):
            initial["mode"] = WizardEmployeeForm.MODE_NEW
            initial.update(state["new_employee"])
        form = WizardEmployeeForm(initial=initial or None)

    return render(request, "tracker/wizard/employee.html",
                  _context(state, 1, form=form))


@login_required
def wizard_details(request):
    """Step 2 — request type and date."""
    state = _get_state(request)
    gap = _redirect_to_first_gap(state, 1)
    if gap:
        return gap

    if request.method == "POST":
        form = WizardTypeDateForm(request.POST)
        if form.is_valid():
            state["request_type"] = form.cleaned_data["request_type"]
            state["requested_date"] = form.cleaned_data["requested_date"].isoformat()
            # Changing the request type only changes step 3's wording, so the
            # chosen systems stay valid and are deliberately preserved.
            _save_state(request, state)
            return redirect("wizard_systems")
    else:
        form = WizardTypeDateForm(initial={
            "request_type": state.get("request_type"),
            "requested_date": state.get("requested_date") or datetime.date.today().isoformat(),
        })

    return render(request, "tracker/wizard/details.html",
                  _context(state, 2, form=form))


@login_required
def wizard_systems(request):
    """Step 3 — which systems. The label depends on the request type."""
    state = _get_state(request)
    gap = _redirect_to_first_gap(state, 2)
    if gap:
        return gap

    request_type = state.get("request_type")

    if request.method == "POST":
        form = WizardSystemsForm(request.POST, request_type=request_type)
        if form.is_valid():
            state["system_ids"] = [s.pk for s in form.cleaned_data["systems"]]
            _save_state(request, state)
            return redirect("wizard_review")
    else:
        form = WizardSystemsForm(
            request_type=request_type,
            initial={"systems": state.get("system_ids", [])},
        )

    return render(request, "tracker/wizard/systems.html",
                  _context(state, 3, form=form))


@login_required
def wizard_review(request):
    """Step 4 — approver, review, and the atomic commit."""
    state = _get_state(request)
    gap = _redirect_to_first_gap(state, 3)
    if gap:
        return gap

    if request.method == "POST":
        form = WizardApproverForm(request.POST, user=request.user)
        if form.is_valid():
            state["approver_id"] = form.cleaned_data["approver"].pk
            state["notes"] = form.cleaned_data["notes"]
            _save_state(request, state)
            return _commit(request, state, form)
    else:
        form = WizardApproverForm(
            user=request.user,
            initial={
                "approver": state.get("approver_id"),
                "notes": state.get("notes", ""),
            },
        )

    return render(request, "tracker/wizard/review.html",
                  _context(state, 4, form=form, **_summary(state)))


# --- Review summary and commit -------------------------------------------

def _summary(state):
    """Resolve session primary keys into objects for the review screen."""
    employee = None
    if state.get("employee_id"):
        employee = Employee.objects.filter(pk=state["employee_id"]).first()

    new_employee = state.get("new_employee")
    new_department = None
    if new_employee:
        new_department = Department.objects.filter(
            pk=new_employee.get("department")
        ).first()

    return {
        "employee": employee,
        "new_employee": new_employee,
        "new_department": new_department,
        "systems": System.objects.filter(pk__in=state.get("system_ids", [])),
        "request_type_label": dict(
            AccessRequest.RequestType.choices
        ).get(state.get("request_type"), ""),
        "systems_label": WizardSystemsForm.LABELS.get(
            state.get("request_type"), "Systems affected"
        ),
    }


def _commit(request, state, form):
    """Write the employee and the request, or write nothing at all.

    The session was filled in over four page loads, so its contents are
    re-checked here against the database before anything is written — an
    employee can be deleted, a system retired, or an approver deactivated
    while the wizard sits open in a tab.
    """
    system_ids = state.get("system_ids", [])
    systems = list(System.objects.filter(pk__in=system_ids))
    if len(systems) != len(system_ids):
        messages.error(
            request,
            "One of the systems you chose is no longer available. "
            "Please re-check your selection.",
        )
        return redirect("wizard_systems")

    if state.get("employee_id") and not Employee.objects.filter(
        pk=state["employee_id"]
    ).exists():
        messages.error(
            request,
            "That employee no longer exists. Please choose someone else.",
        )
        return redirect("wizard_employee")

    new_employee = state.get("new_employee")
    if new_employee and not Department.objects.filter(
        pk=new_employee.get("department"), is_active=True
    ).exists():
        messages.error(
            request,
            "That department is no longer available. Please choose another.",
        )
        return redirect("wizard_employee")

    try:
        # Everything below either commits together or not at all. If creating
        # the employee succeeds but the request fails, the employee is rolled
        # back too - an abandoned half-record is worse than no record.
        with transaction.atomic():
            if state.get("new_employee"):
                data = dict(state["new_employee"])
                data["start_date"] = datetime.date.fromisoformat(data["start_date"])
                data["department_id"] = data.pop("department")
                employee = Employee.objects.create(**data)
            else:
                employee = Employee.objects.get(pk=state["employee_id"])

            access_request = AccessRequest.objects.create(
                employee=employee,
                request_type=state["request_type"],
                requested_date=datetime.date.fromisoformat(state["requested_date"]),
                # The wizard commits straight to pending: this is the normal
                # origin of a submitted request. Drafts come from the plain
                # ModelForm path instead.
                status=AccessRequest.Status.PENDING,
                requested_by=request.user,
                approver=form.cleaned_data["approver"],
                notes=state.get("notes", ""),
            )
            access_request.systems.set(systems)
    except Exception:
        # The transaction has already rolled back by this point, so no partial
        # record survives. Keep the session intact so nothing typed is lost.
        messages.error(
            request,
            "Could not save the request. Nothing was changed - please try again.",
        )
        return redirect("wizard_review")

    _clear_state(request)
    messages.success(request, "Request submitted for approval.")
    return redirect("request_detail", pk=access_request.pk)
