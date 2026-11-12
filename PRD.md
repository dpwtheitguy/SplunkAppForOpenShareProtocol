# Splunk Enterprise OpenSharing MVP PRD

**Status** Draft for review

## Product goal

A Splunk Enterprise administrator can install an app, choose one index or saved report, and publish a bounded, read-only table to a named recipient. Before publishing, the administrator can see which rows and columns will be shared, who can read them, and when access expires. After publishing, the administrator can revoke access and see when the recipient's credential was used.

The protocol target is the Linux Foundation's OpenSharing specification, which extends the original Delta Sharing protocol. The MVP implements its table discovery and URL-based snapshot reads for self-managed Splunk Enterprise. Splunk Cloud Machine Data Lake has a similarly named Open Sharing feature for eligible Cloud datasets. [Linux Foundation OpenSharing announcement](https://www.linuxfoundation.org/press/linux-foundation-announces-opensharing-project-to-standardize-ai-asset-and-data-exchange) [Splunk Cloud Open Sharing documentation](https://help.splunk.com/en/data-management/onboard-data-to-splunk-cloud-platform/land-data-in-machine-data-lake/10.5.2605/discover-and-search-machine-data-lake-data/query-and-access-machine-data-lake-data/share-an-analytics-table-with-open-sharing)

## Users and first workflow

The **publisher** is a Splunk administrator or a user explicitly granted publishing rights. The **recipient** is an analyst or service that reads the shared table with a OpenSharing client.

1. **Choose a source.** Pick a single accessible index or saved report. For an index, set a bounded time window and optional source or sourcetype filters. For a report, show its owner and app so reports with identical names are distinguishable. Start with tabular reports that require no runtime inputs.
2. **Choose fields and preview.** Select columns explicitly. Show sample rows, column types, the resolved time window, and the snapshot row count. Require an explicit choice to include `_raw` if available. Review and publish the same materialized snapshot so report changes after preview cannot alter the published data.
3. **Grant access.** Enter a recipient label and expiration date. Review a summary such as “Analytics team can read 240 rows from Error Counts by Service, including hour, service, and error_count, until Nov 19 at 5 PM Pacific.” Publish and download a recipient-specific OpenSharing profile. Show that anyone holding the profile can use it until it expires or is revoked.
4. **Manage access.** List shares with source, snapshot time, columns, row count, recipients, expiration, and last successful read. Add a recipient, rotate a credential, revoke a recipient, or disable the entire share. To update the data, generate and review a replacement snapshot and publish it atomically. Existing active recipients keep access to the table and receive the replacement on their next read.

## MVP requirements

### Splunk Web interface

