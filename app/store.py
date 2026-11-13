"""Visit records, encrypted at rest (Fernet / AES). Transcripts and audio are never stored.

Delete everything after judging:  python -m app.store purge
"""
import json
import logging
import sys
from datetime import date
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from . import config

log = logging.getLogger("store")


class Store:
    def __init__(self, path: Path | None = None, key: str | None = None):
        self.path = path or (config.DATA_DIR / "records.enc")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        key = key or config.DATA_ENCRYPTION_KEY
        if not key:
            key = Fernet.generate_key().decode()
            log.warning("DATA_ENCRYPTION_KEY not set: using a temporary key; records are unreadable after restart.")
        self.fernet = Fernet(key.encode())

    def save(self, record: dict) -> None:
        token = self.fernet.encrypt(json.dumps(record, ensure_ascii=False, default=str).encode())
        with self.path.open("ab") as f:
            f.write(token + b"\n")

    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_bytes().splitlines():
            try:
                out.append(json.loads(self.fernet.decrypt(line)))
            except (InvalidToken, ValueError):
                continue
        return out

    def followups(self) -> list[dict]:
        """Danger-flagged cases first, then by next visit date."""
        latest = {}
        for r in self.all():
            latest[r["beneficiary_id"]] = r
        items = list(latest.values())
        items.sort(key=lambda r: (not r["danger_signs"], r.get("next_visit_date") or date.max.isoformat()))
        return items

    def purge(self) -> None:
        if self.path.exists():
            self.path.unlink()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "purge":
        Store().purge()
        for f in (config.CACHE_DIR / "tts").glob("*.wav"):
            f.unlink()
        print("Deleted all visit records and cached audio.")
    else:
        print("usage: python -m app.store purge")
