#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="$(realpath -m "${1:-packages}")"
mkdir -p "$output"
app=openshare
version="$(awk '/^\[/{section=$0} section=="[launcher]" && /^version = /{print $3}' "app/$app/default/app.conf")"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
grep -qx "id = $app" "app/$app/default/app.conf"
archive="$app-$version.spl"
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
    --exclude=__pycache__ --exclude='*.pyc' --exclude='*.pyo' \
    -C app -czf "$output/$archive" \
    "$app/default" "$app/metadata" "$app/bin" "$app/appserver" "$app/README" "$app/README.txt" "$app/app.manifest"
(
    cd "$output"
    sha256sum "$archive" > "$archive.sha256"
)
printf '%s\n' "$output/$archive"
