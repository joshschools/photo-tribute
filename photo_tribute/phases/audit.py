"""Phase 1: Summarise what will be downloaded from iCloud.

icloudpd 1.32+ ships as a compiled binary with no importable Python API.
The catalog phase does a dry-run list of files in the target date window
so the user can confirm scope before the real download starts.
"""

import subprocess
from datetime import datetime, timezone, timedelta


def run_catalog(icloud_username: str, icloud_password: str | None, days: int) -> list[str]:
    """Print the filenames that would be downloaded and return them as a list."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    cmd = [
        "icloudpd",
        "--directory", "/tmp/photo-tribute-catalog-probe",
        "--username", icloud_username,
        "--cookie-directory", ".icloud-session",
        "--only-print-filenames",
        "--skip-created-before", cutoff,
        "--folder-structure", "none",
        "--no-progress-bar",
    ]

    if icloud_password:
        cmd += ["--password", icloud_password]

    print(f"Listing iCloud assets created since {cutoff}...")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    filenames = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    print(f"Found {len(filenames)} assets to process.")
    if filenames:
        print("Sample (first 5):")
        for f in filenames[:5]:
            print(f"  {f}")

    return filenames
