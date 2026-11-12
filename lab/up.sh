#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./lab/setup.sh
docker compose --env-file .lab/env up -d --build --wait --wait-timeout 180
./lab/install-app.sh
for attempt in {1..36}; do
    if curl --silent --fail -o /dev/null http://127.0.0.1:8000/en-US/account/login; then
        docker compose --env-file .lab/env exec -T --user splunk splunk /opt/splunk/bin/splunk cmd python < lab/seed.py
        exit
    fi
    sleep 5
done
printf '%s\n' 'Splunk Web did not become ready.' >&2
exit 1
