"""Phase 1: Catalog iCloud assets within a date range and populate state.json.

The Google Photos Library API no longer allows reading a user's full library
(photoslibrary.readonly was removed April 1 2025). We skip the comparison step
entirely — since all photos in the migration window have wrong dates, we just
catalog what's in iCloud for that window and queue everything for fix + re-upload.
"""

from datetime import datetime, timezone, timedelta

from photo_tribute.state import State, AssetRecord, AssetStatus


def run_catalog(icloud_api, days: int) -> State:
    """Fetch iCloud assets added within `days` days and write them to state.json."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    print(f"Fetching iCloud assets added in the last {days} days...")
    state = State.load()
    found = 0

    for asset in icloud_api.photos.all:
        added = asset.added_date
        if added is None:
            continue

        if added.tzinfo is None:
            added = added.replace(tzinfo=timezone.utc)

        if added < cutoff:
            break  # photos.all is newest-first; stop once past the window

        capture = asset.asset_date
        if capture is None:
            continue
        if capture.tzinfo is None:
            capture = capture.replace(tzinfo=timezone.utc)

        # Skip assets already tracked (allows re-running audit safely)
        if asset.id in state.assets:
            continue

        record = AssetRecord(
            icloud_id=asset.id,
            filename=asset.filename,
            icloud_date=capture.isoformat(),
            google_id="",   # unknown — Google read API unavailable
            google_date="", # unknown
            status=AssetStatus.PENDING,
        )
        state.upsert(record)
        found += 1

    state.save()
    print(f"Catalog complete. {found} new assets queued (total tracked: {len(state.assets)}).")
    return state
