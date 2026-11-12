"""Run after the declarations in seed.py inside Splunk."""
def manage(token, action, **kwargs):
    return request("/services/openshare/manage",
                   {"request": json.dumps({"action": action, **kwargs})}, token)


def check():
    token = login("openshare_publisher", os.environ["PUBLISHER_PASSWORD"])
    sources = manage(token, "sources")
    assert "openshare_lab" in sources["indexes"]
    assert any(report["name"] == "OpenShare Lab Errors by Service" for report in sources["reports"])
    for source_type, source in (
        ("index", "openshare_restricted"),
        ("report", "OpenShare Lab Restricted Report"),
    ):
        try:
            restricted = manage(token, "stage", sourceType=source_type, source=source,
                                app="openshare", reportOwner="admin", window="24h",
                                name="Restricted check", fields=["service"])
        except RuntimeError as error:
            assert ": 403 " in str(error), error
        else:
            assert restricted["rows"] == 0, restricted
    print("Restricted index and report did not expose rows.")
    try:
        manage(token, "logging", access_audit=False, verbose=True)
    except RuntimeError as error:
        assert ": 403 " in str(error), error
    else:
        raise AssertionError("A publisher modified administrator logging settings")
    print("Publisher permission checks passed.")


check()
