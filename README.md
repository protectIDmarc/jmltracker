# JML Access Request Tracker

A Django application for tracking **Joiner / Mover / Leaver (JML)** access requests: who needs access to which systems, when, and who approved it — with every decision stamped so the request record is the audit evidence.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2%20LTS-092E20?logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Status](https://img.shields.io/badge/status-in%20development-orange)

**Live demo:** `https://jmltracker.dueback.com` — sign in with the demo credentials below.

** Requester:   requester.demo
                demopassword1234

** Approver:    approver.demo
                demopassword1234

---

## The problem

In most organisations, access requests for joiners, movers and leavers arrive by email or word of mouth. There is no single record of who asked for what, which systems were granted, who approved it, or when. IT provisions late, leavers keep access after their last day, and when an auditor asks for evidence, nobody can produce it.

## What it does

The tracker records access requests across the employee lifecycle. A requester raises a request for an employee, selects the systems involved, and nominates an approver. The approver reviews and approves or rejects it, and every decision is stamped with the approver and the decision time. The result is one authoritative record of access decisions, enforced approval rules, and evidence available on demand.

It is a deliberately focused build: clean relational CRUD over three tables, a guided create wizard, enforced approval rules, and a dashboard. Background task queues, live provisioning against Active Directory or Microsoft Graph, and multi-tenancy are intentionally out of scope — one deployment serves one organisation.

---

## Features

- **Full CRUD** over Systems, Employees and Access Requests, with related-data integrity (deleting an employee who still has requests is blocked, so history is never lost).
- **Guided create wizard** — a four-step, session-based flow that assembles the employee and the request in a single atomic transaction: both are saved, or neither is.
- **Enforced approval rules** — no one can approve their own request, and a request that has already been decided cannot be decided again.
- **Audit-ready records** — each decision stamps the approver and the exact decision time.
- **Dashboard** — request counts by status plus an "awaiting my approval" panel for the signed-in user.
- **Gated by default** — every page requires login; there is no anonymous view of the data.
- **Optional two-factor authentication** — an authenticator-app second factor that is entirely configuration-driven and ships switched off.

---

## Roles and workflows

Two roles, both authenticated: the **Requester** raises and tracks requests, and the **Approver** decides them. Access is gated throughout — the dashboard and every other page sit behind login.

### Signing in

![Signing in](docs/diagrams/signin-flow.svg)

### Requester

![Requester flow](docs/diagrams/requester-flow.svg)

### Approver

![Approver flow](docs/diagrams/approver-flow.svg)

---

## Tech stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.12 |
| Framework | Django 5.2 LTS |
| Database | PostgreSQL (every environment — no engine drift) |
| Config | `django-environ` (12-factor, environment-driven) |
| Static files | WhiteNoise |
| WSGI server | Gunicorn |
| DB driver | `psycopg` (Postgres 3) |

The application uses function-based views, ModelForms and sessions throughout — clarity over cleverness, with comments recording the reasoning behind each decision.

### One codebase, many environments

Nothing environment-specific is hardcoded. `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and the database all read from environment variables with safe local defaults. `DATABASE_URL` is the single database lever, so moving between a local Postgres, the server's Postgres and a hosted Postgres is a configuration change and nothing more. Secrets never enter version control: `.env` is gitignored, and `.env.example` documents every variable with no values.

---

## Data model

Three related tables:

- **System** — an application or entitlement (`name`, `category`, `is_active`).
- **Employee** — the person in the lifecycle (`name`, unique `email`, `department`, `job_title`, `start_date`, `status`).
- **AccessRequest** — a foreign key to Employee (protected on delete, so history is preserved), a many-to-many to System, a `request_type` (join / move / leave), `requested_date`, `status`, `requested_by` and `approver`, `decided_at`, `notes` and timestamps.

### Status lifecycle

```
draft → pending → approved | rejected → completed | cancelled
```

- **draft** — saved but not yet submitted.
- **pending** — submitted through the wizard, awaiting a decision.
- **approved / rejected** — decided by the approver; both stamp who decided and when.
- **completed** — marked explicitly by the approver or an administrator once IT has provisioned the access (which happens outside this system).
- **cancelled** — withdrawn; a status change, never a hard delete.

---

## Security

- **Authentication** — Django session authentication with the standard login and logout views.
- **Access control** — every application view requires login. The login page is the only public page, and it carries nothing credential-shaped: demo credentials live only in this README, never on the deployed site.
- **Approval integrity** — self-approval and double-approval are refused in the view layer, and the decisive status check runs inside the database transaction so a race cannot slip two approvals through.
- **Optional MFA** — an `django-otp` TOTP second factor (authenticator app), chosen over SMS to avoid SIM-swap exposure and external dependencies. It is driven by four environment switches (`MFA_ENABLED`, `MFA_ENFORCED_ROLES`, `MFA_EXEMPT_USERS`, `MFA_GRACE_LOGINS`) and is genuinely inert when disabled — the enrolment routes are not registered and login stays a single step. When enabled, enrolment presents a QR code and one-time recovery codes; verification attempts are throttled per device, while brute-force protection at the network edge is handled by `fail2ban`.

---

## Running locally

```bash
# 1. Clone and enter
git clone https://github.com/protectIDmarc/jmltracker.git
cd jmltracker

# 2. Virtual environment + dependencies
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Environment config
cp .env.example .env               # then set SECRET_KEY and DATABASE_URL

# 4. Database
python manage.py migrate
python manage.py createsuperuser

# 5. Run
python manage.py runserver
```

The app expects PostgreSQL via `DATABASE_URL` (for example `postgres://user:pass@localhost:5432/jml`). Point that variable at a local Postgres instance before running the migrations.

---

## Deployment

Production runs on Ubuntu with Gunicorn under systemd, behind an Nginx reverse proxy with Let's Encrypt TLS. `DEBUG` is always `False` on any public instance, and static files are served by WhiteNoise. The `deploy/` directory holds the systemd unit, the Nginx configuration, and a deploy script that pulls, installs, migrates, collects static files and restarts the service. The environment-driven configuration means a managed host such as Render is a near drop-in target.

---

## Testing

- Model integrity — protected delete on employees with requests; unique email.
- Approval guards — self-approval refused, double-approval refused, approver and decision time stamped (each rule has a test that fails if the rule is removed).
- Wizard atomicity — the final step commits both rows or neither; an abandoned wizard leaves nothing behind.
- Access control — every application view redirects an anonymous visitor to login.

---

## Demo

The public demo is seeded with synthetic data (invented names on `example.com` addresses) and reset on a schedule, so you can create, edit and delete freely while looking around.

| Role | Username | Password |
| --- | --- | --- |
| Requester | `requester.demo` | `demopassword1234` |
| Approver | `approver.demo` | `demopassword1234` |

Sign in as the requester to raise a request, then sign in as the approver to decide it — that walks the whole flow. Two-factor authentication is switched off on the demo: the accounts are shared, so a second factor enrolled by one visitor would lock out the next.

---

## Project status

The core is under active development against a fixed build order. Complete and in progress:

- [x] Environment-driven project scaffold, three-table data model, admin
- [ ] PostgreSQL across all environments
- [ ] Seed data
- [ ] Read paths (list, detail)
- [ ] Write paths (create, edit, withdraw)
- [ ] Guided create wizard
- [ ] Dashboard and approval guards
- [ ] Test suite
- [ ] Public deployment (Gunicorn / Nginx / TLS)
- [ ] Demo hardening and seeded demo accounts
- [ ] Optional two-factor authentication

### Beyond the core

A tamper-evident audit trail using hash-chained, signed records, and a swappable connector seam for real provisioning targets.

---

## Out of scope (by design)

Background task queues, live provisioning against Active Directory or Microsoft Graph, multi-tenancy, and SQLite. These keep the project focused on demonstrable, well-understood fundamentals.

---

## Author

Built by **Luis Marques**.
