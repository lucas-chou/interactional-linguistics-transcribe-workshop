import socket
import subprocess
import sys

from fastapi import APIRouter

from ..config import DB_PATH, MEDIA_DIR
from ..db import connect


router = APIRouter()


@router.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@router.get("/api/system/status")
async def system_status() -> dict:
    def command_ok(command: list[str]) -> tuple[bool, str]:
        try:
            process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
            output = (process.stdout or process.stderr or "").strip().splitlines()
            return process.returncode == 0, output[0] if output else ""
        except Exception as exc:
            return False, str(exc)

    def port_open(port: int, host: str = "127.0.0.1") -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((host, port)) == 0

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
