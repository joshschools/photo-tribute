"""Phase 2b: Use exiftool to ensure DateTimeOriginal is correct in all staged files.

Photos should already have correct EXIF from icloudpd --set-exif-datetime, but
video files (MOV/MP4) need explicit correction — icloudpd sets the filesystem
date, not the embedded metadata track date.
"""

import subprocess
from pathlib import Path

import exiftool

from photo_tribute.state import State, AssetStatus

VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi"}


def _fix_video_date(path: Path, correct_date: str) -> None:
    """Write the correct date into all relevant video metadata tracks."""
    # correct_date expected as ISO8601: 2023-07-14T15:32:00+00:00
    # exiftool wants: "YYYY:MM:DD HH:MM:SS"
    from datetime import datetime
    dt = datetime.fromisoformat(correct_date)
    exif_date = dt.strftime("%Y:%m:%d %H:%M:%S")

    subprocess.run(
        [
            "exiftool",
            f"-DateTimeOriginal={exif_date}",
            f"-CreateDate={exif_date}",
            f"-TrackCreateDate={exif_date}",
            f"-MediaCreateDate={exif_date}",
            "-overwrite_original",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def run_fix() -> None:
    """Fix EXIF dates on all DOWNLOADED assets, then advance to FIXED status."""
    state = State.load()
    to_fix = state.by_status(AssetStatus.DOWNLOADED)

    if not to_fix:
        print("No downloaded assets to fix.")
        return

    print(f"Fixing EXIF dates on {len(to_fix)} files...")

    with exiftool.ExifToolHelper() as et:
        for record in to_fix:
            path = Path(record.local_path)
            ext = path.suffix.lower()

            try:
                if ext in VIDEO_EXTENSIONS:
                    _fix_video_date(path, record.icloud_date)
                else:
                    # Verify photo EXIF is already correct; rewrite if not
                    meta = et.get_tags(str(path), ["EXIF:DateTimeOriginal"])
                    current = meta[0].get("EXIF:DateTimeOriginal", "")
                    from datetime import datetime
                    expected = datetime.fromisoformat(record.icloud_date).strftime("%Y:%m:%d %H:%M:%S")
                    if current != expected:
                        et.set_tags(
                            str(path),
                            {"DateTimeOriginal": expected},
                            params=["-overwrite_original"],
                        )

                record.status = AssetStatus.FIXED
            except Exception as exc:
                record.status = AssetStatus.FAILED
                record.error = str(exc)

            state.upsert(record)

    state.save()
    fixed = len(state.by_status(AssetStatus.FIXED))
    print(f"Fix phase complete. {fixed}/{len(to_fix)} files ready for upload.")
