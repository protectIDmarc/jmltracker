from django.urls import path

from . import views

urlpatterns = [
    # Root is a landing slot: it redirects to the list today and becomes the
    # dashboard at M6, so no URL below has to move.
    path("", views.home, name="home"),
    path("requests/", views.request_list, name="request_list"),
    path("requests/<int:pk>/", views.request_detail, name="request_detail"),
]
