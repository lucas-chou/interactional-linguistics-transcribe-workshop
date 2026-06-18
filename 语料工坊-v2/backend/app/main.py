import asyncio
import csv
import io
import json
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .db import connect, init_db
from .models import SearchResult, TranscribeRequest, TranscriptTagsUpdate, TranscriptUpdate
from .storage import get_media, save_upload
from .storage import utc_now
from .tasks import task_manager
from .transcription import run_transcription_task


app = FastAPI(title="语料工坊 v2", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def attach_tags(conn, rows) -> list[dict]:
    items = [dict(row) for row in rows]
    if not items:
        return items
    transcript_ids = sorted({item["transcript_id"] for item in items})
    placeholders = ",".join("?" for _ in transcript_ids)
    tag_rows = conn.execute(
        f"""
        SELECT transcript_id, tag
        FROM transcript_tags
        WHERE transcript_id IN ({placeholders})
        ORDER BY tag
        """,
        transcript_ids,
    ).fetchall()
    tags_by_transcript = {transcript_id: [] for transcript_id in transcript_ids}
    for row in tag_rows:
        tags_by_transcript[row["transcript_id"]].append(row["tag"])
    for item in items:
        item["tags"] = tags_by_transcript.get(item["transcript_id"], [])
    return items


@app.on_event("startup")
async def startup() -> None:
    init_db()


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/api/media")
async def upload_media(file: UploadFile = File(...)) -> dict:
    return await save_upload(file)


@app.get("/api/media")
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


@app.get("/api/media/{media_id}/file")
async def get_media_file(media_id: str) -> FileResponse:
    media = get_media(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="媒体不存在")
    return FileResponse(media["stored_path"], filename=media["filename"])


@app.post("/api/media/{media_id}/pin")
async def pin_media(media_id: str) -> dict:
    with connect() as conn:
        media = conn.execute("SELECT id FROM media WHERE id = ?", (media_id,)).fetchone()
        if not media:
            raise HTTPException(status_code=404, detail="媒体不存在")
        conn.execute("UPDATE media SET pinned_at = ? WHERE id = ?", (utc_now(), media_id))
    return {"ok": True}


@app.post("/api/media/{media_id}/unpin")
async def unpin_media(media_id: str) -> dict:
    with connect() as conn:
        media = conn.execute("SELECT id FROM media WHERE id = ?", (media_id,)).fetchone()
        if not media:
            raise HTTPException(status_code=404, detail="媒体不存在")
        conn.execute("UPDATE media SET pinned_at = NULL WHERE id = ?", (media_id,))
    return {"ok": True}


@app.delete("/api/media/{media_id}")
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
            conn.execute("DELETE FROM corpus_fts WHERE transcript_id = ?", (transcript_id,))
        conn.execute("DELETE FROM transcripts WHERE media_id = ?", (media_id,))
        conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
    try:
        Path(media["stored_path"]).unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True}


@app.post("/api/transcriptions")
async def create_transcription(request: TranscribeRequest) -> dict:
    task = task_manager.create()
    asyncio.create_task(run_transcription_task(task.id, request))
    return task_manager.to_dict(task)


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task_manager.to_dict(task)


@app.get("/api/transcripts/{transcript_id}")
async def get_transcript(transcript_id: str) -> dict:
    with connect() as conn:
        transcript = conn.execute(
            "SELECT * FROM transcripts WHERE id = ?",
            (transcript_id,),
        ).fetchone()
        if not transcript:
            raise HTTPException(status_code=404, detail="转写结果不存在")
        segments = conn.execute(
            """
            SELECT id, start_time, end_time, text, speaker, sort_index
            FROM segments
            WHERE transcript_id = ?
            ORDER BY sort_index
            """,
            (transcript_id,),
        ).fetchall()
        segment_items = []
        for segment in segments:
            words = conn.execute(
                """
                SELECT id, start_time, end_time, text, confidence, sort_index
                FROM words
                WHERE segment_id = ?
                ORDER BY sort_index
                """,
                (segment["id"],),
            ).fetchall()
            segment_dict = dict(segment)
            segment_dict["words"] = [dict(word) for word in words]
            segment_items.append(segment_dict)
        tag_rows = conn.execute(
            "SELECT tag FROM transcript_tags WHERE transcript_id = ? ORDER BY tag",
            (transcript_id,),
        ).fetchall()
        return {**dict(transcript), "segments": segment_items, "tags": [row["tag"] for row in tag_rows]}


