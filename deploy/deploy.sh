#!/usr/bin/env bash
#
# Deploy the JML tracker: pull, install, migrate, collectstatic, restart.
# Run from the repo root on the target host:  ./deploy/deploy.sh
#
# Deliberately does no git commit or push — this script only ever moves the
# working tree forward to what is already on the remote.

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

echo "==> Collecting static files"
"${VENV}/bin/python" manage.py collectstatic --noinput

echo "==> Running deployment checks"
"${VENV}/bin/python" manage.py check --deploy

echo "==> Restarting ${SERVICE}"
sudo systemctl restart "${SERVICE}"
sudo systemctl --no-pager --lines=0 status "${SERVICE}"

echo "==> Done"
