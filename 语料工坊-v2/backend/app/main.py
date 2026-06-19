import asyncio
import csv
import io
import json
import shutil
import socket
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .acoustic import analyze_acoustic_candidates, ensure_wav
from .config import DATA_DIR, DB_PATH, MEDIA_DIR, WORK_DIR
from .db import connect, init_db
from .models import BatchCorpusDeleteRequest, BatchExportRequest, SearchResult, TextImportRequest, TranscribeRequest, TranscriptTagsUpdate, TranscriptUpdate
from .storage import get_media, save_upload
from .storage import utc_now
from .tasks import task_manager
from .text_normalize import to_simplified_chinese
from .transcription import run_transcription_task


app = FastAPI(title="语料工坊 v2", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKUP_DIR = DATA_DIR / "backups"


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


def create_backup_archive() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = BACKUP_DIR / f"corpus-backup-{utc_now().replace(':', '-').replace(' ', '_')}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
      for path in [DB_PATH, MEDIA_DIR, WORK_DIR]:
        if path.is_file():
          archive.write(path, arcname=path.relative_to(DATA_DIR))
        elif path.is_dir():
          for item in path.rglob("*"):
            if item.is_file():
              archive.write(item, arcname=item.relative_to(DATA_DIR))
    return archive_path


@app.on_event("startup")
async def startup() -> None:
    init_db()


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/api/system/status")
async def system_status() -> dict:
    def command_ok(command: list[str]) -> tuple[bool, str]:
        try:
            process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
            output = (process.stdout or process.stderr or "").strip().splitlines()
            return process.returncode == 0, output[0] if output else ""
        except Exception as exc:
            return False, str(exc)

    def port_open(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    ffmpeg_ok, ffmpeg_message = command_ok(["ffmpeg", "-version"])
    whisperx_ok = False
    whisperx_message = ""
    try:
        import whisperx  # type: ignore

        whisperx_ok = True
        whisperx_message = getattr(whisperx, "__version__", "installed")
    except Exception as exc:
        whisperx_message = str(exc)
    parselmouth_ok = False
    parselmouth_message = ""
    try:
        import parselmouth  # type: ignore

        parselmouth_ok = True
        parselmouth_message = getattr(parselmouth, "__version__", "installed")
    except Exception as exc:
        parselmouth_message = str(exc)

    with connect() as conn:
        media_count = conn.execute("SELECT COUNT(*) AS count FROM media").fetchone()["count"]
        transcript_count = conn.execute("SELECT COUNT(*) AS count FROM transcripts").fetchone()["count"]
        corpus_count = conn.execute("SELECT COUNT(*) AS count FROM transcripts WHERE corpus_saved_at IS NOT NULL").fetchone()["count"]

    return {
        "python": {"ok": True, "message": sys.version.split()[0]},
        "ffmpeg": {"ok": ffmpeg_ok, "message": ffmpeg_message},
        "whisperx": {"ok": whisperx_ok, "message": whisperx_message},
        "parselmouth": {"ok": parselmouth_ok, "message": parselmouth_message},
        "database": {"ok": DB_PATH.exists(), "message": str(DB_PATH)},
        "media_dir": {"ok": MEDIA_DIR.exists(), "message": str(MEDIA_DIR)},
        "backend_port": {"ok": port_open(8765), "message": "127.0.0.1:8765"},
        "frontend_port": {"ok": port_open(5173), "message": "127.0.0.1:5173"},
        "counts": {"media": media_count, "transcripts": transcript_count, "corpus": corpus_count},
    }


@app.get("/api/backups")
async def list_backups() -> list[dict]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = []
    for path in sorted(BACKUP_DIR.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
        backups.append({"filename": path.name, "size": path.stat().st_size, "created_at": path.stat().st_mtime})
    return backups


@app.post("/api/backups")
async def create_backup() -> dict:
    archive_path = create_backup_archive()
    return {"ok": True, "filename": archive_path.name, "size": archive_path.stat().st_size}


@app.get("/api/backups/{filename}")
async def download_backup(filename: str) -> FileResponse:
    archive_path = (BACKUP_DIR / filename).resolve()
    if not str(archive_path).startswith(str(BACKUP_DIR.resolve())) or not archive_path.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    return FileResponse(archive_path, filename=archive_path.name, media_type="application/zip")


@app.delete("/api/backups/{filename}")
async def delete_backup(filename: str) -> dict:
    archive_path = (BACKUP_DIR / filename).resolve()
    if not str(archive_path).startswith(str(BACKUP_DIR.resolve())) or archive_path.suffix.lower() != ".zip" or not archive_path.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    archive_path.unlink()
    return {"ok": True}


@app.post("/api/backups/restore")
async def restore_backup(file: UploadFile = File(...)) -> dict:
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="只支持 zip 备份文件")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    restore_root = DATA_DIR / "restore_tmp"
    if restore_root.exists():
        shutil.rmtree(restore_root)
    restore_root.mkdir(parents=True, exist_ok=True)

    upload_path = restore_root / "backup.zip"
    with upload_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    try:
        with zipfile.ZipFile(upload_path) as archive:
            for member in archive.infolist():
                target = (restore_root / "extract" / member.filename).resolve()
                if not str(target).startswith(str((restore_root / "extract").resolve())):
                    raise HTTPException(status_code=400, detail="备份文件路径不安全")
            archive.extractall(restore_root / "extract")
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="备份文件损坏") from exc

    extracted = restore_root / "extract"
    if not (extracted / "corpus.db").exists():
        raise HTTPException(status_code=400, detail="备份文件缺少 corpus.db")

    safety_backup = create_backup_archive()
    for target in [DB_PATH, MEDIA_DIR, WORK_DIR]:
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()

    shutil.copy2(extracted / "corpus.db", DB_PATH)
    if (extracted / "media").exists():
        shutil.copytree(extracted / "media", MEDIA_DIR, dirs_exist_ok=True)
    if (extracted / "work").exists():
        shutil.copytree(extracted / "work", WORK_DIR, dirs_exist_ok=True)

    shutil.rmtree(restore_root, ignore_errors=True)
    init_db()
    return {"ok": True, "safety_backup": safety_backup.name}


def inspect_cleanup() -> dict:
    with connect() as conn:
        media_rows = conn.execute("SELECT id, stored_path FROM media").fetchall()
    missing_media = [row["id"] for row in media_rows if not Path(row["stored_path"]).exists()]
    referenced_files = {Path(row["stored_path"]).resolve() for row in media_rows}
    orphan_media_files = []
    if MEDIA_DIR.exists():
        for path in MEDIA_DIR.iterdir():
            if path.is_file() and path.resolve() not in referenced_files:
                orphan_media_files.append(str(path))
    work_dirs = [str(path) for path in WORK_DIR.iterdir() if path.is_dir()] if WORK_DIR.exists() else []
    return {
        "missing_media_records": missing_media,
        "orphan_media_files": orphan_media_files,
        "work_dirs": work_dirs,
    }


@app.get("/api/cleanup/preview")
async def cleanup_preview() -> dict:
    return inspect_cleanup()


@app.post("/api/cleanup")
async def cleanup_data() -> dict:
    summary = inspect_cleanup()
    with connect() as conn:
        for media_id in summary["missing_media_records"]:
            transcript_rows = conn.execute("SELECT id FROM transcripts WHERE media_id = ?", (media_id,)).fetchall()
            for transcript in transcript_rows:
                segment_rows = conn.execute("SELECT id FROM segments WHERE transcript_id = ?", (transcript["id"],)).fetchall()
                for segment in segment_rows:
                    conn.execute("DELETE FROM words WHERE segment_id = ?", (segment["id"],))
                conn.execute("DELETE FROM segments WHERE transcript_id = ?", (transcript["id"],))
                conn.execute("DELETE FROM transcript_tags WHERE transcript_id = ?", (transcript["id"],))
                conn.execute("DELETE FROM corpus_fts WHERE transcript_id = ?", (transcript["id"],))
            conn.execute("DELETE FROM transcripts WHERE media_id = ?", (media_id,))
            conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
    for path_text in summary["orphan_media_files"]:
        Path(path_text).unlink(missing_ok=True)
    for path_text in summary["work_dirs"]:
        shutil.rmtree(path_text, ignore_errors=True)
    return {"ok": True, "summary": summary}


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


@app.post("/api/transcripts/import-text")
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


@app.get("/api/transcripts/{transcript_id}/acoustic-candidates")
async def get_acoustic_candidates(transcript_id: str) -> dict:
    with connect() as conn:
        transcript = conn.execute(
            """
            SELECT transcripts.id, media.stored_path
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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
    tags = conn.execute(
        "SELECT tag FROM transcript_tags WHERE transcript_id = ? ORDER BY tag",
        (transcript_id,),
    ).fetchall()
    return dict(transcript), [dict(segment) for segment in segments], [row["tag"] for row in tags]


def export_filename(original_filename: str, suffix: str) -> str:
    safe_stem = Path(original_filename).stem.strip() or "transcript"
    return quote(f"{safe_stem}.{suffix}", safe="")


def build_txt_export(transcript: dict, tags: list[str]) -> str:
    lines = [
        f"???{transcript['filename']}",
        f"???{transcript['model']}",
        f"???{transcript['language'] or ''}",
        f"???{', '.join(tags)}",
        "",
        transcript["text"],
    ]
    return "\n".join(lines)


def build_csv_export(transcript_id: str, transcript: dict, segments: list[dict], tags: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["filename", "transcript_id", "tags", "segment_index", "start_time", "end_time", "speaker", "text"])
    for segment in segments:
        writer.writerow([
            transcript["filename"],
            transcript_id,
            ";".join(tags),
            segment["sort_index"],
            segment["start_time"],
            segment["end_time"],
            segment["speaker"] or "",
            segment["text"],
        ])
    return buffer.getvalue()


@app.get("/api/transcripts/{transcript_id}/export/txt")
async def export_transcript_txt(transcript_id: str) -> StreamingResponse:
    with connect() as conn:
        transcript, _segments, tags = get_export_data(conn, transcript_id)
    content = build_txt_export(transcript, tags)
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
    content = build_csv_export(transcript_id, transcript, segments, tags)
    filename = export_filename(transcript["filename"], "csv")
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@app.post("/api/exports/batch")
async def export_transcripts_batch(request: BatchExportRequest) -> StreamingResponse:
    export_format = request.format.lower().strip()
    if export_format not in {"txt", "csv"}:
        raise HTTPException(status_code=400, detail="??? txt ? csv")
    transcript_ids = []
    seen = set()
    for transcript_id in request.transcript_ids:
        if transcript_id not in seen:
            transcript_ids.append(transcript_id)
            seen.add(transcript_id)
    if not transcript_ids:
        raise HTTPException(status_code=400, detail="?????????")

    zip_buffer = io.BytesIO()
    with connect() as conn, zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, transcript_id in enumerate(transcript_ids, start=1):
            transcript, segments, tags = get_export_data(conn, transcript_id)
            stem = Path(transcript["filename"]).stem.strip() or f"transcript-{index}"
            if export_format == "txt":
                content = build_txt_export(transcript, tags)
            else:
                content = build_csv_export(transcript_id, transcript, segments, tags)
            archive.writestr(f"{index:03d}-{stem}.{export_format}", content.encode("utf-8-sig"))

    zip_buffer.seek(0)
    filename = quote(f"corpus-batch-export.{export_format}.zip", safe="")
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
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


@app.post("/api/corpus/delete")
async def delete_corpus_entries(request: BatchCorpusDeleteRequest) -> dict:
    transcript_ids = []
    seen = set()
    for transcript_id in request.transcript_ids:
        if transcript_id not in seen:
            transcript_ids.append(transcript_id)
            seen.add(transcript_id)
    if not transcript_ids:
        raise HTTPException(status_code=400, detail="请先选择要删除的语料")

    placeholders = ",".join("?" for _ in transcript_ids)
    with connect() as conn:
        deleted = conn.execute(
            f"SELECT COUNT(*) AS count FROM transcripts WHERE id IN ({placeholders}) AND corpus_saved_at IS NOT NULL",
            transcript_ids,
        ).fetchone()["count"]
        for transcript_id in transcript_ids:
            conn.execute("DELETE FROM corpus_fts WHERE transcript_id = ?", (transcript_id,))
        conn.execute(
            f"UPDATE transcripts SET corpus_saved_at = NULL WHERE id IN ({placeholders})",
            transcript_ids,
        )
    return {"ok": True, "deleted": deleted}


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
async def search(q: str = "", tag: str = "") -> list[dict]:
    with connect() as conn:
        tag = tag.strip()
        if not q.strip():
            if tag:
                rows = conn.execute(
                    """
                    SELECT transcripts.id AS transcript_id, transcripts.media_id, substr(transcripts.text, 1, 220) AS snippet
                    FROM transcripts
                    JOIN transcript_tags ON transcript_tags.transcript_id = transcripts.id
                    WHERE transcripts.corpus_saved_at IS NOT NULL AND transcript_tags.tag = ?
                    ORDER BY transcripts.created_at DESC
                    LIMIT 50
                    """,
                    (tag,),
                ).fetchall()
                return attach_tags(conn, rows)
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
            if tag:
                rows = conn.execute(
                    """
                    SELECT corpus_fts.transcript_id, corpus_fts.media_id, snippet(corpus_fts, 2, '[', ']', '...', 12) AS snippet
                    FROM corpus_fts
                    JOIN transcript_tags ON transcript_tags.transcript_id = corpus_fts.transcript_id
                    WHERE corpus_fts MATCH ? AND transcript_tags.tag = ?
                    LIMIT 50
                    """,
                    (q, tag),
                ).fetchall()
            else:
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
            if tag:
                rows = conn.execute(
                    """
                    SELECT transcripts.id AS transcript_id, transcripts.media_id, substr(transcripts.text, 1, 160) AS snippet
                    FROM transcripts
                    JOIN transcript_tags ON transcript_tags.transcript_id = transcripts.id
                    WHERE transcripts.corpus_saved_at IS NOT NULL AND transcripts.text LIKE ? AND transcript_tags.tag = ?
                    ORDER BY transcripts.created_at DESC
                    LIMIT 50
                    """,
                    (f"%{q}%", tag),
                ).fetchall()
            else:
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


@app.get("/api/tags")
async def list_tags() -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT DISTINCT tag FROM transcript_tags ORDER BY tag").fetchall()
        return [row["tag"] for row in rows]


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8765, reload=False)
