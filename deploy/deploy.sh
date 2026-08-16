#!/usr/bin/env bash
#
# Deploy the JML tracker: pull, install, migrate, test, collectstatic, restart.
# Run from the repo root on the target host:  ./deploy/deploy.sh
#
# Deliberately does no git commit or push — this script only ever moves the
# working tree forward to what is already on the remote.
#
# The final step restarts the service, so it will prompt for a sudo password.
# That is intentional: a deploy is a deliberate act, and granting passwordless
# sudo for systemctl to avoid one prompt trades a real privilege for a small
# convenience.

set -euo pipefail

APP_DIR="/opt/jmltracker/jmltracker"
VENV="${APP_DIR}/.venv"
SERVICE="jmltracker"

cd "${APP_DIR}"

echo "==> Checking for uncommitted local changes"
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "ERROR: working tree is dirty. Commit or stash before deploying." >&2
    exit 1
fi

echo "==> Pulling latest"
git pull --ff-only

echo "==> Installing dependencies"
"${VENV}/bin/pip" install --quiet --upgrade pip
"${VENV}/bin/pip" install --quiet -r requirements.txt

echo "==> Applying migrations"
"${VENV}/bin/python" manage.py migrate --noinput

echo "==> Running the test suite"
# Before the restart, not after: a failure here leaves the running service on
# the previous code rather than swapping in something broken. set -e aborts the
# script on a non-zero exit, so this is the gate.
"${VENV}/bin/python" manage.py test tracker

echo "==> Collecting static files"
"${VENV}/bin/python" manage.py collectstatic --noinput

echo "==> Running deployment checks"
# Warnings do not abort: check --deploy exits non-zero only on errors, and the
# TLS warnings are expected until a certificate is in place.
"${VENV}/bin/python" manage.py check --deploy

echo "==> Restarting ${SERVICE}"
sudo systemctl restart "${SERVICE}"
sudo systemctl --no-pager --lines=0 status "${SERVICE}"

echo "==> Done"
