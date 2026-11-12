"""Read the single table granted to the isolated recipient."""

import json
import sys

import delta_sharing

PROFILE = "/recipient/profile.share"
MAX_ROWS = 100
MAX_BYTES = 10_000


class SnapshotError(Exception):
    """A reader error that is safe to show without connector details."""


def main():
    client = delta_sharing.SharingClient(PROFILE)
    tables = client.list_all_tables()
    if len(tables) != 1:
        raise SnapshotError("The lab expects a profile scoped to one table.")
    table = tables[0]
    name = f"{table.share}.{table.schema}.{table.name}"
    frame = delta_sharing.load_as_pandas(f"{PROFILE}#{name}", limit=MAX_ROWS + 1)
    if len(frame) > MAX_ROWS:
        raise SnapshotError(f"Publish an aggregate with at most {MAX_ROWS} rows for this demo.")
    payload = json.dumps(
        {
            "table": name,
            "columns": list(frame.columns),
            "rows": json.loads(frame.to_json(orient="records")),
        },
        ensure_ascii=False,
    )
    if len(payload.encode()) > MAX_BYTES:
        raise SnapshotError("The snapshot is too large for the lab's local-model context.")
    print(payload)


if __name__ == "__main__":
    try:
        main()
    except SnapshotError as error:
        sys.exit(str(error))
    except Exception:
        sys.exit("OpenSharing read failed. Check the share, profile expiry, and gateway.")
