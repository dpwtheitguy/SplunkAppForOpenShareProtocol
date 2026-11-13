# OpenShare project handoff

OpenShare publishes reviewed, read-only snapshots from Splunk Enterprise indexes and saved reports using the Linux Foundation OpenSharing table protocol. The Splunk app handles publisher permissions, preview, publishing, recipient tokens, and Activity. The separately deployed companion materializes Parquet and serves scoped profiles through the recipient HTTPS gateway. LM Studio is an optional lab consumer.

## Release state

- The latest package is `packages/openshare-0.3.2.spl` with a SHA-256 sidecar. The source and archive include Apache 2.0 licensing and credit to OpenShare contributors.
- Keep the app ID, archive root, and manifest name `openshare` for in-place upgrades. Match the version in both `app.conf` stanzas and `app.manifest`. Preserve older archives and checksums. Add each new package and its changes to the README version history.
- Keep `[package] check_for_updates = 1` in public packages. Splunkbase rejected 0.3.0 when this was disabled. The local AppInspect private-app advisory does not apply to the public submission. The builder rejects disabled or missing update checks.
- Standalone Linux Enterprise 9.4.16 and 10.6.1 passed browser and recipient regression on 0.3.1. Version 0.3.2 added licensing and passed local AppInspect with zero errors, zero failures, and four warnings. Cloud, Windows, and clustered compatibility remain unvalidated. Splunkbase approval has not been confirmed.
- See `docs/splunkbase/submission.md` for the listing materials and `README.md` for deployment, troubleshooting, and security.

## Working in the repository

- `app/openshare/` contains the Splunk app. Keep third-party Python packages outside the archive. The handler uses Splunk's bundled APIs and supports Python 3.9 and 3.13.
- `service/` contains the companion and OCSF 1.7.0 audit exporter. `lab/` contains Compose setup, synthetic fixtures, the isolated recipient, browser checks, and the LM Studio tool.
- Keep lab secrets, TLS keys, and profiles under ignored `.lab/`. Avoid printing them in logs or copying them into the package.
- The signed-in publisher's Splunk permissions govern the search. Only the original publisher refreshes an existing share. Rotation preserves expiry. Revocation blocks new signed URLs. Previously issued links can remain valid for up to five minutes, bounded by grant expiration.
- Keep the publishing listener and Splunk management endpoints private. The recipient gateway serves only approved OpenSharing routes. Pending production work includes automatic snapshot retention, bounded audit spooling, and a hardened non-root companion.

## Build and verify

```bash
./scripts/package.sh
./scripts/check-package.sh
./lab/test-unit.sh
./lab/verify.sh
(cd packages && sha256sum -c ./*.sha256)
```

Start the lab with `./lab/up.sh` after reviewing the Splunk image terms. The current local session can use `sg docker -c '…'` for Docker access. The test suite installs the generated archive and exercises publishing, refresh, rotation, and revocation on the running lab. The lab and optional LM Studio demo are documented in the README.

No project-specific hooks or skills were created. The repository's build and verification scripts are the reusable checks. Existing host skills remain managed outside this project.
