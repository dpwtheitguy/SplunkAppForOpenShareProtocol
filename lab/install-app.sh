#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --env-file .lab/env exec -T --user root splunk sh -ec '
    mkdir -p /opt/splunk/etc/apps/openshare
    cp -a /mnt/openshare-app/. /opt/splunk/etc/apps/openshare/
    chown -R splunk:splunk /opt/splunk/etc/apps/openshare
'
docker compose --env-file .lab/env restart splunk
