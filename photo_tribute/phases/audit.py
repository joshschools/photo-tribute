"""Phase 1: Fetch metadata from both services, match assets, identify date mismatches."""

from datetime import datetime, timezone, timedelta
from typing import Optional
import requests

from photo_tribute.state import State, AssetRecord, AssetStatus

GPHOTOS_BASE = "https://photoslibrary.googleapis.com/v1"

# Tolerance window — dates within this are considered matching
DATE_TOLERANCE = timedelta(minutes=1)


def _gphotos_headers(creds) -> dict:
    creds.refresh(requests.Request()) if creds.expired else None
    return {"Authorization": f"Bearer {creds.token}"}


def fetch_recent_google_items(creds, days: int = 10) -> list[dict]:
    """Fetch all Google Photos items added within the last `days` days.

    Items are returned newest-first via mediaItems.list pagination; we stop
    once we've passed the cutoff so we don't scan the whole library.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    headers = _gphotos_headers(creds)
    items = []
    page_token: Optional[str] = None

    while True:
        params = {"pageSize": 100}
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(f"{GPHOTOS_BASE}/mediaItems", headers=headers, params=params)
        resp.raise_for_status()
        body = resp.json()

        for item in body.get("mediaItems", []):
            creation_time = datetime.fromisoformat(
                item["mediaMetadata"]["creationTime"].replace("Z", "+00:00")
            )
            # Google Photos returns in upload order (newest first).
            # creationTime here is what Google *thinks* it is — likely the
            # wrong transfer date for migrated items.
            if creation_time < cutoff:
                return items
            items.append(item)

        page_token = body.get("nextPageToken")
        if not page_token:
            break

    return items


def fetch_icloud_assets(api, days: int = 10) -> list:
    """Fetch all iCloud photo assets with their original capture dates."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days * 10)
    assets = []
    for asset in api.photos.all:
        # asset.asset_date is the EXIF capture date (the ground truth we want)
        if asset.asset_date and asset.asset_date.replace(tzinfo=timezone.utc) < cutoff:
            break
        assets.append(asset)
    return assets


def match_assets(
    google_items: list[dict],
    icloud_assets: list,
) -> list[tuple[dict, object]]:
    """Match Google items to iCloud assets by filename.

    Returns a list of (google_item, icloud_asset) pairs.
    Unmatched items on either side are silently skipped — logged separately.
    """
    icloud_by_name = {a.filename: a for a in icloud_assets}
    matched = []
    unmatched_google = []

    for item in google_items:
        asset = icloud_by_name.get(item["filename"])
        if asset:
            matched.append((item, asset))
        else:
            unmatched_google.append(item["filename"])

    if unmatched_google:
        print(f"  {len(unmatched_google)} Google items had no iCloud match (filename mismatch).")

    return matched


def run_audit(creds, icloud_api, days: int = 10) -> State:
    """Run the full audit phase and return a populated State."""
    print(f"Fetching Google Photos items from the last {days} days...")
    google_items = fetch_recent_google_items(creds, days=days)
    print(f"  Found {len(google_items)} Google items.")

    print("Fetching iCloud assets...")
    icloud_assets = fetch_icloud_assets(icloud_api, days=days)
    print(f"  Found {len(icloud_assets)} iCloud assets in window.")

    print("Matching assets by filename...")
    pairs = match_assets(google_items, icloud_assets)
    print(f"  Matched {len(pairs)} pairs.")

    state = State.load()
    mismatches = 0

    for g_item, i_asset in pairs:
        g_date = datetime.fromisoformat(
            g_item["mediaMetadata"]["creationTime"].replace("Z", "+00:00")
        )
        i_date = i_asset.asset_date.replace(tzinfo=timezone.utc)

        if abs(g_date - i_date) <= DATE_TOLERANCE:
            continue  # dates already agree

        mismatches += 1
        record = AssetRecord(
            icloud_id=i_asset.id,
            filename=i_asset.filename,
            icloud_date=i_date.isoformat(),
            google_id=g_item["id"],
            google_date=g_date.isoformat(),
            status=AssetStatus.PENDING,
        )
        state.upsert(record)

    state.save()
    print(f"\nAudit complete. {mismatches} mismatched assets written to state.json.")
    return state
