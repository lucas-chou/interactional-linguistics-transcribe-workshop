import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

from .config import MEDIA_DIR
from .db import connect


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def media_response(row: dict, duplicate: bool = False) -> dict:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "stored_path": row["stored_path"],
        "pinned_at": row.get("pinned_at"),
        "created_at": row["created_at"],
        "duplicate": duplicate,
    }


async def save_upload(file: UploadFile) -> dict:
    media_id = str(uuid.uuid4())
    suffix = Path(file.filename or "").suffix
    temp_path = MEDIA_DIR / f".upload-{media_id}{suffix or '.tmp'}"
    stored_path = MEDIA_DIR / f"{media_id}{suffix}"

    hasher = hashlib.sha256()
    with temp_path.open("wb") as output:
        for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
            hasher.update(chunk)
            output.write(chunk)
    content_hash = hasher.hexdigest()

    with connect() as conn:
        existing = conn.execute(
            """
            SELECT id, filename, stored_path, pinned_at, created_at
            FROM media
            WHERE content_hash = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (content_hash,),
        ).fetchone()
        if existing and Path(existing["stored_path"]).exists():
            temp_path.unlink(missing_ok=True)
            return media_response(dict(existing), duplicate=True)

        legacy_rows = conn.execute(
            """
            SELECT id, filename, stored_path, pinned_at, created_at
            FROM media
            WHERE content_hash IS NULL
            ORDER BY created_at ASC
            """
        ).fetchall()
        for legacy_row in legacy_rows:
            legacy_path = Path(legacy_row["stored_path"])
            if not legacy_path.exists():
                continue
            if file_sha256(legacy_path) == content_hash:
                conn.execute("UPDATE media SET content_hash = ? WHERE id = ?", (content_hash, legacy_row["id"]))
                temp_path.unlink(missing_ok=True)
                return media_response(dict(legacy_row), duplicate=True)

        temp_path.replace(stored_path)
        created_at = utc_now()
        conn.execute(
            """
            INSERT INTO media (id, filename, original_path, stored_path, content_hash, mime_type, duration, pinned_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (media_id, file.filename or stored_path.name, None, str(stored_path), content_hash, file.content_type, None, None, created_at),
        )

    return {
        "id": media_id,
        "filename": file.filename or stored_path.name,
        "stored_path": str(stored_path),
        "created_at": created_at,
        "duplicate": False,
    }


def get_media(media_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        return dict(row) if row else None
