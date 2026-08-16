from django.urls import path

from . import views, wizard

urlpatterns = [
    # Root is a landing slot: it redirects to the list today and becomes the
    # dashboard at M6, so no URL below has to move.
    path("", views.home, name="home"),

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
]
