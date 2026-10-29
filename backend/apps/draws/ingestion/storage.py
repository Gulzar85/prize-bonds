"""Private storage for the raw files we download. Never publicly served; keys are content-addressed."""

import datetime

from django.core.files.base import ContentFile
from django.core.files.storage import Storage, storages

STORAGE_ALIAS = "draws_raw"


def raw_storage() -> Storage:
    return storages[STORAGE_ALIAS]


def raw_key(denomination_slug: str, draw_date: datetime.date, sha256: str, ext: str) -> str:
    return f"raw/{denomination_slug}/{draw_date.isoformat()}/{sha256}.{ext.lower().lstrip('.')}"


def store_raw(key: str, content: bytes) -> str:
    """Save the bytes under ``key`` (idempotent: the key contains the SHA-256 of the content)."""
    storage = raw_storage()
    if not storage.exists(key):
        saved = storage.save(key, ContentFile(content))
        assert saved == key, "storage renamed a content-addressed key"
    return key


def read_raw(key: str) -> bytes:
    with raw_storage().open(key, "rb") as handle:
        return bytes(handle.read())
