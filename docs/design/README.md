# Design documentation

**JML Access Request Tracker** — Luis Marques, August 2026.

Four parts, written from the finished build rather than ahead of it. They
document what the system does and why it was built that way, including the
decisions that were not obvious and the ones that were wrong first.

| Part | Covers |
| --- | --- |
| [1 — Use case](01-use-case.md) | The problem, what the system does, who uses it, what is deliberately out of scope |
| [2 — Technical design](02-technical-design.md) | Stack, configuration, data model, security model, URL structure, the wizard, deployment architecture |
| [3 — Implementation](03-implementation.md) | Build order, the false start, decision log, testing, deployment process, commit protocol |
| [4 — User guide](04-user-guide.md) | Signing in, the requester and approver paths, reading the data, administration, the demo |

This is documentation, not specification. Where it describes behaviour, the code
is the authority; anything here that the application does not do is a defect in
this document.

Two-factor authentication is **designed but not built**. It is described as a
design throughout, never as a feature.
