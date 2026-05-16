"""Phase 3: Upload corrected files to Google Photos, then remove old items.

Google Photos API does not support updating creationTime on existing items,
so we must upload fresh copies and delete the originals.

Deletion note: the Library API only allows deleting items created by the
calling app. Items migrated from iCloud are user-owned and cannot be deleted
via API. Those are written to a report for manual cleanup in Google Photos.
"""

import mimetypes
from pathlib import Path

import requests
from tqdm import tqdm

from photo_tribute.state import State, AssetStatus

GPHOTOS_UPLOAD_URL = "https://photoslibrary.googleapis.com/v1/uploads"
GPHOTOS_CREATE_URL = "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate"
GPHOTOS_DELETE_URL = "https://photoslibrary.googleapis.com/v1/mediaItems:batchDelete"

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
    """Finalise upload and return the new mediaItem id."""
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
    resp.raise_for_status()
    result = resp.json()["newMediaItemResults"][0]
    status = result.get("status", {})
    if status.get("message", "").lower() not in ("success", "ok", ""):
        raise RuntimeError(f"Upload failed: {status}")
    return result["mediaItem"]["id"]


def _try_delete(creds, google_id: str) -> bool:
    """Attempt to delete a media item. Returns True on success."""
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        GPHOTOS_DELETE_URL,
        headers=headers,
        json={"mediaItemIds": [google_id]},
    )
    return resp.status_code == 200


def run_swap(creds) -> None:
    """Upload all FIXED assets and attempt to delete their old Google counterparts."""
    state = State.load()
    to_upload = state.by_status(AssetStatus.FIXED)

    if not to_upload:
        print("No fixed assets ready for upload.")
        return

    print(f"Uploading {len(to_upload)} corrected files to Google Photos...")
    manual_deletes = []

    for record in tqdm(to_upload):
        path = Path(record.local_path)
        try:
            token = _upload_bytes(creds, path)
            new_id = _create_media_item(creds, token, record.filename)
            record.new_google_id = new_id
            record.status = AssetStatus.UPLOADED
            state.upsert(record)
            state.save()
        except Exception as exc:
            record.status = AssetStatus.FAILED
            record.error = str(exc)
            state.upsert(record)
            state.save()
            continue

        # Attempt deletion of old item
        deleted = _try_delete(creds, record.google_id)
        if deleted:
            record.status = AssetStatus.DELETED_OLD
        else:
            # API cannot delete user-owned items — queue for manual cleanup
            manual_deletes.append(record.google_id)
            record.status = AssetStatus.VERIFIED  # upload succeeded; delete pending
        state.upsert(record)
        state.save()

    if manual_deletes:
        NEEDS_MANUAL_DELETE_FILE.write_text("\n".join(manual_deletes) + "\n")
        print(
            f"\n{len(manual_deletes)} old items could not be deleted via API "
            f"(Google restricts deleting user-owned items).\n"
            f"Their IDs are saved to {NEEDS_MANUAL_DELETE_FILE}.\n"
            "Open Google Photos, search for duplicates, and delete manually."
        )

    uploaded = len(state.by_status(AssetStatus.UPLOADED)) + len(state.by_status(AssetStatus.DELETED_OLD))
    print(f"\nSwap phase complete. {uploaded}/{len(to_upload)} files successfully re-uploaded.")
