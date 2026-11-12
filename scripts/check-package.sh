#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
archive=$(./scripts/package.sh)
report_dir="$PWD/.lab/appinspect"
mkdir -p "$report_dir"
docker build -t openshare-build-tools -f scripts/BuildTools.Dockerfile scripts
docker run --rm \
    -v "$PWD:/workspace:ro" \
    -v "$report_dir:/reports" \
    openshare-build-tools sh -ec '
        ruff check --no-cache app service lab tests
        ruff format --no-cache --check app service lab tests
        slim validate app/openshare
        splunk-appinspect inspect "$1" --mode precert \
            --output-file /reports/report.json --data-format json > /reports/appinspect.log
        python -c "
import json
with open(\"/reports/report.json\") as source:
    report = json.load(source)
summary = report[\"summary\"]
print(\"AppInspect summary:\", summary)
raise SystemExit(bool(summary.get(\"failure\") or summary.get(\"error\")))
"
    ' sh "/workspace/packages/${archive##*/}"
printf 'AppInspect report: %s/report.json\n' "$report_dir"
