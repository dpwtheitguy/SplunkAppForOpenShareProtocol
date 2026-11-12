"""Exercise the publisher workflow through the installed Splunk UI."""

import os
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

base = os.environ.get("WEB_BASE", "http://127.0.0.1:8000")
output = Path("/lab-output")
stage = os.environ.get("WEB_STAGE", "publish")

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 980})
    page.goto(base + "/en-US/account/login")
    admin = stage.startswith("logging")
    page.locator('input[name="username"]').fill("admin" if admin else "openshare_publisher")
    page.locator('input[name="password"]').fill(
        os.environ["SPLUNK_PASSWORD" if admin else "PUBLISHER_PASSWORD"]
    )
    page.locator('input[name="password"]').press("Enter")
    page.wait_for_url(lambda url: "/account/login" not in url)
    page.goto(base + "/en-US/app/openshare/openshare")
    expect(page.get_by_role("button", name="Create share")).to_be_visible(timeout=30000)
    if admin:
        page.locator("#openshare").get_by_role("button", name="Logging", exact=True).click()
        audit = page.get_by_label("Record recipient access audit")
        verbose = page.get_by_label("Verbose diagnostics for 30 minutes")
        if stage == "logging_enable_debug":
            audit.uncheck()
            verbose.check()
        else:
            audit.check()
            verbose.uncheck()
        page.get_by_role("button", name="Save logging settings").click()
        expect(page.get_by_text("Logging settings saved.")).to_be_visible()
        print("Changed both logging toggles through Splunk Web.")
    elif stage in {"publish", "index"}:
        expect(
            page.locator("#openshare").get_by_role("button", name="Logging", exact=True)
        ).to_have_count(0)
        is_index = stage == "index"
        name = ("Browser index " if is_index else "Browser report ") + str(int(time.time()))
        page.get_by_role("button", name="Create share").click()
        page.get_by_label("Source type").select_option("index" if is_index else "report")
        page.get_by_label("Source", exact=True).select_option(
            label="openshare_lab"
            if is_index
            else "OpenShare Lab Errors by Service (openshare / admin)"
        )
        page.get_by_label("Share name").fill(name)
        page.get_by_label("Fields (comma-separated)").fill(
            "source, sourcetype" if is_index else "service, error_count"
        )
        page.get_by_role("button", name="Preview snapshot").click()
        expect(page.get_by_role("heading", name="Review snapshot")).to_be_visible(timeout=30000)
        expect(
            page.get_by_role(
                "cell", name="openshare_lab" if is_index else "billing", exact=True
            ).first
        ).to_be_visible()
        expect(page.get_by_text("demo_sensitive", exact=False)).to_have_count(0)
        page.get_by_label("Share name").fill(name + " changed")
        expect(page.get_by_role("button", name="Publish snapshot")).to_have_count(0)
        page.get_by_label("Share name").fill(name)
        page.get_by_role("button", name="Preview snapshot").click()
        page.get_by_role("button", name="Publish snapshot").click()
        guide = page.locator(".os-network-guide")
        expect(
            guide.get_by_role("heading", name="Firewall and load balancer guide")
        ).to_be_visible()
        expect(guide.get_by_text("https://share.lab:8443/open-sharing", exact=True)).to_be_visible()
        expect(guide.get_by_text("HTTP 401", exact=False)).to_be_visible()
        guide.get_by_text("Allowed methods and paths", exact=True).click()
        expect(guide.get_by_role("cell", name="/open-sharing/shares", exact=True)).to_be_visible()
        expect(
            guide.get_by_role(
                "cell",
                name="/open-sharing/files/{snapshot}/{grant}/{expiry}/{signature}",
                exact=True,
            )
        ).to_be_visible()
        page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
        guide.get_by_role("button", name="Copy network guide").click()
        expect(page.get_by_text("Network guide copied.", exact=True)).to_be_visible()
        handoff = page.evaluate("navigator.clipboard.readText()")
        assert "share.lab on TCP 8443" in handoff
        assert "/schemas/data/tables/snapshot/query" in handoff
        assert "bearerToken" not in handoff
        if not is_index:
            guide.screenshot(path="/artifacts/openshare-network-guide.png")
        guide.get_by_role("button", name="Done", exact=True).click()
        row = page.get_by_role("row").filter(has_text=name)
        row.get_by_role("button", name="Network guide", exact=True).click()
        expect(guide.get_by_text("Network handoff for " + name, exact=True)).to_be_visible()
        guide.get_by_role("button", name="Done", exact=True).click()
        row.get_by_role("button", name="Generate profile").click()
        expect(page.get_by_role("dialog")).to_be_visible()
        page.get_by_label("Recipient label").fill(name)
        with page.expect_download() as download:
            page.get_by_role("button", name="Generate and download").click()
        download.value.save_as(output / "profile.share")
        (output / "profile.share").chmod(0o600)
        (output / "browser-share-name").write_text(name)
        print(
            "Published an index and downloaded its profile through Splunk Web."
            if is_index
            else "Published a report and downloaded its profile through Splunk Web."
        )
    elif stage == "refresh":
        name = (output / "browser-share-name").read_text()
        page.get_by_role("row").filter(has_text=name).get_by_role("button", name="Refresh").click()
        expect(page.get_by_role("heading", name="Review snapshot")).to_be_visible(timeout=30000)
        page.get_by_role("button", name="Publish replacement").click()
        expect(page.get_by_text("Snapshot refreshed.", exact=True)).to_be_visible()
        print("Refreshed the share in Splunk Web.")
    elif stage == "rotate":
        name = (output / "browser-share-name").read_text()
        page.get_by_role("button", name="Access Tokens", exact=True).click()
        row = page.get_by_role("row").filter(has_text=name).filter(has_text="Active")
        page.once("dialog", lambda dialog: dialog.accept())
        with page.expect_download() as download:
            row.get_by_role("button", name="Rotate").click()
        download.value.save_as(output / "rotated.share")
        (output / "rotated.share").chmod(0o600)
        expect(
            page.get_by_role("row").filter(has_text=name).filter(has_text="Revoked")
        ).to_have_count(1)
        print("Rotated the profile through Splunk Web.")
    elif stage == "layout":
        page.locator("#openshare").screenshot(path="/artifacts/openshare-shares.png")
        page.set_viewport_size({"width": 600, "height": 930})
        page.get_by_role("button", name="Create share").click()
        expect(page.get_by_label("Source", exact=True)).to_be_visible()
        bounds = page.locator("#openshare").bounding_box()
        assert bounds["x"] + bounds["width"] <= 600, bounds
        page.locator("#openshare").screenshot(path="/artifacts/openshare-create-narrow.png")
        print("Captured desktop and narrow layouts.")
    elif stage == "disable":
        name = (output / "browser-share-name").read_text()
        row = page.get_by_role("row").filter(has_text=name)
        page.once("dialog", lambda dialog: dialog.accept())
        row.get_by_role("button", name="Disable").click()
        expect(row).to_have_count(0)
        print("Disabled the test share through Splunk Web.")
    else:
        name = (output / "browser-share-name").read_text()
        page.locator("#openshare").get_by_role("button", name="Activity", exact=True).click()
        page.get_by_label("Share", exact=True).select_option(label=name)
        page.get_by_label("Event type", exact=True).select_option("file_served")
        expect(
            page.get_by_role("row").filter(has_text=name).filter(has_text="file served").first
        ).to_be_visible()
        page.get_by_role("button", name="Access Tokens", exact=True).click()
        page.once("dialog", lambda dialog: dialog.accept())
        row = page.get_by_role("row").filter(has_text=name).filter(has_text="Active")
        row.get_by_role("button", name="Revoke").click()
        expect(
            page.get_by_role("row").filter(has_text=name).filter(has_text="Revoked")
        ).to_have_count(2)
        print("Observed download activity and revoked the profile in Splunk Web.")
