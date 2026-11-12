import json
import os
import socket
from urllib.parse import urlsplit

import delta_sharing
import requests

profile = "/recipient/profile.share"
with open(profile) as file:
    credentials = json.load(file)
endpoint = credentials["endpoint"]
origin = urlsplit(endpoint)
for host in ("splunk", "sharing"):
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror:
        continue
    raise AssertionError(f"Private host {host} resolved on the recipient network")
assert (
    requests.get(f"{origin.scheme}://{origin.netloc}/private/manage", timeout=5).status_code == 404
)
assert requests.delete(endpoint + "/shares", timeout=5).status_code == 405
headers = {"Authorization": "Bearer " + credentials["bearerToken"]}
discovery = requests.get(endpoint + "/shares", headers=headers, timeout=5)
if os.getenv("EXPECT_REVOKED"):
    assert discovery.status_code == 401, discovery.status_code
    print("Revoked profile rejected with HTTP 401.")
    raise SystemExit(0)
discovery.raise_for_status()
client = delta_sharing.SharingClient(profile)
tables = client.list_all_tables()
assert len(tables) == 1, tables
table = tables[0]
frame = delta_sharing.load_as_pandas(f"{profile}#{table.share}.{table.schema}.{table.name}")
print(frame.to_string(index=False))
if os.getenv("EXPECT_INDEX"):
    assert list(frame.columns) == ["source", "sourcetype"]
    assert len(frame) and set(frame["sourcetype"]) == {"openshare_lab"}
    raise SystemExit(0)
assert list(frame.columns) == ["service", "error_count"]
assert set(frame["service"]) == {"billing", "identity"}
billing = int(frame.loc[frame["service"] == "billing", "error_count"].iloc[0])
print(f"billing_count={billing}")
if os.getenv("EXPECT_BILLING"):
    assert billing == int(os.environ["EXPECT_BILLING"])
if os.getenv("EXPECT_VERSION"):
    path = f"/shares/{table.share}/schemas/{table.schema}/tables/{table.name}/version"
    version = requests.get(endpoint + path, headers=headers, timeout=5)
    version.raise_for_status()
    assert version.headers["Delta-Table-Version"] == os.environ["EXPECT_VERSION"]