def get_export_data(conn, transcript_id: str) -> tuple[dict, list[dict], list[str]]:
    transcript = conn.execute(
        """
        SELECT transcripts.*, media.filename
        FROM transcripts
        JOIN media ON media.id = transcripts.media_id
        WHERE transcripts.id = ?
        """,
        (transcript_id,),
    ).fetchone()
    if not transcript:
        raise HTTPException(status_code=404, detail="转写结果不存在")
    segments = conn.execute(
        """
        SELECT start_time, end_time, text, speaker, sort_index
        FROM segments
        WHERE transcript_id = ?
        ORDER BY sort_index
        """,
        (transcript_id,),
    ).fetchall()
    tags = conn.execute(
        "SELECT tag FROM transcript_tags WHERE transcript_id = ? ORDER BY tag",
        (transcript_id,),
    ).fetchall()
    return dict(transcript), [dict(segment) for segment in segments], [row["tag"] for row in tags]


def export_filename(original_filename: str, suffix: str) -> str:
    safe_stem = Path(original_filename).stem.strip() or "transcript"
    return quote(f"{safe_stem}.{suffix}", safe="")


@app.get("/api/transcripts/{transcript_id}/export/txt")
async def export_transcript_txt(transcript_id: str) -> StreamingResponse:
    with connect() as conn:
        transcript, _segments, tags = get_export_data(conn, transcript_id)
    lines = [
        f"文件：{transcript['filename']}",
        f"模型：{transcript['model']}",
        f"语言：{transcript['language'] or ''}",
        f"标签：{', '.join(tags)}",
        "",
        transcript["text"],
    ]
    content = "\n".join(lines)
    filename = export_filename(transcript["filename"], "txt")
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8-sig")),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@app.get("/api/transcripts/{transcript_id}/export/csv")
async def export_transcript_csv(transcript_id: str) -> StreamingResponse:
    with connect() as conn:
        transcript, segments, tags = get_export_data(conn, transcript_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["filename", "transcript_id", "tags", "segment_index", "start_time", "end_time", "speaker", "text"])
    for segment in segments:
        writer.writerow(
            [
                transcript["filename"],
                transcript_id,
                ";".join(tags),
                segment["sort_index"],
                segment["start_time"],
                segment["end_time"],
                segment["speaker"] or "",
                segment["text"],
            ]
        )
    filename = export_filename(transcript["filename"], "csv")
    return StreamingResponse(
        io.BytesIO(buffer.getvalue().encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@app.put("/api/transcripts/{transcript_id}")
async def update_transcript(transcript_id: str, update: TranscriptUpdate) -> dict:
    with connect() as conn:
        exists = conn.execute("SELECT id, media_id FROM transcripts WHERE id = ?", (transcript_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="转写结果不存在")
        if update.full_text is not None:
            full_text = update.full_text
            segment_rows = conn.execute(
                "SELECT id FROM segments WHERE transcript_id = ? ORDER BY sort_index",
                (transcript_id,),
            ).fetchall()
            for index, row in enumerate(segment_rows):
                conn.execute(
                    "UPDATE segments SET text = ? WHERE id = ?",
                    (full_text if index == 0 else "", row["id"]),
                )
        else:
            segment_text_by_id = {segment.id: segment.text for segment in update.segments}
            for segment_id, text in segment_text_by_id.items():
                conn.execute(
                    "UPDATE segments SET text = ? WHERE id = ? AND transcript_id = ?",
                    (text, segment_id, transcript_id),
                )
            rows = conn.execute(
                "SELECT text FROM segments WHERE transcript_id = ? ORDER BY sort_index",
                (transcript_id,),
            ).fetchall()
            full_text = "\n".join(row["text"] for row in rows)
        conn.execute("UPDATE transcripts SET text = ? WHERE id = ?", (full_text, transcript_id))
    return {"ok": True}


@app.put("/api/transcripts/{transcript_id}/tags")
async def update_transcript_tags(transcript_id: str, update: TranscriptTagsUpdate) -> dict:
    cleaned_tags = []
    seen = set()
    for tag in update.tags:
        cleaned = tag.strip()
        if cleaned and cleaned not in seen:
            cleaned_tags.append(cleaned[:60])
            seen.add(cleaned)

    with connect() as conn:
        transcript = conn.execute("SELECT id FROM transcripts WHERE id = ?", (transcript_id,)).fetchone()
        if not transcript:
            raise HTTPException(status_code=404, detail="转写结果不存在")
        conn.execute("DELETE FROM transcript_tags WHERE transcript_id = ?", (transcript_id,))
        for tag in cleaned_tags:
            conn.execute(
                "INSERT INTO transcript_tags (transcript_id, tag, created_at) VALUES (?, ?, ?)",
                (transcript_id, tag, utc_now()),
            )
    return {"ok": True, "tags": cleaned_tags}


@app.post("/api/transcripts/{transcript_id}/corpus")
async def save_transcript_to_corpus(transcript_id: str) -> dict:
    with connect() as conn:
        transcript = conn.execute(
            "SELECT id, media_id, text FROM transcripts WHERE id = ?",
            (transcript_id,),
        ).fetchone()
        if not transcript:
            raise HTTPException(status_code=404, detail="转写结果不存在")
        conn.execute("DELETE FROM corpus_fts WHERE transcript_id = ?", (transcript_id,))
        conn.execute(
            "INSERT INTO corpus_fts (transcript_id, media_id, text) VALUES (?, ?, ?)",
            (transcript_id, transcript["media_id"], transcript["text"]),
        )
        conn.execute("UPDATE transcripts SET corpus_saved_at = ? WHERE id = ?", (utc_now(), transcript_id))
    return {"ok": True}


@app.websocket("/ws/tasks/{task_id}")
async def task_socket(websocket: WebSocket, task_id: str) -> None:
    task = task_manager.get(task_id)
    if not task:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = await task_manager.subscribe(task_id)
    try:
        while True:
            payload = await queue.get()
            await websocket.send_text(json.dumps(payload, ensure_ascii=False))
            if payload["status"] in {"completed", "failed"}:
                break
    except WebSocketDisconnect:
        pass
    finally:
        task_manager.unsubscribe(task_id, queue)


@app.get("/api/search", response_model=list[SearchResult])
async def search(q: str = "") -> list[dict]:
    with connect() as conn:
        if not q.strip():
            rows = conn.execute(
                """
                SELECT id AS transcript_id, media_id, substr(text, 1, 220) AS snippet
                FROM transcripts
                WHERE corpus_saved_at IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 50
                """
            ).fetchall()
            return attach_tags(conn, rows)
        try:
            rows = conn.execute(
                """
                SELECT transcript_id, media_id, snippet(corpus_fts, 2, '[', ']', '...', 12) AS snippet
                FROM corpus_fts
                WHERE corpus_fts MATCH ?
                LIMIT 50
                """,
                (q,),
            ).fetchall()
        except Exception:
            rows = []
        if not rows:
            rows = conn.execute(
                """
                SELECT id AS transcript_id, media_id, substr(text, 1, 160) AS snippet
                FROM transcripts
                WHERE corpus_saved_at IS NOT NULL AND text LIKE ?
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (f"%{q}%",),
            ).fetchall()
        return attach_tags(conn, rows)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8765, reload=False)
