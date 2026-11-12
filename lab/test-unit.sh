#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./lab/setup.sh
docker compose --env-file .lab/env build sharing
docker compose --env-file .lab/env run --rm --no-deps \
    --volume "$PWD/tests:/tests:ro" --entrypoint python sharing \
    -m unittest discover -s /tests -v
