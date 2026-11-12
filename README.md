# OpenShare for Splunk Enterprise

This lab app publishes read-only OpenSharing table snapshots from a Splunk index or saved report. Publishers use Splunk Web to preview and publish data, refresh a snapshot, manage recipient profiles, and review activity. The gateway exposes the recipient API and signed Parquet downloads.

## Running the lab

Run the startup script after reviewing the Splunk Enterprise license and General Terms. The official image's startup flags signal acceptance.

```bash
sg docker -c './lab/up.sh'
```

Open [OpenShare in Splunk Web](http://127.0.0.1:8000/en-US/app/openshare/openshare). Use `admin` for logging settings or `openshare_publisher` for the limited publisher workflow. The corresponding credentials are in the private `.lab/env` file under `SPLUNK_PASSWORD` and `PUBLISHER_PASSWORD`.

1. Create a share from **Saved report → OpenShare Lab Errors by Service**.
2. Select `service, error_count` and preview the snapshot. Publishing opens a copyable firewall and load balancer guide with the recipient endpoint, port, allowed routes, and a token-free reachability check. Reopen it from **Network guide** on the share, then generate a profile for the recipient.
3. For the isolated recipient, save the profile as `.lab/recipient/profile.share` with mode `0600`. The connector trusts the lab CA and resolves `share.lab` through Docker.
4. Review **Activity** and manage the grant in **Access Tokens**. Use **Network Access** for the allowed route list.

## Tests and sample data

Run the unit tests and the Playwright and OpenSharing regression against the local lab:

```bash
sg docker -c './lab/test-unit.sh'
sg docker -c './lab/verify.sh'
```

The regression seeds synthetic billing and identity events, checks restricted sources, and drives index and report publishing through Splunk Web. It inserts a billing event between the two report reads and verifies that refresh adds it without changing the grant. It checks token rotation, revocation, Activity filtering, and the gateway boundary. Test profiles live in a temporary directory. Desktop and narrow-width screenshots go to `.lab/test-artifacts/`.

To add another synthetic billing error for a manual refresh demo:

```bash
sg docker -c 'docker compose --env-file .lab/env exec -T --user splunk splunk /opt/splunk/bin/splunk cmd python - --append-billing' < lab/seed.py
```

Search the administrator's Splunk search view with `index=openshare_audit sourcetype=openshare:audit` to see the audit mirror. SQLite holds the live grant state and powers the Activity screen. The audit mirror may lag briefly and records carry an event ID for deduplication.

## Deployment boundaries

The gateway binds to host loopback on TCP 8443. The isolated recipient network reaches the gateway by its `share.lab` alias. Splunk Web binds to loopback on TCP 8000. Splunk management, publishing routes, and raw snapshot storage are private. The lab uses synthetic data, a local CA, and a deployment-mounted integration secret over the private Docker network. Recipient tokens are stored as SHA-256 verifiers.

This MVP uses scalar string columns and a single active snapshot per table. Refresh preserves recipient grants. Signed file links expire within five minutes, bounded by the credential's expiration. The lab retains snapshot files in its Docker volume. Production deployment needs private-link TLS, managed secret provisioning, and automated snapshot retention. The app archive can be built for inspection with `tar -C app -czf .lab/openshare.spl openshare`. Running the app requires the companion service and its private integration configuration.
