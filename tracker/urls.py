from django.urls import path

from . import views, wizard

urlpatterns = [
    # The dashboard took over the root slot at M6, exactly as the placeholder
    # there was reserved for — no other URL had to move.
    path("", views.dashboard, name="dashboard"),

    path("requests/", views.request_list, name="request_list"),
    path("requests/new/", views.request_create, name="request_create"),

    # The wizard. Named steps rather than /1/ /2/ so a URL says where it is.
    path("requests/new/wizard/", wizard.wizard_start, name="wizard_start"),
    path("requests/new/wizard/employee/", wizard.wizard_employee, name="wizard_employee"),
    path("requests/new/wizard/details/", wizard.wizard_details, name="wizard_details"),
    path("requests/new/wizard/systems/", wizard.wizard_systems, name="wizard_systems"),
    path("requests/new/wizard/review/", wizard.wizard_review, name="wizard_review"),
    path("requests/new/wizard/cancel/", wizard.wizard_cancel, name="wizard_cancel"),

    path("requests/<int:pk>/", views.request_detail, name="request_detail"),
    path("requests/<int:pk>/edit/", views.request_edit, name="request_edit"),
    path("requests/<int:pk>/submit/", views.request_submit, name="request_submit"),
    path("requests/<int:pk>/withdraw/", views.request_withdraw, name="request_withdraw"),
    path("requests/<int:pk>/decide/", views.request_decide, name="request_decide"),
    path("requests/<int:pk>/complete/", views.request_complete, name="request_complete"),
]
