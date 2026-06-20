import asyncio
import csv
import io
import json
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from ..acoustic import analyze_acoustic_candidates, ensure_wav
from ..config import MEDIA_DIR, WORK_DIR
from ..db import connect
from ..models import BatchExportRequest, TextImportRequest, TranscribeRequest, TranscriptTagsUpdate, TranscriptUpdate
from ..storage import get_media, utc_now
from ..tasks import task_manager
from ..text_normalize import to_simplified_chinese
from ..transcription import run_transcription_task


router = APIRouter()


@router.post("/api/transcriptions")
async def create_transcription(request: TranscribeRequest) -> dict:
    task = task_manager.create()
    asyncio.create_task(run_transcription_task(task.id, request))
    return task_manager.to_dict(task)


@router.post("/api/transcripts/import-text")
async def import_text_transcript(request: TextImportRequest) -> dict:
    media = get_media(request.media_id)
    if not media:
        raise HTTPException(status_code=404, detail="媒体不存在")
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="文本不能为空")
    if request.language is None or request.language.startswith("zh"):
        text = to_simplified_chinese(text)

    transcript_id = str(uuid.uuid4())
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        lines = [text]
    step = 1.0
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO transcripts (id, media_id, engine, model, language, text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (transcript_id, request.media_id, "manual", request.model, request.language, text, utc_now()),
        )
        for index, line in enumerate(lines):
            conn.execute(
                """
                INSERT INTO segments (id, transcript_id, start_time, end_time, text, speaker, sort_index)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), transcript_id, index * step, (index + 1) * step, line, None, index),
            )
    return {"ok": True, "transcript_id": transcript_id}


@router.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task_manager.to_dict(task)


@router.get("/api/transcripts/{transcript_id}")
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
        tags = [row["tag"] for row in conn.execute("SELECT tag FROM transcript_tags WHERE transcript_id = ? ORDER BY tag", (transcript_id,)).fetchall()]
        result = dict(transcript)
        result["segments"] = segment_items
        result["tags"] = tags
        return result


@router.get("/api/transcripts/{transcript_id}/acoustic-candidates")
async def get_acoustic_candidates(transcript_id: str) -> dict:
    with connect() as conn:
        transcript = conn.execute(
            """
            SELECT transcripts.id, transcripts.media_id, media.stored_path
            FROM transcripts
            JOIN media ON media.id = transcripts.media_id
            WHERE transcripts.id = ?
            """,
            (transcript_id,),
        ).fetchone()
        if not transcript:
            raise HTTPException(status_code=404, detail="转写结果不存在")
        segment_rows = conn.execute(
            """
            SELECT id, start_time, end_time, text, sort_index
            FROM segments
            WHERE transcript_id = ?
            ORDER BY sort_index
            """,
            (transcript_id,),
        ).fetchall()
        segment_items = []
        for segment in segment_rows:
            word_rows = conn.execute(
                """
                SELECT id, start_time, end_time, text, confidence, sort_index
                FROM words
                WHERE segment_id = ?
                ORDER BY sort_index
                """,
                (segment["id"],),
            ).fetchall()
            item = dict(segment)
            item["words"] = [dict(word) for word in word_rows]
            segment_items.append(item)
    if not segment_items:
        return {"candidates": []}

    source_path = Path(transcript["stored_path"])
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="媒体文件不存在")
    wav_path = WORK_DIR / "acoustic" / f"{transcript_id}.wav"
    try:
        ensure_wav(source_path, wav_path)
        candidates = analyze_acoustic_candidates(wav_path, segment_items)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"candidates": candidates}


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
    tags = [row["tag"] for row in conn.execute("SELECT tag FROM transcript_tags WHERE transcript_id = ? ORDER BY tag", (transcript_id,)).fetchall()]
    return dict(transcript), [dict(row) for row in segments], tags


def export_filename(original_filename: str, suffix: str) -> str:
    stem = Path(original_filename).stem or "transcript"
    safe_stem = "".join(char if char not in '\\/:*?"<>|' else "_" for char in stem)
    return quote(f"{safe_stem}.{suffix}", safe="")


def build_txt_export(transcript: dict, tags: list[str]) -> str:
    parts = [
        f"媒体文件：{transcript.get('filename', '')}",
        f"转写模型：{transcript.get('model', '')}",
        f"语言：{transcript.get('language') or ''}",
        f"标签：{', '.join(tags)}" if tags else "标签：",
        "",
        transcript.get("text", ""),
    ]
    return "\n".join(parts)


def build_csv_export(transcript_id: str, transcript: dict, segments: list[dict], tags: list[str]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["transcript_id", "media_filename", "start_time", "end_time", "speaker", "text", "tags"])
    for segment in segments:
        writer.writerow([
            transcript_id,
            transcript.get("filename", ""),
            segment.get("start_time", ""),
            segment.get("end_time", ""),
            segment.get("speaker") or "",
            segment.get("text", ""),
            ";".join(tags),
        ])
    return output.getvalue()


@router.get("/api/transcripts/{transcript_id}/export/txt")
async def export_transcript_txt(transcript_id: str) -> StreamingResponse:
    with connect() as conn:
        transcript, _segments, tags = get_export_data(conn, transcript_id)
    content = build_txt_export(transcript, tags)
    filename = export_filename(transcript["filename"], "txt")
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/api/transcripts/{transcript_id}/export/csv")
async def export_transcript_csv(transcript_id: str) -> StreamingResponse:
    with connect() as conn:
        transcript, segments, tags = get_export_data(conn, transcript_id)
    content = build_csv_export(transcript_id, transcript, segments, tags)
    filename = export_filename(transcript["filename"], "csv")
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/api/exports/batch")
async def export_transcripts_batch(request: BatchExportRequest) -> StreamingResponse:
    export_format = request.format.lower()
    if export_format not in {"txt", "csv"}:
        raise HTTPException(status_code=400, detail="只支持 txt 或 csv")
    transcript_ids = []
    seen = set()
    for transcript_id in request.transcript_ids:
        if transcript_id not in seen:
            transcript_ids.append(transcript_id)
            seen.add(transcript_id)
    if not transcript_ids:
        raise HTTPException(status_code=400, detail="请先选择要导出的语料")

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        with connect() as conn:
            for index, transcript_id in enumerate(transcript_ids, start=1):
                transcript, segments, tags = get_export_data(conn, transcript_id)
                stem = Path(transcript["filename"]).stem or transcript_id
                stem = "".join(char if char not in '\\/:*?"<>|' else "_" for char in stem)
                if export_format == "txt":
                    content = build_txt_export(transcript, tags)
                else:
                    content = build_csv_export(transcript_id, transcript, segments, tags)
                archive.writestr(f"{index:03d}-{stem}.{export_format}", content.encode("utf-8-sig"))

    archive_buffer.seek(0)
    filename = quote(f"corpus-batch-export.{export_format}.zip", safe="")
    return StreamingResponse(
        archive_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.put("/api/transcripts/{transcript_id}")
async def update_transcript(transcript_id: str, update: TranscriptUpdate) -> dict:
    with connect() as conn:
        exists = conn.execute("SELECT id, media_id, text FROM transcripts WHERE id = ?", (transcript_id,)).fetchone()
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
        if full_text != exists["text"]:
            conn.execute("DELETE FROM corpus_fts WHERE transcript_id = ?", (transcript_id,))
            conn.execute("UPDATE transcripts SET corpus_saved_at = NULL WHERE id = ?", (transcript_id,))
    return {"ok": True}


@router.put("/api/transcripts/{transcript_id}/tags")
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


@router.websocket("/ws/tasks/{task_id}")
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
