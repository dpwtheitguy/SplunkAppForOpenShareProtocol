"""Map committed OpenShare audit events to OCSF 1.7.0 API Activity."""

ACTIVITIES = {
    "share_published": (1, "Create"),
    "grant_issued": (1, "Create"),
    "snapshot_requested": (2, "Read"),
    "file_served": (2, "Read"),
    "recipient_denied": (2, "Read"),
    "grant_revoked": (3, "Update"),
    "grant_rotated": (3, "Update"),
    "share_refreshed": (3, "Update"),
    "share_disabled": (3, "Update"),
    "recipient_audit_enabled": (3, "Update"),
    "recipient_audit_disabled": (3, "Update"),
    "verbose_diagnostics_enabled": (3, "Update"),
    "verbose_diagnostics_disabled": (3, "Update"),
    "logging_settings_changed": (3, "Update"),
}


def api_activity(row, installation):
    operation = row["event"]
    activity, label = ACTIVITIES.get(operation, (99, "Other"))
    denied = operation == "recipient_denied"
    principal = {"name": row["actor"]} if row["actor"] else {"type_id": 0}
    source = {"ip": row["source_ip"]} if row["source_ip"] else {"type_id": 0}
    event = {
        "time": row["ts"] * 1000,
        "category_uid": 6,
        "class_uid": 6003,
        "type_uid": 600300 + activity,
        "activity_id": activity,
        "activity_name": label,
        "severity_id": 2 if denied else 1,
        "status_id": 2 if denied else 1,
        "metadata": {
            "version": "1.7.0",
            "product": {"name": "OpenShare"},
            "uid": f"{installation}:{row['event_id']}",
        },
        "actor": {"user": principal},
        "src_endpoint": source,
        "api": {"operation": operation, "service": {"name": "OpenShare"}},
    }
    if row["snapshot"]:
        event["resources"] = [{"uid": row["snapshot"], "type": "OpenShare Share"}]
    unmapped = {}
    if row["grant_id"]:
        unmapped["grant_id"] = row["grant_id"]
    if row["request_id"]:
        unmapped["request_id"] = row["request_id"]
    if unmapped:
        event["unmapped"] = unmapped
    return event
