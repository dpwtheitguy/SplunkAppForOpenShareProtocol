#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
archive=$(./scripts/package.sh .lab)
docker compose --env-file .lab/env exec -T --user splunk splunk sh -ec '
    package=$(mktemp --suffix=.spl)
    trap "unlink \"$package\"" EXIT
    cat > "$package"
    /opt/splunk/bin/splunk install app "$package" -update 1 -auth "admin:$SPLUNK_PASSWORD"
' < "$archive"
docker compose --env-file .lab/env exec -T --user root splunk sh -ec '
    mkdir -p /opt/splunk/etc/apps/openshare/local
    cp -a /mnt/openshare-lab/splunk/. /opt/splunk/etc/apps/openshare/local/
    chown -R splunk:splunk /opt/splunk/etc/apps/openshare
'
docker compose --env-file .lab/env restart splunk
