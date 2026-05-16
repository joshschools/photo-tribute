"""Persistent per-asset progress tracking so runs are resumable."""

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

STATE_FILE = Path("state.json")


class AssetStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    FIXED = "fixed"       # exiftool pass complete
    UPLOADED = "uploaded"
    VERIFIED = "verified"
    DELETED_OLD = "deleted_old"
    FAILED = "failed"


@dataclass
class AssetRecord:
    icloud_id: str
    filename: str
    icloud_date: str          # ISO8601, from iCloud asset_date
    google_id: str            # Google Photos media item id
    google_date: str          # ISO8601, what Google currently shows
    status: AssetStatus = AssetStatus.PENDING
    local_path: Optional[str] = None
    new_google_id: Optional[str] = None  # set after re-upload
    error: Optional[str] = None


@dataclass
class State:
    assets: dict[str, AssetRecord] = field(default_factory=dict)  # keyed by icloud_id

    def save(self, path: Path = STATE_FILE) -> None:
        data = {k: asdict(v) for k, v in self.assets.items()}
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path = STATE_FILE) -> "State":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        assets = {k: AssetRecord(**v) for k, v in data.items()}
        return cls(assets=assets)

    def upsert(self, record: AssetRecord) -> None:
        self.assets[record.icloud_id] = record

    def by_status(self, status: AssetStatus) -> list[AssetRecord]:
        return [r for r in self.assets.values() if r.status == status]

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.assets.values():
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts
