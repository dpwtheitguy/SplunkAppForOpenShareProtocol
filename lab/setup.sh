#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p .lab/tls .lab/recipient
if [[ ! -f .lab/env ]]; then
    {
        printf 'SPLUNK_PASSWORD=Lab!%s\n' "$(openssl rand -hex 16)"
        printf 'OPENSHARE_KEY=%s\n' "$(openssl rand -hex 32)"
        printf 'FILE_KEY=%s\n' "$(openssl rand -hex 32)"
    } > .lab/env
fi
if ! grep -q '^PUBLISHER_PASSWORD=' .lab/env; then
    printf 'PUBLISHER_PASSWORD=Lab!%s\n' "$(openssl rand -hex 16)" >> .lab/env
fi
if [[ ! -f .lab/app-key ]]; then
    sed -n 's/^OPENSHARE_KEY=//p' .lab/env > .lab/app-key
    chmod 444 .lab/app-key
fi
if [[ ! -f .lab/tls/server.crt ]]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj /CN=OpenShare-Lab-CA \
        -keyout .lab/tls/ca.key -out .lab/tls/ca.crt 2>/dev/null
    openssl req -newkey rsa:2048 -nodes -subj /CN=share.lab \
        -keyout .lab/tls/server.key -out .lab/tls/server.csr 2>/dev/null
    printf 'subjectAltName=DNS:share.lab\nextendedKeyUsage=serverAuth\n' > .lab/tls/server.ext
    openssl x509 -req -days 30 -in .lab/tls/server.csr -CA .lab/tls/ca.crt \
        -CAkey .lab/tls/ca.key -CAcreateserial -extfile .lab/tls/server.ext \
        -out .lab/tls/server.crt 2>/dev/null
fi
