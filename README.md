# OpenShare for Splunk Enterprise

Publish a read-only table from a Splunk Enterprise index or saved report. Choose the fields and time window in Splunk Web, preview the snapshot, and issue an expiring OpenSharing profile. Recipients read the published data over HTTPS with a standard client. They need only the profile and access to the OpenShare gateway.

**[Download OpenShare 0.2.0 (.spl)](https://raw.githubusercontent.com/dpwtheitguy/SplunkAppForOpenShareProtocol/main/packages/openshare-0.2.0.spl)** · [SHA-256 checksum](packages/openshare-0.2.0.spl.sha256) · [Install on Splunk Enterprise](#install-on-splunk-enterprise) · [Run the Docker lab](#run-the-docker-lab)

Tested on standalone Splunk Enterprise 10.6.1 on Linux. The Splunk package provides the publisher UI and requires a separately deployed OpenShare companion service. Splunk Cloud Platform has not been validated.

## See it work

**Publish from Splunk Web.** The publisher reviews the exact columns and a sample of the snapshot before making it available.

![Splunk Web preview of the Service errors demo share with service and error count columns](docs/images/publish-preview.png)

**Read from the recipient network.** In this lab run, a Python client on a separate Docker network discovered the authorized table and downloaded its Parquet data through the HTTPS gateway. LM Studio summarized the returned rows. After the share was disabled, the same profile received HTTP 401.

![Captured OpenSharing lab run showing the remote client command, returned Splunk rows, local model answer, and HTTP 401 after access was revoked](docs/images/recipient-query.png)

The demo uses synthetic billing and identity events. The recipient container has its own network on the same machine and reaches the lab only through the sharing gateway.

## Install on Splunk Enterprise

### 1. Deploy the companion service

Use the companion source from the same revision as the app. The companion stores grant state and Parquet snapshots in `/data`. Provision a persistent volume and two separate random secrets of at least 32 characters. Use the same integration key on the Splunk and companion hosts. Keep the file-signing key on the companion host.

```bash
docker build -t openshare-companion:0.2.0 ./service
docker volume create openshare-data
docker run -d --name openshare-companion --restart unless-stopped \
  -p 127.0.0.1:9000:9000 \
  -e ENDPOINT=https://share.example.com/open-sharing \
  -e OPENSHARE_KEY_FILE=/run/secrets/integration-key \
  -e FILE_KEY_FILE=/run/secrets/file-signing-key \
  --mount type=bind,source=/path/to/integration-key,target=/run/secrets/integration-key,readonly \
  --mount type=bind,source=/path/to/file-signing-key,target=/run/secrets/file-signing-key,readonly \
  --mount type=volume,source=openshare-data,target=/data \
  openshare-companion:0.2.0
```

Replace the hostname and secret paths with your deployment values. Terminate TLS at a gateway on the companion host. Route the published hostname’s OpenSharing discovery, table, and signed file routes to the loopback service. Use [the lab’s NGINX route rules](lab/nginx.conf) as a starting point and replace the lab hostname, port, certificate paths, and upstream address. Route `POST /private/manage` on a separate private HTTPS listener reachable only by Splunk. Use the configured hostname in the TLS certificate and exclude authorization headers and signed URLs from gateway logs.

### 2. Install and configure the Splunk app

With the archive and checksum in the same directory, run `sha256sum -c openshare-0.2.0.spl.sha256` before uploading.

1. In Splunk Web, go to **Apps → Manage Apps → Install app from file** and upload the versioned `.spl`. For an existing `openshare` install, choose **Upgrade app**.
2. On the Splunk host, create `$SPLUNK_HOME/etc/apps/openshare/local/openshare.conf` using the example below. The integration key file must be readable by the Splunk OS account and protected from other users. Use the private gateway URL without the `/private/manage` suffix.
3. Restart Splunk if prompted. Assign the `openshare_publish` capability to a Splunk search role that can read the intended indexes or saved reports. Open **OpenShare for Splunk Enterprise** from the app menu.

```ini
[companion]
url = https://openshare-private.example.com
key_file = /path/to/integration-key
ca_file = /path/to/private-ca.pem
```

Omit `ca_file` when the private certificate chains to the host’s trusted CA store. The app validates HTTPS certificates and hostnames. If it cannot load, check the private listener, CA trust, and the integration key file’s permissions. The lab’s HTTP override lives in its local configuration and is for the isolated Docker network.

### 3. Publish and consume

1. In **Shares**, select **Create share** and choose an index or saved report available to your role. Set the time window, select the columns, and review the preview before publishing.
2. Send the **Network guide** to your network engineer. Generate an expiring profile for the recipient and hand it off as a credential.
3. The recipient uses the profile with an OpenSharing client. See the Python example below. Use **Activity** to review reads, **Refresh** to publish updated results, and **Access Tokens** to rotate or revoke credentials.

For a Splunk audit index, mount or forward the companion’s optional audit export. The companion writes JSONL to `AUDIT_EXPORT_DIR` when that directory exists. Use the [lab monitor configuration](lab/splunk/inputs.conf) as a template and restrict access to the `openshare_audit` index. The Activity screen reads the companion’s audit state directly.

## Run the Docker lab

### 1. Start the lab

Use a Linux host with Docker Engine, the Docker Compose plugin, Git, OpenSSL, and curl. You need permission to run Docker and free loopback ports **8000** and **8443**. Review the Splunk license and General Terms before starting. The startup script passes the official image’s acceptance flags. [Splunk Enterprise container setup](https://help.splunk.com/en/splunk-enterprise/administer/install-and-upgrade/10.6/install-splunk-enterprise-in-virtual-and-containerized-environments/deploy-and-run-splunk-enterprise-inside-a-docker-container)

```bash
git clone https://github.com/dpwtheitguy/SplunkAppForOpenShareProtocol.git
cd SplunkAppForOpenShareProtocol
./lab/up.sh
```

The script generates lab credentials and TLS certificates, starts Splunk Enterprise 10.6.1 and the sharing service, installs the app, and seeds the synthetic indexes and reports. If you recently joined the Docker group and your current shell still has its old membership, use `sg docker -c './lab/up.sh'`.

### 2. Publish a share

Open [OpenShare in Splunk Web](http://127.0.0.1:8000/en-US/app/openshare/openshare). Sign in as `openshare_publisher` with the password generated for this checkout:

```bash
sed -n 's/^PUBLISHER_PASSWORD=//p' .lab/env
```

1. Select **Create share**, set **Source type** to **Saved report**, and choose **OpenShare Lab Errors by Service**.
2. Give the share a name, select the last 24 hours, and enter `service, error_count` in **Fields**.
3. Click **Preview snapshot**, review the columns and rows, and click **Publish snapshot**.
4. Copy the firewall and load balancer guide if needed. Then click **Generate profile** on the share, enter a recipient label and expiry, and download the profile.

To try the index workflow, choose `openshare_lab` and preview `source, sourcetype`. The limited publisher can read that index. The lab also seeds `openshare_restricted` to exercise Splunk’s role restrictions.

### 3. Read from the isolated client

Copy the downloaded profile to the lab’s recipient directory. Replace the example source path with the location of your download. The profile contains a bearer credential.

```bash
install -m 600 /path/to/downloaded/openshare.share .lab/recipient/profile.share
docker compose --env-file .lab/env --profile test build recipient
docker compose --env-file .lab/env --profile test run --rm recipient
```

The demo runner expects the **Errors by Service** report and prints the two approved columns. The client resolves `share.lab` on the isolated Docker network and trusts the lab CA mounted by Compose. For other shares, use the stock Python connector with the profile. [OpenSharing connectors](https://github.com/OpenSharing-IO/OpenSharing#connectors)

```python
import delta_sharing

profile = "/recipient/profile.share"
client = delta_sharing.SharingClient(profile)
table = client.list_all_tables()[0]
table_url = f"{profile}#{table.share}.{table.schema}.{table.name}"
print(delta_sharing.load_as_pandas(table_url).to_string(index=False))
```

### 4. Ask an LLM and test revocation

For a live question, load a tool-capable model in LM Studio and start its local server from the **Developer** tab on port 1234. With the profile saved at `.lab/recipient/profile.share`, run:

```bash
python3 lab/ask.py "Which service had the most errors, and how many?"
```

The default model ID is `gpt-oss-20b`. Pass `--model` to select another loaded model or `--profile-dir` for a different directory containing `profile.share`. If the local API requires authentication, set `LM_API_TOKEN` in your environment. The model calls `read_shared_snapshot` and the isolated client reads the latest authorized snapshot on each question. The demo accepts up to 100 rows and 10 KB of serialized data. [LM Studio local server](https://lmstudio.ai/docs/developer/core/server) [LM Studio tool calling](https://lmstudio.ai/docs/developer/openai-compat/tools)

You can also paste the returned table into LM Studio Chat:

> Which service had the most errors? Give the count and one limitation of the snapshot.

The model sees the approved rows. The Python client holds the profile and token. [LM Studio local chat](https://lmstudio.ai/docs/app/offline)

In OpenShare, **Activity** shows the snapshot request and file delivery. Revoke the recipient’s grant in **Access Tokens**, then check that the same profile receives HTTP 401:

```bash
docker compose --env-file .lab/env --profile test run --rm -e EXPECT_REVOKED=1 recipient
```

Previously issued file URLs can remain valid for up to five minutes, bounded by the grant’s expiration. Recipients retain files they already downloaded.

## Firewall and load balancer handoff

Publishing opens a copyable **Network guide**. Reopen it from the share’s row or use **Network Access** for the listener-wide route list. The guide gives network engineers the destination host and TCP port, allowed HTTP methods and paths, DNS and certificate requirements, and a token-free connectivity check. The copied handoff contains route templates for signed downloads.

The lab endpoint is `https://share.lab:8443/open-sharing`. A token-free request to `/open-sharing/shares` should return **HTTP 401** from a network that can resolve the hostname and trust the lab CA. Use a valid profile to verify data delivery. Keep Splunk Web, the Splunk management API, and OpenShare’s publishing endpoint on private routes.

![OpenShare’s firewall and load balancer guide showing the recipient hostname, port, allowed routes, and token-free connectivity check](docs/images/network-guide.png)

## How the lab fits together

```mermaid
flowchart LR
    P[Publisher] --> W[Splunk Web and OpenShare app]
    W -->|Approved snapshot and grant changes| S[Private sharing service]
    S --> D[(Parquet snapshots and grant state)]
    C[Recipient client] -->|HTTPS and sharing profile| G[OpenShare gateway]
    G -->|Table and file routes| S
    C -->|Approved rows| L[Optional local LLM]
```

| Surface | Lab access |
| --- | --- |
| Splunk Web | Host loopback, TCP 8000 |
| OpenShare HTTPS gateway | Host loopback, TCP 8443. The recipient network uses the `share.lab` alias. |
| Splunk management, publishing, and storage | Private Docker network or volumes |
| Recipient profile | A bearer credential scoped to one share. The service stores a SHA-256 verifier. |

Admins can use **Logging** to toggle recipient access auditing and enable verbose diagnostics for 30 minutes. The app keeps audit events for share and grant changes. To inspect the Splunk audit mirror, sign in as `admin` using `SPLUNK_PASSWORD` from `.lab/env` and run:

```spl
index=openshare_audit sourcetype=openshare:audit
```

## Verify and troubleshoot

```bash
./lab/test-unit.sh
./lab/verify.sh
```

Build the versioned app archive and run the release checks:

```bash
./scripts/package.sh
./scripts/check-package.sh
```

The build-tools container runs Ruff lint and formatting checks, Splunk Packaging Toolkit validation, and AppInspect in precert mode. The JSON report goes to `.lab/appinspect/report.json`. The lab installs the generated `.spl` with the Splunk CLI before the browser tests. Splunkbase publication requires its own submission and review. [Splunkbase release process](https://dev.splunk.com/enterprise/docs/releaseapps/splunkbase/)

The browser regression publishes an index and a report, checks permissions and the network guide, injects a billing event, verifies that refresh returns the changed count, and checks token rotation and revocation. It leaves screenshots in `.lab/test-artifacts/` and uses temporary profiles. For a manual refresh demo, add an event before clicking **Refresh** on the share:

```bash
docker compose --env-file .lab/env exec -T --user splunk splunk \
  /opt/splunk/bin/splunk cmd python - --append-billing < lab/seed.py
```

| Symptom | Check |
| --- | --- |
| Splunk Web is still starting | Run `docker compose --env-file .lab/env ps` and wait for Splunk to report healthy. |
| Recipient receives HTTP 401 | Confirm the profile is current and the share is enabled. Issue a fresh profile after rotation or revocation. |
| TLS or name resolution fails | Use the Compose recipient runner, which mounts the lab CA and resolves `share.lab` on the recipient network. |
| Demo reports are empty | Rerun `./lab/up.sh` to seed fresh synthetic events and use a time window that includes them. |

Stop the lab while retaining its Docker volumes:

```bash
docker compose --env-file .lab/env down
```

## MVP scope

OpenShare serves scalar string columns and one active snapshot per share. A refresh preserves active recipient grants. The lab uses a local CA, a deployment-mounted integration secret, and persistent local snapshot storage. A production deployment still needs private-link TLS, managed secrets, role and audit retention configuration, and automated snapshot retention.

The Splunk app is under [`app/openshare/`](app/openshare/), the OpenSharing provider is in [`service/`](service/), and the Docker lab and browser tests are in [`lab/`](lab/). See the [MVP PRD](PRD.md) for the design and acceptance criteria or [GitHub Issues](https://github.com/dpwtheitguy/SplunkAppForOpenShareProtocol/issues) for support.
