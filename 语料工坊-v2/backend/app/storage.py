import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

from .config import MEDIA_DIR
from .db import connect


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def save_upload(file: UploadFile) -> dict:
    media_id = str(uuid.uuid4())
    suffix = Path(file.filename or "").suffix
    stored_path = MEDIA_DIR / f"{media_id}{suffix}"

    with stored_path.open("wb") as output:
      shutil.copyfileobj(file.file, output)

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO media (id, filename, original_path, stored_path, mime_type, duration, pinned_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (media_id, file.filename or stored_path.name, None, str(stored_path), file.content_type, None, None, utc_now()),
        )

    return {
        "id": media_id,
        "filename": file.filename or stored_path.name,
        "stored_path": str(stored_path),
        "created_at": utc_now(),
    }


def get_media(media_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        return dict(row) if row else None
