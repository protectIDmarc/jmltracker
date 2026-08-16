"""
The access boundary: there is no anonymous read path.

This enumerates the URLconf rather than listing routes by hand, so a view added
later is covered the moment it is routed. A test you have to remember to update
is a test that will eventually be wrong.
"""

from django.urls import reverse

from tracker import urls as tracker_urls

from .base import AppTestCase
from .factories import PASSWORD, make_request, make_user


def _all_tracker_urls():
    """Every route the tracker app defines, with a placeholder pk if needed."""
    built = []
    for pattern in tracker_urls.urlpatterns:
        name = pattern.name
        if "<int:pk>" in str(pattern.pattern):
            built.append((name, reverse(name, args=[1])))
        else:
            built.append((name, reverse(name)))
    return built


class AnonymousAccessTests(AppTestCase):
    def test_every_tracker_view_redirects_anonymous_users_to_login(self):
        routes = _all_tracker_urls()
        # Guard against the enumeration silently finding nothing and the test
        # passing vacuously.
        self.assertGreater(len(routes), 10)

        for name, url in routes:
            with self.subTest(route=name, url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302, f"{name} is not gated")
                self.assertIn("/accounts/login/", response["Location"])

    def test_login_page_is_reachable_anonymously(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_login_page_shows_nothing_credential_shaped(self):
        """The README is the only place demo credentials are published."""
        body = self.client.get(reverse("login")).content.decode().lower()
        for needle in ["requester.demo", "approver.demo", "demopassword",
                       "sign in as"]:
            self.assertNotIn(needle, body)

    def test_admin_is_gated(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)


class AuthenticatedAccessTests(AppTestCase):
    def setUp(self):
        # Needs a real password: two tests below post to the login view.
        self.user = make_user(password=PASSWORD)
        self.client.force_login(self.user)

    def test_root_is_the_dashboard(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_signed_in_user_can_read_any_request(self):
        """Reading is open to any signed-in user; only writing is restricted."""
        other = make_user()
        request = make_request(requested_by=other)
        response = self.client.get(reverse("request_detail", args=[request.pk]))
        self.assertEqual(response.status_code, 200)

    def test_login_redirects_to_the_dashboard(self):
        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": PASSWORD},
        )
        self.assertRedirects(response, reverse("dashboard"))

    def test_next_parameter_survives_login(self):
        """A deep link followed while signed out lands where it was aimed."""
        other = make_user()
        request = make_request(requested_by=other)
        target = reverse("request_detail", args=[request.pk])
        self.client.logout()

        response = self.client.get(target)
        self.assertIn(f"next={target}", response["Location"])

        response = self.client.post(
            f"{reverse('login')}?next={target}",
            {"username": self.user.username, "password": PASSWORD},
        )
        self.assertRedirects(response, target)
