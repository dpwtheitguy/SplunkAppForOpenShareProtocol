# OpenShare for Splunk Enterprise MVP PRD

## Product goal

A Splunk Enterprise publisher can review and publish a read-only table from one index or saved report and grant a recipient time-limited access over HTTPS. The recipient reads the published snapshot through the Linux Foundation’s OpenSharing table APIs. Splunk Cloud Machine Data Lake also uses the name Open Sharing for its own workflow. This product targets self-managed Splunk Enterprise. [OpenSharing specification](https://github.com/OpenSharing-IO/OpenSharing/tree/main/spec/protocols) [Splunk Cloud Open Sharing](https://help.splunk.com/en/data-management/onboard-data-to-splunk-cloud-platform/land-data-in-machine-data-lake/10.5.2605/discover-and-search-machine-data-lake-data/query-and-access-machine-data-lake-data/share-an-analytics-table-with-open-sharing)

Use OpenShare when data owners need to approve what leaves Splunk before a consumer reads it. Splunk MCP Server supports interactive tool calls, including live search where configured. An agent can use a narrow reader tool to consume an OpenShare snapshot. The lab demonstrates this with LM Studio and the stock Python connector. [Splunk MCP Server](https://help.splunk.com/en/splunk-enterprise/mcp-server-for-splunk-platform/2.1/about-splunk-mcp-server/about-mcp-server-for-splunk-platform)

## Publisher and recipient workflows

1. **Select and preview.** A user with `openshare_publish` selects an index or saved report, a search window, and an explicit list of fields. The app runs the search in the user’s Splunk context and materializes a Parquet snapshot. The preview shows up to ten rows and the exact selected fields. Changes to the form clear the preview. A draft expires after 30 minutes.
2. **Publish and grant.** Publish the previewed snapshot and review the firewall and load balancer guide. Generate an expiring recipient profile and download it once. The UI shows the share, recipient label, status, expiration, and last snapshot request.
3. **Read.** The recipient client uses HTTPS and the profile’s bearer token to discover the granted table, request the current snapshot, and fetch signed Parquet files. Recipient requests run no SPL.
4. **Operate.** Filter the Activity view by share and event. The original publisher can preview and publish a refresh. Activation swaps the snapshot atomically and preserves active grants. Publishers and app administrators can manage grants, and rotation preserves the existing expiry. Revocation and disablement block new requests. Previously issued file URLs remain usable within their five-minute lifetime or the earlier grant expiration.

## Delivery and portability

The installable `openshare` app provides Splunk Web controls and a private authenticated REST handler. The package carries no third-party Python libraries. The handler uses the standard library and Splunk’s bundled REST APIs, with a Python 3.9 fallback and Python 3.13 selection on releases that support it. Parquet and web-server dependencies stay in the companion. The reproducible archive builder uses Python’s standard library and runs independently of Docker.

The companion stores SQLite grants and Parquet data on a persistent volume. Splunk connects to the companion’s private listener with a provisioned integration key and verified HTTPS outside the isolated lab. Configure one companion, volume, and integration credential per Splunk trust domain. A separate recipient gateway serves OpenSharing routes. Publishing routes, Splunk Web, and the management API stay private. The app shows the recipient hostname and port, allowlisted methods and paths, TLS and DNS requirements, and a token-free probe. A reachable unauthenticated discovery route returns HTTP 401. File delivery requires a valid profile.

The MVP supports standalone Linux deployments, manual snapshots and refresh, and one published table per share. Preview limits include a maximum seven-day search window, 50,000 rows, and 100 MB of serialized results. Supported scalar results are published as strings. Defer clustered deployment, Cloud vetting, scheduled refresh, Iceberg catalog access, change data feeds, and additional OpenSharing asset types.

## Security and telemetry

- **Source authorization.** Use the signed-in publisher’s Splunk session for extraction and the original publisher’s context for refresh. Preview and publish the same materialized rows. Publisher access changes require an operator review of existing grants.
- **Credentials.** Store opaque recipient-token verifiers, provision integration and signing keys separately, and use TLS for recipient and private production traffic. Keep profile and signed-link material out of logs. Serialize grant revocation with signed URL issuance and use private, no-store recipient responses.
- **Audit.** Persist share mutations, grant lifecycle changes, and logging-setting changes. Record snapshot requests, completed file responses, and authorization denials when recipient auditing is enabled. The exporter uses OCSF 1.7.0 API Activity JSONL with an installation-scoped event identifier, observed request metadata, and restricted Splunk indexing. Bearer activity identifies a grant and does not establish who held it. Previously exported legacy records stay in their original format. [OCSF API Activity](https://github.com/ocsf/ocsf-schema/blob/v1.7.0/events/application/api_activity.json)
- **Diagnostics.** Admins can enable verbose diagnostics for 30 minutes. Debug telemetry records timing and status and uses route templates. Regular audit records exclude tokens, signed URLs, headers, and exported rows.
- **Operator responsibilities.** Apply request limits at trusted ingress, restrict storage and audit access, set backup and retention policy, and review active grants. Automatic pruning of staged and retired files, bounded audit spooling, audit delivery health indicators, and hardened non-root service deployment remain follow-up work.

## Acceptance and release gates

- Build a versioned `.spl` with matching folder, package ID, and manifest identity. Verify its checksum and install the archive through Splunk’s CLI.
- Run Ruff, Splunk Packaging Toolkit validation, AppInspect precert, and the service unit tests.
- Exercise a limited publisher and a restricted index and report. Verify the same approved columns and rows in Splunk preview and recipient output, with external access limited to the HTTPS gateway.
- Inject a synthetic event and confirm refresh updates the snapshot with the same profile. Verify rotation preserves the expiration, expired or revoked credentials cannot get new file URLs, and admin refresh cannot expand another publisher’s data access.
- Verify the OCSF export contains publish, read, and revoke events in Splunk, preserves timestamps, and excludes credentials and exported rows. Turn recipient auditing off and confirm share and grant mutations still appear.
- For a Splunkbase submission, confirm app ID availability, choose distribution licensing and support terms, document the companion dependency and exported data, provide listing media, and complete Splunk’s submission and manual review. AppInspect precert is one input to that review. [Splunkbase file standards](https://dev.splunk.com/enterprise/docs/releaseapps/splunkbase/approvalcriteria/) [Splunkbase validation and review](https://dev.splunk.com/enterprise/docs/releaseapps/splunkbase/app-tiering/)

## Lab

The Compose lab runs Splunk Web on host loopback, the companion on a private network, and the Python recipient on a separate internal network. The gateway is the only lab service shared with the recipient network. The lab includes allowed and restricted indexes, synthetic billing and identity events, and a saved aggregate report. It can run the same regression on additional Splunk images with alternate host ports. See [setup and test commands](README.md).
