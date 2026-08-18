# Part 4 — User Guide

## Signing in

![Signing in](../diagrams/signin-flow.svg)

Every page requires authentication. There is no public dashboard, and following a deep link while signed out returns you to that page after login rather than dropping you at the front.

The login page deliberately carries nothing credential-shaped — no printed demo logins, no “sign in as” shortcut. Demo credentials are published in the README and nowhere else.

Two-factor authentication is designed but not built. Signing in is a single step: username and password. The design is complete — a time-based code from an authenticator app, four configuration switches, per-device throttling — and is held as the final, optional milestone. Nothing in the running application implements it.

## Requester

### Raising a request — the wizard

![Requester flow](../diagrams/requester-flow.svg)

New request in the navigation starts the four-step wizard. It is the normal way in, and commits straight to pending.

| Step | You provide |
| --- | --- |
| 1 · Employee | Pick an existing employee, or capture a new one |
| 2 · Type and date | Joiner, mover or leaver, and when it is needed |
| 3 · Systems | Which systems — labelled to grant, to revoke or affected depending on the type |
| 4 · Review | Nominate an approver, check everything, confirm |

You can go back at any point; earlier answers are preserved. Nothing is saved until you confirm — abandoning the wizard leaves no trace, and a new employee captured at step 1 is created only at the final step, together with the request, in one transaction.

If someone already exists with the email you enter, step 1 tells you immediately rather than failing at the end.

### Raising a draft

Quick draft on the requests list saves a request without submitting it — useful when you are missing a detail. A draft appears in your dashboard under My open requests. Nominate an approver and use Submit for approval when ready; submitting without one is refused, because a pending request with no approver is invisible to whoever must act on it.

### Editing and withdrawing

You may edit or withdraw your own requests, and only while they are a draft or pending. Once a decision is taken the record is fixed — that is the point of it being evidence.

Withdraw marks the request cancelled and keeps it on record. Nothing is deleted.

## Approver

### Your queue

![Approver flow](../diagrams/approver-flow.svg)

The dashboard leads with Awaiting my approval — pending requests nominated to you, excluding any you raised yourself. Review opens the full record: employee, systems, dates, who raised it and why.

### Deciding

Approve or Reject. Both are recorded against your name with the exact time, and neither can be revised — a decision is a decision.

Three rules the system enforces rather than assumes:

- You cannot decide a request you raised.

- Only the nominated approver can decide.

- A request that has been decided cannot be decided again, including when two people click at the same moment.

### Marking completed

Once IT has actually provisioned the access, open the approved request and use Mark completed. Available to the approver or an administrator.

This is deliberately a separate, manual step. Approval is a decision; provisioning is work that happens outside this system. Marking completed automatically on approval would record access as granted that nobody granted.

## Reading the data

Requests lists everything, newest first, ten to a page. Any signed-in user can read any request — only writing is restricted. Status is always shown as a labelled badge, never colour alone.

The detail page is the audit record: employee and department, the systems (retired ones still shown, marked as such), requested date, who raised it, the approver, the decision time, notes, and when the record was created and last changed.

## Administrators

The Django admin at /admin/ manages the system and department catalogues and corrects data. It is restricted to staff accounts; the demo accounts have no administrative rights, so /admin/ is closed to them.

Retire a system by clearing is active rather than deleting it — historic requests must keep naming the system they were raised against. Deleting an employee who has request history is refused outright. Departments work the same way, and the admin is where the list everyone else picks from is maintained: add one and it appears in the wizard immediately. Deleting a department anyone is recorded against is refused too.

## Trying the demo

The public demo is seeded with invented people on example.com addresses and resets on a schedule, so create, edit and withdraw freely — a banner on every page says as much.

Credentials are in the README. The instructive path is to sign in as the requester, raise a request through the wizard, then sign in as the approver and decide it — that walks the whole lifecycle in about two minutes.

Two-factor authentication is not built. The demo is part of why it is specified to ship disabled even once it is: the accounts are shared, and a second factor enrolled by one visitor would lock out the next.
