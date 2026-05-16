"""Phase 3: Upload corrected files to Google Photos.

Google Photos API does not support updating creationTime on existing items,
so we upload fresh copies with correct EXIF dates. The old wrongly-dated items
must be deleted manually — the API only allows deleting app-created content,
not user-owned items migrated from iCloud.
"""

import mimetypes
from pathlib import Path

import requests
from tqdm import tqdm

from photo_tribute.state import State, AssetStatus

GPHOTOS_UPLOAD_URL = "https://photoslibrary.googleapis.com/v1/uploads"
GPHOTOS_CREATE_URL = "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate"

NEEDS_MANUAL_DELETE_FILE = Path("manual_delete.txt")


def _upload_bytes(creds, path: Path) -> str:
    """Upload raw bytes and return an uploadToken."""
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/octet-stream",
        "X-Goog-Upload-Content-Type": mime,
        "X-Goog-Upload-Protocol": "raw",
    }
    resp = requests.post(
        GPHOTOS_UPLOAD_URL,
        headers=headers,
        data=path.read_bytes(),
    )
    resp.raise_for_status()
    return resp.text.strip()


def _create_media_item(creds, upload_token: str, filename: str) -> str:
    """Finalise upload and return the new mediaItem id.

    batchCreate returns 200 on full success or 207 MULTI_STATUS on partial
    success. We check the per-item status regardless of the HTTP status code.
    """
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    body = {
        "newMediaItems": [
            {
                "simpleMediaItem": {
                    "uploadToken": upload_token,
                    "fileName": filename,
                }
            }
        ]
    }
    resp = requests.post(GPHOTOS_CREATE_URL, headers=headers, json=body)

    # 200 = full success, 207 = partial success — both need per-item inspection
    if resp.status_code not in (200, 207):
        resp.raise_for_status()

    result = resp.json()["newMediaItemResults"][0]
    item_status = result.get("status", {})
    code = item_status.get("code", 0)
    # gRPC OK = 0, already exists = treated as success (Google deduplicates)
    if code not in (0, 6):
        raise RuntimeError(f"Upload failed ({item_status.get('message', 'unknown')})")

    return result["mediaItem"]["id"]


def run_swap(creds) -> None:
    """Upload all FIXED assets to Google Photos and report what needs manual cleanup."""
    state = State.load()
    to_upload = state.by_status(AssetStatus.FIXED)

    if not to_upload:
        print("No fixed assets ready for upload.")
        return

    print(f"Uploading {len(to_upload)} corrected files to Google Photos...")
    old_ids_to_delete = []

    for record in tqdm(to_upload):
        path = Path(record.local_path)
        try:
            token = _upload_bytes(creds, path)
            new_id = _create_media_item(creds, token, record.filename)
            record.new_google_id = new_id
            record.status = AssetStatus.UPLOADED
            old_ids_to_delete.append(record.google_id)
        except Exception as exc:
            record.status = AssetStatus.FAILED
            record.error = str(exc)

        state.upsert(record)
        state.save()

    if old_ids_to_delete:
        NEEDS_MANUAL_DELETE_FILE.write_text("\n".join(old_ids_to_delete) + "\n")
        print(
            f"\n{len(old_ids_to_delete)} old wrongly-dated items need manual deletion.\n"
            f"Their Google Photos IDs are saved to: {NEEDS_MANUAL_DELETE_FILE}\n"
            "In Google Photos, search by date for the migration date and delete the duplicates."
        )

    uploaded = len(state.by_status(AssetStatus.UPLOADED))
    failed = len(state.by_status(AssetStatus.FAILED))
    print(f"\nUpload complete: {uploaded} succeeded, {failed} failed.")
