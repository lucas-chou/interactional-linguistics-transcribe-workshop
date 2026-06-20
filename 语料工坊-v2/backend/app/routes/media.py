from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..db import connect
from ..storage import get_media, save_upload, utc_now


router = APIRouter()


@router.post("/api/media")
async def upload_media(file: UploadFile = File(...)) -> dict:
    return await save_upload(file)


@router.get("/api/media")
async def list_media() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                media.id,
                media.filename,
                media.stored_path,
                media.pinned_at,
                media.created_at,
                (
                    SELECT transcripts.id
                    FROM transcripts
                    WHERE transcripts.media_id = media.id
                    ORDER BY transcripts.created_at DESC
                    LIMIT 1
                ) AS latest_transcript_id,
                (
                    SELECT transcripts.corpus_saved_at
                    FROM transcripts
                    WHERE transcripts.media_id = media.id
                    ORDER BY transcripts.created_at DESC
                    LIMIT 1
                ) AS latest_corpus_saved_at
            FROM media
            ORDER BY media.pinned_at IS NULL, media.pinned_at DESC, media.created_at DESC
            LIMIT 100
            """
        ).fetchall()
        return [dict(row) for row in rows]


@router.get("/api/media/{media_id}/file")
async def get_media_file(media_id: str) -> FileResponse:
    media = get_media(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="媒体不存在")
    return FileResponse(media["stored_path"], filename=media["filename"])


@router.post("/api/media/{media_id}/pin")
async def pin_media(media_id: str) -> dict:
    with connect() as conn:
        media = conn.execute("SELECT id FROM media WHERE id = ?", (media_id,)).fetchone()
        if not media:
            raise HTTPException(status_code=404, detail="媒体不存在")
        conn.execute("UPDATE media SET pinned_at = ? WHERE id = ?", (utc_now(), media_id))
    return {"ok": True}


@router.post("/api/media/{media_id}/unpin")
async def unpin_media(media_id: str) -> dict:
    with connect() as conn:
        media = conn.execute("SELECT id FROM media WHERE id = ?", (media_id,)).fetchone()
        if not media:
            raise HTTPException(status_code=404, detail="媒体不存在")
        conn.execute("UPDATE media SET pinned_at = NULL WHERE id = ?", (media_id,))
    return {"ok": True}


@router.delete("/api/media/{media_id}")
async def delete_media(media_id: str) -> dict:
    media = get_media(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="媒体不存在")
    with connect() as conn:
        transcript_rows = conn.execute("SELECT id FROM transcripts WHERE media_id = ?", (media_id,)).fetchall()
        transcript_ids = [row["id"] for row in transcript_rows]
        for transcript_id in transcript_ids:
            segment_rows = conn.execute("SELECT id FROM segments WHERE transcript_id = ?", (transcript_id,)).fetchall()
            for segment in segment_rows:
                conn.execute("DELETE FROM words WHERE segment_id = ?", (segment["id"],))
            conn.execute("DELETE FROM segments WHERE transcript_id = ?", (transcript_id,))
            conn.execute("DELETE FROM transcript_tags WHERE transcript_id = ?", (transcript_id,))
            conn.execute("DELETE FROM corpus_fts WHERE transcript_id = ?", (transcript_id,))
        conn.execute("DELETE FROM transcripts WHERE media_id = ?", (media_id,))
        conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
    try:
        Path(media["stored_path"]).unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True}
