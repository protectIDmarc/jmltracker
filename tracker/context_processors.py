from django.conf import settings


def demo_mode(request):
    """Expose DEMO_MODE to every template.

    A context processor rather than a template tag because the banner appears
    on the login page too, which is rendered by django.contrib.auth's view —
    there is no project view there to add it to the context.
    """
    return {"demo_mode": settings.DEMO_MODE}
