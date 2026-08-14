"""
Root URL configuration.

The only anonymous routes in this project are the login page and static files.
Everything else sits behind @login_required, so an anonymous hit on the root
URL redirects to login rather than rendering anything.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Supplies login/ and logout/ (plus the password-reset routes, unused for
    # now). LOGIN_URL resolves against the "login" name defined here.
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("tracker.urls")),
]
