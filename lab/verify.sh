#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
RECIPIENT_DIR=$(mktemp -d "$PWD/.lab/browser-test.XXXXXXXX")
export RECIPIENT_DIR
trap 'rm -rf -- "$RECIPIENT_DIR"' EXIT
mkdir -p .lab/test-artifacts
grep '^PUBLISHER_PASSWORD=' .lab/env > "$RECIPIENT_DIR/browser.env"
docker compose --env-file .lab/env exec -T --user splunk splunk /opt/splunk/bin/splunk cmd python < lab/seed.py
docker compose --env-file .lab/env exec -T --user splunk splunk \
    /opt/splunk/bin/splunk cmd python /mnt/openshare-lab/check.py
docker build -t openshare-lab-browser -f lab/WebCheck.Dockerfile lab
docker compose --env-file .lab/env --profile test build recipient
browser() {
    docker run --rm --network host --user "$(id -u):$(id -g)" \
        --env-file "$RECIPIENT_DIR/browser.env" -e "WEB_STAGE=$1" \
        -e "WEB_BASE=http://127.0.0.1:${SPLUNK_WEB_PORT:-8000}" \
        -v "$RECIPIENT_DIR:/lab-output" \
        -v "$PWD/.lab/test-artifacts:/artifacts" openshare-lab-browser
}
recipient() {
    local -a options=()
    for setting in "$@"; do options+=(-e "$setting"); done
    docker compose --env-file .lab/env --profile test run --rm "${options[@]}" recipient
}
browser layout
browser index
recipient EXPECT_INDEX=1
browser disable
recipient EXPECT_REVOKED=1
browser publish
baseline=$(recipient EXPECT_VERSION=0)
printf '%s\n' "$baseline"
billing=$(printf '%s\n' "$baseline" | sed -n 's/^billing_count=//p')
[[ "$billing" =~ ^[0-9]+$ ]]
docker compose --env-file .lab/env exec -T --user splunk splunk /opt/splunk/bin/splunk cmd python - --append-billing < lab/seed.py
browser refresh
recipient EXPECT_VERSION=1 "EXPECT_BILLING=$((billing + 1))"
browser rotate
recipient EXPECT_REVOKED=1
mv "$RECIPIENT_DIR/rotated.share" "$RECIPIENT_DIR/profile.share"
recipient EXPECT_VERSION=1 "EXPECT_BILLING=$((billing + 1))"
browser revoke
recipient EXPECT_REVOKED=1
browser disable
