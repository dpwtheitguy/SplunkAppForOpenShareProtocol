"""Service behavior using a fresh SQLite database and Parquet volume per test."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyarrow.parquet as parquet
from fastapi import HTTPException
from starlette.requests import Request

import server


class SharingTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.enterContext(patch.object(server, "root", self.root))
        self.enterContext(patch.object(server, "epoch", return_value=1_800_000_000))
        server.initialize_database()

    def act(self, action, *, actor="alice", admin=False, **values):
        return server.manage_action({"action": action, "actor": actor, "admin": admin, **values})

    def stage(self, **overrides):
        return self.act("stage", **{
            "name": "Incident review",
            "source": "lab_events",
            "sourceType": "index",
            "fields": ["service", "error_count"],
            "rows": [{"service": "billing", "error_count": "3", "secret": "omit"}],
            **overrides,
        })

    def publish(self):
        share = self.stage()["id"]
        self.act("publish", snapshot=share)
        return share

    def issue(self, share, token="sample-test-token"):
        return self.act("issue", snapshot=share, label="On-call", days=1,
                        verifier=hashlib.sha256(token.encode()).hexdigest())

    def bearer(self, token="sample-test-token"):
        return Request({"type": "http", "headers": [(b"authorization", ("Bearer " + token).encode())]})

    def test_parquet_contains_only_approved_columns(self):
        draft = self.stage()
        saved = parquet.read_table(self.root / (draft["id"] + ".parquet"))
        self.assertEqual(saved.column_names, ["service", "error_count"])
        self.assertEqual(saved.to_pylist(), [{"service": "billing", "error_count": "3"}])
        self.assertEqual(draft["sample"], saved.to_pylist())

    def test_duplicate_fields_are_rejected_before_writing(self):
        with self.assertRaises(HTTPException) as error:
            self.stage(fields=["service", "service"])
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(list(self.root.glob("*.parquet")), [])

    def test_unpublished_snapshot_cannot_issue_grant(self):
        with self.assertRaises(HTTPException) as error:
            self.issue(self.stage()["id"])
        self.assertEqual(error.exception.status_code, 409)

    def test_only_owner_or_admin_can_manage_a_share(self):
        share = self.publish()
        with self.assertRaises(HTTPException) as error:
            self.act("disable", actor="bob", snapshot=share)
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.act("list", actor="bob")["shares"], [])
        self.act("disable", actor="admin", admin=True, snapshot=share)
        self.assertEqual(self.act("list")["shares"], [])

    def test_recipient_is_limited_to_granted_table(self):
        share = self.publish()
        other = self.publish()
        self.issue(share)
        self.assertEqual(server.authorized(self.bearer(), share, "data", "snapshot")["id"], share)
        with self.assertRaises(HTTPException) as error:
            server.authorized(self.bearer(), other)
        self.assertEqual(error.exception.status_code, 404)

    def test_expired_grant_is_denied(self):
        share = self.publish()
        self.issue(share)
        with patch.object(server, "epoch", return_value=1_800_086_400):
            with self.assertRaises(HTTPException) as error:
                server.authorized(self.bearer(), share)
        self.assertEqual(error.exception.status_code, 401)

    def test_rotate_replaces_old_token_and_revocation_denies_new_token(self):
        share = self.publish()
        self.issue(share)
        grant = self.act("list")["grants"][0]["id"]
        self.act("rotate", snapshot=share, grant=grant, days=2,
                 verifier=hashlib.sha256(b"replacement").hexdigest())
        with self.assertRaises(HTTPException) as error:
            server.authorized(self.bearer())
        self.assertEqual(error.exception.status_code, 401)
        rotated = server.authorized(self.bearer("replacement"))
        self.act("revoke", snapshot=share, grant=rotated["grant_id"])
        with self.assertRaises(HTTPException) as error:
            server.authorized(self.bearer("replacement"))
        self.assertEqual(error.exception.status_code, 401)

    def test_stale_refresh_cannot_replace_newer_snapshot(self):
        share = self.publish()
        self.issue(share)
        first = self.stage(replacement_for=share, base_version=0)
        stale = self.stage(replacement_for=share, base_version=0)
        self.act("publish", snapshot=first["id"])
        with self.assertRaises(HTTPException) as error:
            self.act("publish", snapshot=stale["id"])
        self.assertEqual(error.exception.status_code, 409)
        live = server.authorized(self.bearer(), share)
        self.assertEqual((live["active_file"], live["version"]), (first["id"], 1))

    def test_audit_toggle_drops_recipient_events_and_keeps_mutation_history(self):
        share = self.publish()
        self.issue(share)
        with self.assertRaises(HTTPException) as error:
            self.act("logging", access_audit=False, verbose=True)
        self.assertEqual(error.exception.status_code, 403)
        self.act("logging", admin=True, access_audit=False, verbose=True)
        with self.assertRaises(HTTPException):
            server.authorized(self.bearer("invalid"), share)
        state = self.act("list", admin=True)
        self.assertEqual(state["settings"]["debug_until"], 1_800_001_800)
        events = {item["event"] for item in state["activity"]}
        self.assertIn("recipient_audit_disabled", events)
        self.assertIn("grant_issued", events)
        self.assertNotIn("recipient_denied", events)

    def test_download_signature_cannot_be_reused_for_other_grants_or_after_expiry(self):
        share = self.publish()
        expires = 1_800_000_300
        signature = server.sign(share, "grant-a", expires)
        request = Request({"type": "http", "method": "HEAD"})
        self.assertEqual(server.download(share, "grant-a", expires, signature, request).status_code, 200)
        with self.assertRaises(HTTPException):
            server.download(share, "grant-b", expires, signature, request)
        with patch.object(server, "epoch", return_value=expires):
            with self.assertRaises(HTTPException):
                server.download(share, "grant-a", expires, signature, request)
