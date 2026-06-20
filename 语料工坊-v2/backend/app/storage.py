import hashlib
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import MEDIA_DIR
from .db import connect


ALLOWED_MEDIA_SUFFIXES = {
    ".aac",
    ".avi",
    ".flac",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
    ".wmv",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024 * 1024


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


def validate_media_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_MEDIA_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_MEDIA_SUFFIXES))
        raise HTTPException(status_code=400, detail=f"不支持的文件格式。请导入音视频文件：{allowed}")
    return suffix


def validate_media_file(path: Path) -> None:
    try:
        process = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="未找到 ffprobe，请确认 FFmpeg 已正确安装并加入 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=400, detail="文件检测超时，请确认文件是否损坏") from exc
    if process.returncode != 0:
        raise HTTPException(status_code=400, detail="文件无法被 FFmpeg 识别，请确认它是有效的音频或视频文件")


async def save_upload(file: UploadFile) -> dict:
    media_id = str(uuid.uuid4())
    suffix = validate_media_suffix(file.filename)
    temp_path = MEDIA_DIR / f".upload-{media_id}{suffix or '.tmp'}"
    stored_path = MEDIA_DIR / f"{media_id}{suffix}"

    hasher = hashlib.sha256()
    total_bytes = 0
    with temp_path.open("wb") as output:
        for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                temp_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="文件过大，当前最多支持 10GB")
            hasher.update(chunk)
            output.write(chunk)
    if total_bytes == 0:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="文件为空")
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

        try:
            validate_media_file(temp_path)
        except HTTPException:
            temp_path.unlink(missing_ok=True)
            raise
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
