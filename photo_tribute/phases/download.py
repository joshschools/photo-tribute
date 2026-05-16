"""Phase 2: Download assets from iCloud via icloudpd and build state from EXIF."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import exiftool

from photo_tribute.state import State, AssetRecord, AssetStatus

STAGING_DIR = Path("staging")


def _read_exif_date(path: Path, et: exiftool.ExifToolHelper) -> str | None:
    """Return DateTimeOriginal from file as ISO8601 string, or None."""
    try:
        meta = et.get_tags(str(path), ["EXIF:DateTimeOriginal", "QuickTime:CreateDate"])
        for tag in ("EXIF:DateTimeOriginal", "QuickTime:CreateDate"):
            val = meta[0].get(tag)
            if val:
                dt = datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                return dt.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        pass
    return None


def run_download(icloud_username: str, icloud_password: str | None = None, days: int = 15) -> None:
    """Download iCloud assets for the given window and populate state.json."""
    STAGING_DIR.mkdir(exist_ok=True)

    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    cmd = [
        "icloudpd",
        "--directory", str(STAGING_DIR),
        "--username", icloud_username,
        "--cookie-directory", ".icloud-session",
        "--set-exif-datetime",
        "--skip-live-photos",
        "--folder-structure", "none",       # flat directory — easier to scan
        "--skip-created-before", cutoff,
        "--no-progress-bar",
    ]

    if icloud_password:
        cmd += ["--password", icloud_password]

    print(f"Downloading iCloud assets created since {cutoff}...")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"icloudpd exited with code {result.returncode}.")

    # Build state from whatever landed in staging
    print("Reading EXIF dates from downloaded files...")
    state = State.load()
    new_count = 0

    with exiftool.ExifToolHelper() as et:
        for path in sorted(STAGING_DIR.iterdir()):
            if not path.is_file():
                continue

            # Use filename as a stable key (no iCloud asset ID available via CLI)
            asset_key = path.name
            if asset_key in {r.icloud_id for r in state.assets.values()}:
                continue  # already tracked

            icloud_date = _read_exif_date(path, et) or ""

            record = AssetRecord(
                icloud_id=asset_key,
                filename=path.name,
                icloud_date=icloud_date,
                google_id="",
                google_date="",
                status=AssetStatus.DOWNLOADED,
                local_path=str(path),
            )
            state.upsert(record)
            new_count += 1

    state.save()
    print(f"Download complete. {new_count} new files tracked (total: {len(state.assets)}).")
