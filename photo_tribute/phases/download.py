"""Phase 2: Download mismatched assets from iCloud via icloudpd."""

import subprocess
from pathlib import Path

from photo_tribute.state import State, AssetStatus

STAGING_DIR = Path("staging")


def run_download(icloud_username: str, icloud_password: str | None = None) -> None:
    """Download all PENDING assets from iCloud into the staging directory."""
    state = State.load()
    pending = state.by_status(AssetStatus.PENDING)

    if not pending:
        print("No pending assets to download.")
        return

    print(f"Downloading {len(pending)} assets from iCloud...")
    STAGING_DIR.mkdir(exist_ok=True)

    # icloudpd downloads by album/folder, not individual asset IDs.
    # We download the full recent window into staging and then filter locally.
    cmd = [
        "icloudpd",
        "--directory", str(STAGING_DIR),
        "--username", icloud_username,
        "--set-exif-datetime",       # write DateTimeOriginal from asset capture date
        "--skip-live-photos",        # keep image + video separate for now
        "--recent", str(len(pending) + 50),  # small buffer for misses
        "--until-found", "20",       # stop after 20 consecutive already-present files
        "--no-progress-bar",
    ]

    if icloud_password:
        cmd += ["--password", icloud_password]

    # Session cookie is picked up automatically from .icloud-session/ by pyicloud-ipd
    cmd += ["--cookie-directory", ".icloud-session"]

    result = subprocess.run(cmd, check=False)

    if result.returncode != 0:
        print(f"icloudpd exited with code {result.returncode}. Check output above.")

    # Map downloaded files back to state records by filename
    downloaded_files = {f.name: f for f in STAGING_DIR.rglob("*") if f.is_file()}
    matched = 0

    for record in pending:
        local = downloaded_files.get(record.filename)
        if local:
            record.local_path = str(local)
            record.status = AssetStatus.DOWNLOADED
            state.upsert(record)
            matched += 1
        else:
            record.error = "File not found in staging after icloudpd run"
            record.status = AssetStatus.FAILED
            state.upsert(record)

    state.save()
    print(f"Download phase complete. {matched}/{len(pending)} files located in staging.")
