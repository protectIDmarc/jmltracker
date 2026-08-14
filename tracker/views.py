from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """Placeholder landing page.

    Behind @login_required from the very first view: there is no anonymous read
    path in this application, and the boundary is easier to keep than to add.
    """
    return render(request, "tracker/home.html")
