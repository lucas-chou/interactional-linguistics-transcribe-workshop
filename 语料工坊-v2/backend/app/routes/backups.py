import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import DATA_DIR, DB_PATH, MEDIA_DIR, WORK_DIR
from ..db import connect, init_db
from ..storage import utc_now


router = APIRouter()
BACKUP_DIR = DATA_DIR / "backups"


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


def ensure_child_path(base: Path, target: Path) -> Path:
    resolved_base = base.resolve()
    resolved_target = target.resolve()
    try:
        resolved_target.relative_to(resolved_base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="路径不安全") from exc
    return resolved_target


def backup_file_path(filename: str) -> Path:
    if Path(filename).name != filename or not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="备份文件名不合法")
    archive_path = ensure_child_path(BACKUP_DIR, BACKUP_DIR / filename)
    if not archive_path.exists() or not archive_path.is_file():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    return archive_path


@router.get("/api/backups")
async def list_backups() -> list[dict]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = []
    for path in sorted(BACKUP_DIR.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
        backups.append({"filename": path.name, "size": path.stat().st_size, "created_at": path.stat().st_mtime})
    return backups


@router.post("/api/backups")
async def create_backup() -> dict:
    archive_path = create_backup_archive()
    return {"ok": True, "filename": archive_path.name, "size": archive_path.stat().st_size}


@router.get("/api/backups/{filename}")
async def download_backup(filename: str) -> FileResponse:
    archive_path = backup_file_path(filename)
    return FileResponse(archive_path, filename=archive_path.name, media_type="application/zip")


@router.delete("/api/backups/{filename}")
async def delete_backup(filename: str) -> dict:
    archive_path = backup_file_path(filename)
    archive_path.unlink()
    return {"ok": True}


@router.post("/api/backups/restore")
async def restore_backup(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".zip"):
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
            extract_root = (restore_root / "extract").resolve()
            for member in archive.infolist():
                ensure_child_path(extract_root, extract_root / member.filename)
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
        orphan_tags = [
            row["transcript_id"]
            for row in conn.execute(
                """
                SELECT DISTINCT transcript_tags.transcript_id
                FROM transcript_tags
                LEFT JOIN transcripts ON transcripts.id = transcript_tags.transcript_id
                WHERE transcripts.id IS NULL
                """
            ).fetchall()
        ]
        orphan_fts = [
            row["transcript_id"]
            for row in conn.execute(
                """
                SELECT DISTINCT corpus_fts.transcript_id
                FROM corpus_fts
                LEFT JOIN transcripts ON transcripts.id = corpus_fts.transcript_id
                WHERE transcripts.id IS NULL
                """
            ).fetchall()
        ]
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
        "orphan_tags": orphan_tags,
        "orphan_fts": orphan_fts,
        "work_dirs": work_dirs,
    }


@router.get("/api/cleanup/preview")
async def cleanup_preview() -> dict:
    return inspect_cleanup()


@router.post("/api/cleanup")
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
        for transcript_id in summary["orphan_tags"]:
            conn.execute("DELETE FROM transcript_tags WHERE transcript_id = ?", (transcript_id,))
        for transcript_id in summary["orphan_fts"]:
            conn.execute("DELETE FROM corpus_fts WHERE transcript_id = ?", (transcript_id,))
    for path_text in summary["orphan_media_files"]:
        Path(path_text).unlink(missing_ok=True)
    for path_text in summary["work_dirs"]:
        shutil.rmtree(path_text, ignore_errors=True)
    return {"ok": True, "summary": summary}
