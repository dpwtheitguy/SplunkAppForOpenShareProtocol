"""Run inside the lab Splunk container."""

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = "https://127.0.0.1:8089"
TLS = ssl._create_unverified_context()  # noqa: S323 - lab Splunk loopback only.


def request(path, values=None, token=None, raw=None, existing=False):
    url = ROOT + path
    url += ("&" if "?" in url else "?") + "output_mode=json"
    data = (
        raw
        if raw is not None
        else None
        if values is None
        else urllib.parse.urlencode(values, doseq=True).encode()
    )
    headers = {"Authorization": "Splunk " + token} if token else {}
    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed loopback HTTPS origin.
            urllib.request.Request(url, data, headers),  # noqa: S310
            context=TLS,
            timeout=30,
        ) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode()
        if existing and (error.code == 409 or "already exists" in body.lower()):
            return None
        raise RuntimeError(f"{path}: {error.code} {body}") from None


def login(user, password):
    return request("/services/auth/login", {"username": user, "password": password})["sessionKey"]


def append_billing():
    token = login("admin", os.environ["SPLUNK_PASSWORD"])
    fixture_id = uuid.uuid4().hex
    event = f"service=billing status=error demo_sensitive=omit_me fixture_id={fixture_id}\n"
    request(
        "/services/receivers/simple?index=openshare_lab&sourcetype=openshare_lab",
        token=token,
        raw=event.encode(),
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = request(
            "/services/search/jobs",
            {
                "search": f"search index=openshare_lab fixture_id={fixture_id} | head 1",
                "earliest_time": "-1h",
                "exec_mode": "blocking",
            },
            token,
        )
        if request("/services/search/jobs/" + job["sid"] + "/results", token=token)["results"]:
            print("Indexed a new synthetic billing error for the refresh check.")
            return
        time.sleep(0.5)
    raise RuntimeError("The injected sample event was not searchable")


def seed():
    token = login("admin", os.environ["SPLUNK_PASSWORD"])
    for index in ("openshare_lab", "openshare_restricted"):
        request("/services/data/indexes", {"name": index}, token, existing=True)
        job = request(
            "/services/search/jobs",
            {
                "search": f"search index={index} | head 1",
                "earliest_time": "-1h",
                "exec_mode": "blocking",
            },
            token,
        )
        recent = request("/services/search/jobs/" + job["sid"] + "/results", token=token)
        if not recent["results"]:
            for service, count in (("billing", 3), ("identity", 2)):
                event = f"service={service} status=error demo_sensitive=omit_me\n"
                for _ in range(count):
                    request(
                        f"/services/receivers/simple?index={index}&sourcetype=openshare_lab",
                        token=token,
                        raw=event.encode(),
                    )
    request(
        "/services/authorization/roles",
        {
            "name": "openshare_lab_publisher",
            "capabilities": ["search", "openshare_publish"],
            "srchIndexesAllowed": "openshare_lab",
            "srchIndexesDefault": "openshare_lab",
        },
        token,
        existing=True,
    )
    publisher = {
        "password": os.environ["PUBLISHER_PASSWORD"],
        "roles": "openshare_lab_publisher",
    }
    created = request(
        "/services/authentication/users",
        {
            "name": "openshare_publisher",
            **publisher,
        },
        token,
        existing=True,
    )
    if created is None:
        request("/services/authentication/users/openshare_publisher", publisher, token)
    for name, index in (
        ("OpenShare Lab Errors by Service", "openshare_lab"),
        ("OpenShare Lab Restricted Report", "openshare_restricted"),
    ):
        path = "/servicesNS/admin/openshare/saved/searches"
        report = urllib.parse.quote(name, safe="")
        try:
            request("/servicesNS/nobody/openshare/saved/searches/" + report, token=token)
        except RuntimeError as error:
            if ": 404 " not in str(error):
                raise
        else:
            continue
        created = request(
            path,
            {
                "name": name,
                "search": f"index={index} | stats count as error_count by service",
                "dispatchAs": "user",
            },
            token,
            existing=True,
        )
        if created is not None:
            request(
                path + "/" + report + "/acl",
                {"sharing": "app", "owner": "admin", "perms.read": "*", "perms.write": "admin"},
                token,
            )
    print("Seeded lab indexes, saved reports, and limited publisher.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--append-billing"]:
        append_billing()
    else:
        seed()