Use the Splunk MCP Server app as the design reference for navigation, settings tabs, tables, and token dialogs. Open on **Shares** with a **Create share** action. Show **Generate profile** on each published share and provide a central **Settings → Access Tokens** screen for managing credentials across shares. [Splunk MCP Server token management](https://help.splunk.com/en/splunk-enterprise/mcp-server-for-splunk-platform/2.1/set-up-and-connect-to-splunk-mcp-server/manage-encrypted-tokens-for-splunk-mcp-server)

The token dialog shows the selected share and read-only access, asks for a recipient label and expiration, and offers a one-time profile download. The token table shows recipient label, share, issuer, expiration, status, and last successful use, with actions to rotate or revoke. Last use tracks the credential. The recipient label is an administrative label.

The OpenShare app owns the token lifecycle. Publishers generate tokens, download profiles, view status, rotate tokens, and revoke access entirely within the app in Splunk Web. The app manages OpenShare credentials through its own permission-checked backend. The companion service enforces the app's grants on recipient requests.

### Authentication

- Publishers sign in through Splunk Web. The app checks the publisher's role and share ownership before issuing, rotating, or revoking a recipient credential.
- The app issues an OpenShare-specific opaque bearer token for one recipient grant and one share. The downloaded OpenSharing profile includes `shareCredentialsVersion`, the HTTPS `endpoint`, the `bearerToken`, and `expirationTime`. The client's HTTPS requests send the token in the Authorization header. The sharing service verifies the token and checks its grant, expiry, and revocation status before returning metadata or download URLs. [OpenSharing profile specification](https://github.com/OpenSharing-IO/OpenSharing/blob/main/spec/protocols/OVERVIEW.md)
- The credential is accepted only by the sharing service. Recipients need no Splunk account, and the profile grants read access only to the published table. Rotation issues a replacement profile and invalidates the previous token for new requests. Previously issued file URLs follow the same expiration bound as revocation.

### Publishing and access

- A share contains one table. Multiple recipients can have independently revocable grants to that table. A recipient can discover and read only the table granted by their profile.
- Run preview and extraction under the publisher's effective Splunk permissions, including index restrictions, role search filters, and report ACLs. Avoid dispatch modes that run with elevated or report-owner privileges. Block reports whose results cannot be safely produced under the publisher's permissions.
- Use an explicit field allowlist before transferring results to the companion service. Apply finite search runtime, time range, row, and output size limits on the server. Fail publication on partial or truncated results, unsupported field types, or materialization errors. Keep an active snapshot available if a replacement fails.
- Use explicit publishing permissions separate from ordinary Splunk search access. Limit share management to its publisher and app administrators. Removing source permissions blocks subsequent snapshots. Already published snapshots have their own grants and must be disabled or revoked through the app.
- Require TLS for the sharing endpoint and file delivery. Store bearer token verifiers and show token material only at issuance. Apply expiration and revocation to discovery, metadata, and data requests. Keep the private snapshot store inaccessible except through authorized file delivery.
- Audit publication, refresh, grant creation, rotation, revocation, disablement, and successful or denied read requests. Record the actor or resolved recipient, share, timestamp, and outcome where available. Exclude bearer tokens, download URLs, and row contents from audit logs.

### Serving model

Package the Splunk UI and publishing controls as an installable app. Deploy a companion sharing service for the external OpenSharing API and private snapshot delivery. The app sends bounded, field-selected results to the service for Parquet materialization. The publisher previews that snapshot before activating it, and recipients connect to the service over HTTPS. Recipient requests never trigger Splunk searches or require access to Splunk Web or the management API. Target OpenSharing table discovery, metadata, and latest-snapshot reads using URL-based access with Parquet responses. Verify routes, response fields, and capability negotiation against the pinned specification and client during the prototype. [OpenSharing table specification](https://github.com/OpenSharing-IO/OpenSharing/blob/main/spec/protocols/TABLES.md)

Proposed starting limits for the local pilot are a seven-day maximum search window, 50,000 rows, 100 MB of exported data, a two-minute search timeout, and seven-day recipient grants by default. Validate these defaults with representative reports. Expire unpublished previews, clean up retired snapshots after the file URL lifetime, and remove disabled share data according to the configured retention window.

**Revocation shown in the UI.** Revoking access blocks new protocol requests immediately. A previously issued file URL may still work for up to five minutes or until its earlier expiration. Recipients retain copies they already downloaded. Cap file URL lifetime at the remaining grant lifetime.

### Recipient endpoints and network handoff

Use **recipient** for the person or team receiving access and **OpenSharing client** for the software making requests. Clients use OpenSharing over HTTPS. The profile supplies the API base URL and bearer token. The API returns short-lived download URLs for the authorized Parquet files. [OpenSharing table specification](https://github.com/OpenSharing-IO/OpenSharing/blob/main/spec/protocols/TABLES.md)

Proposed MVP deployment uses one dedicated recipient hostname and TCP port 443. The HTTPS reverse proxy routes only the supported method and path pairs to the companion service. Keep Splunk Web, the Splunk management API, the publishing API, and backing storage on private routes. File URLs use the same recipient hostname and do not redirect to another host.

| Request | Example path on `share.example.com:443` |
| --- | --- |
| Discover authorized shares and tables | `GET /open-sharing/shares` and supported discovery routes beneath it |
| Read table metadata | `GET /open-sharing/shares/{share}/schemas/{schema}/tables/{table}/metadata` |
| Request snapshot files | `POST /open-sharing/shares/{share}/schemas/{schema}/tables/{table}/query` |
| Download a file | `GET /open-sharing/files/{signed-id}` |

The routes above illustrate the flow. Pin the client and verify the exact discovery, version, and file methods it uses, including any HEAD and range requests. Generate the handoff from the actual gateway route configuration.

Add **Settings → Network Access** with a copyable handoff showing the configured profile endpoint, destination hostname, TCP port, allowed HTTP methods and paths, and the source CIDRs to allow when applicable. Include DNS and TLS requirements and a token-free connectivity check using the discovery route. The check should explain that an authentication response confirms the route is reachable and that an authorized client read verifies data delivery. Keep credentials and signed file URLs out of the handoff. Firewalls can restrict host or IP and port. Apply URL path and method restrictions at the HTTPS reverse proxy or an application-layer firewall that can inspect the request.

### Scope for the first release

Support one standalone Splunk Enterprise deployment, manual snapshot publishing and refresh, and one validated OpenSharing-compatible Python connector version. Defer Iceberg catalog access, directory-based access, volumes, models, and agent skills. Defer scheduled refresh, streaming, change data feed, history queries, SSO, per-recipient row rules, clustered deployments, and Splunkbase distribution. An LM Studio demo can summarize the published synthetic table after the client reads it successfully.

## Local validation and release criteria

Run a pinned Splunk Enterprise container with synthetic events and a saved aggregate report. Run the companion service on the same machine and read it from a separate Python client process. Use the generated profile with the table listing and pandas read APIs of the Python connector listed by OpenSharing. Its package is currently named `delta-sharing`. [OpenSharing connectors](https://github.com/OpenSharing-IO/OpenSharing#connectors)

- Install the packaged app on a clean instance and publish both the index and report examples from the UI. Verify the stock client can discover and read each table and that rows, fields, and types match its approved snapshot.
- Verify a publisher without the required permissions cannot export restricted data. Verify a recipient profile cannot list or directly request another share. Confirm omitted fields, including an unselected `_raw`, are absent from the downloaded files.
- Verify expired, revoked, and rotated credentials cannot discover or fetch new data. Confirm issued file URLs stop working within the displayed bound and the private backing files cannot be fetched directly.
- Complete token generation, profile download, status review, rotation, and revocation using only the OpenShare app in Splunk Web.
- Run the pinned client from a separate network with access only to the documented HTTPS ingress. Verify discovery and Parquet downloads work on the same hostname and that recipient ingress serves only documented method and path pairs.
- Verify a successful refresh swaps the table contents and a failed or oversized refresh preserves the previous snapshot. Confirm publish, read, and revoke are traceable in the audit view.
- Have a Splunk administrator follow the setup instructions and complete install, publish, client read, and revoke in 15 minutes after the containers are ready. Ask them to identify what was shared, who could read it, and when revocation takes effect from the UI alone.

## Decisions for the prototype

- Pin the Splunk Enterprise build, OpenSharing specification revision, and Python connector version for the first support matrix.
- Validate saved report execution under the publisher's permissions. Offer index publishing while report shapes that depend on owner context are evaluated.
- Confirm that customers can deploy a companion service with recipient-reachable TLS. This is the main deployment tradeoff against a single-package app experience.

## Implementation research

### Splunk Python and libraries

| Component | Proposed dependencies | Rationale |
| --- | --- | --- |
| Splunk app | Python standard library and authenticated Splunk REST handlers. Optional pinned `splunk-sdk` (`splunklib`) for search and saved-report calls. | Keep search authorization and publishing controls in Splunk. Splunk Enterprise 10.6 defaults to Python 3.9 and allows custom REST handlers to select 3.13 using `python.required`. The SDK repository currently lists Python 3.13 or newer. If using the SDK, pin and test a compatible release and vendor dependencies in the app's `bin/lib`. [Splunk 10.6 Python guidance](https://help.splunk.com/en/splunk-enterprise/administer/install-and-upgrade/10.6/upgrade-or-migrate-splunk-enterprise/about-upgrading-to-10.6-read-this-first) [Splunk Python SDK](https://github.com/splunk/splunk-sdk-python) |
| Sharing service | Standalone Python 3.13, FastAPI and Uvicorn, PyArrow for Parquet, SQLite for grant state in the single-instance pilot, and a TLS gateway. | Keep native dependencies and download traffic outside the Splunk runtime. PyArrow includes native libraries and its current releases require Python 3.11 or newer. Validate the image and wheel architecture. [PyArrow installation](https://arrow.apache.org/docs/python/install.html) [FastAPI container deployment](https://fastapi.tiangolo.com/deployment/docker/) |
| Recipient test | The OpenSharing-listed Python connector (`delta-sharing`) in a separate environment. | Test discovery and file downloads with an independent client. The historical reference server is useful as a comparison during protocol tests. Its project documentation describes it as a test implementation and configures it with Delta Lake tables. [OpenSharing connectors](https://github.com/OpenSharing-IO/OpenSharing#connectors) [Reference server](https://github.com/delta-io/delta-sharing#delta-sharing-reference-server) |

### What Splunk can serve

Splunk supports authenticated custom REST endpoints in `splunkd` through `restmap.conf`, including persistent Python handlers. The app can selectively expose endpoints to its own Splunk Web UI through `web.conf` and retain CSRF protection. Keep `requireAuthentication` enabled and check publishing capability and share ownership server-side. Use the authenticated user's session for local search calls, leave `passSystemAuth` off, and verify that report dispatch uses the requesting user's context. [Splunk REST handler configuration](https://help.splunk.com/en/splunk-enterprise/administer/admin-manual/10.6/configuration-file-reference/10.6.0-configuration-file-reference/restmap.conf) [Splunk Web route configuration](https://help.splunk.com/en/splunk-enterprise/administer/admin-manual/10.6/configuration-file-reference/10.6.1-configuration-file-reference/web.conf) [Saved search dispatch API](https://help.splunk.com/en/splunk-enterprise/rest-api-reference/10.6/search-endpoints/search-endpoint-descriptions)

A custom handler can serve app HTTP requests. A Splunk-only recipient endpoint would need its own bearer validation and a gateway restricted to recipient paths. It would also need proof that the response and proxy stack handles OpenSharing status codes, headers, newline-delimited JSON and, if serving files there, binary and range responses under load. Splunk's documented native Delta Sharing settings refer to its Machine Data Lake integration. For the MVP, run the companion service on the same host or private network with a separate recipient hostname, TLS gateway, and private management listener. Splunk sends selected search results to that private listener and retains its own session credentials. Recipient reads continue from the published snapshot independently of Splunk availability. [Splunk server configuration](https://help.splunk.com/en/splunk-enterprise/administer/admin-manual/10.6/configuration-file-reference/10.6.0-configuration-file-reference/server.conf)

### Credential storage

- **Recipient bearer tokens.** Generate a high-entropy token in the app backend using Python's `secrets` module and return it in the profile once. Send only a verifier and grant metadata to the private sharing service. Store a SHA-256 digest of the randomly generated secret, with grant scope, expiry, and revocation state in the service database. Keep grant writes on the private management interface and enforce rotation and revocation with a single authoritative grant record. An app-initiated revoke is complete when that write commits.
- **App-to-service credential.** For a shared integration secret the app must recover to authenticate outbound calls, use Splunk's app-scoped `storage/passwords` store with a restricted ACL and local retrieval. Splunk encrypts the secret at rest with a key derived from `splunk.secret`. Authorized local API callers can retrieve plaintext. Keep the default network restriction, protect the host and backups, and test which identity can retrieve only the required credential. Publishers should use OpenShare controls under the app's publishing capability. If the app cannot retrieve the integration secret without granting publishers broad credential access, use deployment-provisioned mTLS for the private management interface. [Splunk credential access controls](https://help.splunk.com/en/splunk-enterprise/administer/manage-users-and-security/10.6/manage-credentials-and-keys/manage-credentials-used-by-apps-and-data-inputs) [Splunk credential REST API](https://help.splunk.com/en/splunk-enterprise/rest-api-reference/10.6/access-endpoints/access-endpoint-descriptions) [Splunk encryption key handling](https://help.splunk.com/en/splunk-enterprise/administer/manage-users-and-security/10.6/install-splunk-enterprise-securely/deploy-secure-passwords-across-multiple-servers)
- **Gateway and service keys.** Provision TLS and file-URL signing keys through the gateway or service deployment's secret mechanism. Give the recipient listener only the access it needs to verify grants and deliver approved files. Suppress Authorization headers and signed URL credentials in proxy, app, and service logs.

### First technical test

On the pinned Splunk container, confirm the handler's actual Python version and package imports. Publish a synthetic report as a restricted user and verify the result obeys that user's index permissions. Check that publishers can manage their shares while direct reads of the app-to-service credential are denied. From the recipient network, load the approved snapshot through the documented HTTPS routes, revoke access in Splunk Web, and verify the service rejects the next authenticated request. These are prototype checks pending execution.

## Logging controls

Add an administrator-only **Settings → Logging** page. Show the effective setting for each component and flag any component that has yet to apply a change.

| Toggle | Default | Effect |
| --- | --- | --- |
| Record recipient access audit | On | Record successful and denied recipient requests, including separate events for a snapshot query and a file transfer. Turning it off stops new per-request audit events and labels the affected interval in Activity. |
| Verbose diagnostics | Off | Temporarily include debug events and timing detail. Automatically revert after a displayed interval, initially 30 minutes. Keep ordinary warnings and errors available. |

Keep a baseline audit trail for share changes, credential issuance and revocation, and logging-setting changes. Record when a logging toggle changed and who changed it. Keep previously collected events subject to the configured retention policy. Apply the same redaction rules at every level, including to headers, signed URLs, and exported rows. Keep the audit index restricted to authorized roles. Log delivery issues appear as a health warning with an operation ID where available.

## Local development lab

Use one x86-64 Linux host with a Compose-compatible container runtime. Pin the official Splunk Enterprise 10.6 image and client and service dependencies. The official Splunk image requires license and General Terms acceptance at startup. Use the Enterprise trial for initial integration work. [Splunk container setup](https://help.splunk.com/en/splunk-enterprise/administer/install-and-upgrade/10.6/install-splunk-enterprise-in-virtual-and-containerized-environments/deploy-and-run-splunk-enterprise-inside-a-docker-container) [Splunk trial license](https://help.splunk.com/en/splunk-enterprise/administer/admin-manual/10.6/start-splunk-enterprise-and-perform-initial-tasks/install-your-license)

- **Splunk Enterprise.** Install the OpenShare app. Bind Splunk Web to host loopback for operator access and keep management and audit ingestion on the private network. Seed an allowed index, a restricted index, and an aggregate saved report. Create an admin and a limited publisher. Include synthetic sensitive fields to test column exclusion.
- **Companion and HTTPS gateway.** Use private storage and persistent grant state. Give the gateway a dedicated lab hostname and a lab CA trusted by the recipient client. Expose only the OpenSharing routes to the recipient network. Keep snapshot publication and grant management private. The lab mirrors audit events into the dedicated Splunk index over a read-only monitored volume. Activity reads the committed audit events from the companion service.
- **Recipient client.** Run the stock Python connector on a second container network that reaches only the gateway. Test profile download, table discovery, data reads, and revocation. Check that the client cannot reach Splunk Web, the management API, or private service routes. LM Studio can be added after this workflow passes.

The first demo is a single round trip. Publish the synthetic report as the limited publisher, download the profile, read the approved snapshot from the recipient container, find the download in Activity, revoke access, and verify the next authenticated request fails. Repeat with recipient audit disabled and diagnostics enabled to confirm the controls and redaction behavior.
