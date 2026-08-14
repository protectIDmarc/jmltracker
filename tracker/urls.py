from django.urls import path

from . import views

urlpatterns = [
    # Root is a landing slot: it redirects to the list today and becomes the
    # dashboard at M6, so no URL below has to move.
    path("", views.home, name="home"),
    path("requests/", views.request_list, name="request_list"),
    path("requests/new/", views.request_create, name="request_create"),
    path("requests/<int:pk>/", views.request_detail, name="request_detail"),
    path("requests/<int:pk>/edit/", views.request_edit, name="request_edit"),
    path("requests/<int:pk>/submit/", views.request_submit, name="request_submit"),
    path("requests/<int:pk>/withdraw/", views.request_withdraw, name="request_withdraw"),
]
