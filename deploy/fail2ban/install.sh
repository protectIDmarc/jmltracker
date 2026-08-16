#!/usr/bin/env bash
#
# Install the fail2ban filter, action and jails for this deployment.
#
# Run as root:  sudo ./deploy/fail2ban/install.sh
#
# Validates the filter against the real access log before enabling anything.
# A filter that matches nothing is worse than no filter: it looks like
# protection and provides none.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="/etc/fail2ban"
ACCESS_LOG="/var/log/nginx/access.log"
BLOCKLIST="/etc/nginx/conf.d/fail2ban-deny.conf"

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: must run as root" >&2
    exit 1
fi

echo "==> Installing filter, action and jails"
install -m 0644 "${SRC}/filter.d/jmltracker-login.conf" "${DEST}/filter.d/"
install -m 0644 "${SRC}/action.d/nginx-deny.conf"       "${DEST}/action.d/"
install -m 0644 "${SRC}/jail.d/jmltracker.conf"         "${DEST}/jail.d/"

echo "==> Preparing the nginx blocklist"
touch "$BLOCKLIST"
chmod 0644 "$BLOCKLIST"
nginx -t

echo "==> Validating the filter against the real log"
# fail2ban-regex reports how many lines matched. It cannot tell us the filter
# is *correct*, but it does catch the common failure - a regex that matches
# nothing because the log format is not what the filter assumed.
if ! fail2ban-regex "$ACCESS_LOG" "${DEST}/filter.d/jmltracker-login.conf" \
        --print-no-missed >/tmp/f2b-regex.out 2>&1; then
    echo "ERROR: fail2ban-regex failed:" >&2
    cat /tmp/f2b-regex.out >&2
    exit 1
fi
grep -E "^(Lines:|.*Failregex.*matched)" /tmp/f2b-regex.out || true
echo
echo "    (0 matches is expected if nobody has failed a login yet - the"
echo "     check below produces a real one.)"

echo "==> Reloading fail2ban"
systemctl reload fail2ban || systemctl restart fail2ban
sleep 2
fail2ban-client status

echo
echo "==> Jail detail"
fail2ban-client status sshd || true
fail2ban-client status jmltracker-login || true

echo
echo "==> Checking the login jail is watching the file, not the journal"
# The check that matters. fail2ban-regex above proves the filter matches lines
# in the file, but the running jail only reads that file if it is file-backed.
# Debian and Ubuntu default every jail to backend = systemd, and with that the
# logpath is ignored: the jail reads the journal, finds no nginx requests, and
# bans nobody while still appearing in the jail list as active.
if fail2ban-client status jmltracker-login | grep -q "Journal matches"; then
    echo "ERROR: jmltracker-login is reading the systemd journal, so it is" >&2
    echo "       watching nothing. Set 'backend = auto' in the jail." >&2
    exit 1
fi
if ! fail2ban-client status jmltracker-login | grep -q "${ACCESS_LOG}"; then
    echo "ERROR: jmltracker-login is not watching ${ACCESS_LOG}." >&2
    exit 1
fi
echo "    OK - watching ${ACCESS_LOG}"

echo
echo "==> Done. To prove the login jail actually bans, from a machine NOT in"
echo "    ignoreip, fail the login 10 times, then:"
echo "      sudo fail2ban-client status jmltracker-login"
echo "      cat ${BLOCKLIST}"
echo "    and to release:  sudo fail2ban-client set jmltracker-login unbanip <ip>"
