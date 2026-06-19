import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DEFAULT_HF_ENDPOINT, NLTK_DATA_DIR, WORK_DIR
from .db import connect
from .models import TranscribeRequest
from .storage import get_media
from .tasks import task_manager


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_transcription_task(task_id: str, request: TranscribeRequest) -> None:
    try:
        await task_manager.update(task_id, status="running", stage="preprocess", progress=0.05, message="准备音频")
        media = get_media(request.media_id)
        if not media:
            raise RuntimeError("媒体文件不存在")

        work_dir = WORK_DIR / task_id
        work_dir.mkdir(parents=True, exist_ok=True)
        wav_path = work_dir / "input.wav"
        result_path = work_dir / "result.json"

        await _convert_to_wav(Path(media["stored_path"]), wav_path)
        await task_manager.update(task_id, stage="transcribe", progress=0.2, message="本地模型转写中")

        raw_result = await _run_whisperx_script(task_id, wav_path, result_path, request)
        await task_manager.update(task_id, stage="persist", progress=0.9, message="写入语料库")

        transcript_id = _persist_result(request.media_id, request, raw_result)
        await task_manager.update(
            task_id,
            status="completed",
            stage="completed",
            progress=1,
            message="转写完成",
            transcript_id=transcript_id,
        )
    except Exception as error:
        await task_manager.update(
            task_id,
            status="failed",
            stage="failed",
            message="转写失败",
            error=f"{type(error).__name__}: {error}",
        )


async def _convert_to_wav(source: Path, target: Path) -> None:
    await asyncio.to_thread(_convert_to_wav_sync, source, target)


def _convert_to_wav_sync(source: Path, target: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr or process.stdout or "ffmpeg 转换失败")


async def _run_whisperx_script(task_id: str, wav_path: Path, result_path: Path, request: TranscribeRequest) -> dict[str, Any]:
    progress_path = result_path.with_suffix(".progress.json")
    script = f"""
import json
import os
import shutil
import traceback

os.environ.setdefault("HF_ENDPOINT", {DEFAULT_HF_ENDPOINT!r})
os.environ["PATH"] = r"C:\\ffmpeg\\bin" + os.pathsep + os.environ.get("PATH", "")
os.environ["NLTK_DATA"] = {str(NLTK_DATA_DIR)!r}

def ensure_nltk_data():
    import nltk

    nltk_data_dir = {str(NLTK_DATA_DIR)!r}
    os.makedirs(nltk_data_dir, exist_ok=True)
    if nltk_data_dir not in nltk.data.path:
        nltk.data.path.insert(0, nltk_data_dir)

    for package in ("punkt", "punkt_tab"):
        bad_zip = os.path.join(nltk_data_dir, "tokenizers", f"{{package}}.zip")
        if os.path.exists(bad_zip) and os.path.getsize(bad_zip) == 0:
            os.remove(bad_zip)

    for package in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{{package}}")
        except Exception:
            nltk.download(package, download_dir=nltk_data_dir, quiet=True)

    for package in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{{package}}")
        except Exception:
            shutil.rmtree(os.path.join(nltk_data_dir, "tokenizers", package), ignore_errors=True)
            zip_path = os.path.join(nltk_data_dir, "tokenizers", f"{{package}}.zip")
            if os.path.exists(zip_path):
                os.remove(zip_path)
            nltk.download(package, download_dir=nltk_data_dir, quiet=True, force=True)
            if os.path.exists(zip_path) and os.path.getsize(zip_path) == 0:
                os.remove(zip_path)

try:
    import torch
    from faster_whisper import WhisperModel

    audio_file = {str(wav_path)!r}
    result_file = {str(result_path)!r}
    progress_file = {str(progress_path)!r}
    requested_device = {request.device!r}
    device = "cuda" if requested_device == "auto" and torch.cuda.is_available() else ("cpu" if requested_device == "auto" else requested_device)
    requested_compute_type = {request.compute_type!r}
    compute_type = "float16" if requested_compute_type == "auto" and device == "cuda" else ("int8" if requested_compute_type == "auto" else requested_compute_type)
    language = None if {request.language!r} == "auto" else {request.language!r}

    def write_progress(progress, message, stage="transcribe"):
        with open(progress_file, "w", encoding="utf-8") as progress_output:
            json.dump({{"progress": progress, "message": message, "stage": stage}}, progress_output, ensure_ascii=False)

    write_progress(0.22, "正在加载本地模型")
    model = WhisperModel(
        {request.model!r},
        device=device,
        compute_type=compute_type,
        download_root=None,
        local_files_only=False,
    )
    write_progress(0.25, "模型加载完成，开始转写")
    segments_iter, info = model.transcribe(
        audio_file,
        language=language,
        task="transcribe",
        beam_size=5,
        word_timestamps=True,
        vad_filter=False,
    )
    segments = []
    duration = float(getattr(info, "duration", 0) or 0)
    for segment in segments_iter:
        words = []
        for word in segment.words or []:
            words.append({{
                "word": word.word,
                "start": word.start,
                "end": word.end,
                "score": word.probability,
            }})
        segments.append({{
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
            "words": words,
        }})
        if duration > 0:
            segment_progress = min(0.8, 0.25 + (float(segment.end or 0) / duration) * 0.55)
            write_progress(segment_progress, f"正在转写：{{float(segment.end or 0):.1f}} / {{duration:.1f}} 秒")
        else:
            write_progress(0.35, f"正在转写：已生成 {{len(segments)}} 个片段")
    result = {{"segments": segments, "language": info.language}}

    if {request.align!r}:
        write_progress(0.82, "正在进行 WhisperX 精细对齐", "align")
        import whisperx
        import whisperx.alignment as whisperx_alignment
        original_nltk_load = whisperx_alignment.nltk_load

        class FallbackSentenceSplitter:
            def span_tokenize(self, text):
                return [(0, len(text))] if text else []

        def safe_nltk_load(resource):
            try:
                return original_nltk_load(resource)
            except Exception:
                return FallbackSentenceSplitter()

        whisperx_alignment.nltk_load = safe_nltk_load

        audio = whisperx.load_audio(audio_file)
        align_model, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
        result = whisperx.align(result["segments"], align_model, metadata, audio, device, return_char_alignments=True)
        write_progress(0.88, "精细对齐完成", "align")

    result["language"] = result.get("language")
    result["engine"] = "whisperx" if {request.align!r} else "faster-whisper"
    result["model"] = {request.model!r}
    result["device"] = device
    result["compute_type"] = compute_type

    with open(result_file, "w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False)
    write_progress(0.9, "转写结果生成完成", "persist")
except Exception:
    traceback.print_exc()
    raise
"""
    script_path = result_path.with_suffix(".py")
    script_path.write_text(script, encoding="utf-8")
    return await _run_whisperx_script_process(task_id, script_path, result_path, progress_path)


async def _read_process_stream(stream: asyncio.StreamReader | None, lines: list[str]) -> None:
    if stream is None:
        return
    while True:
        line = await stream.readline()
        if not line:
            break
        lines.append(line.decode("utf-8", errors="replace"))


async def _run_whisperx_script_process(task_id: str, script_path: Path, result_path: Path, progress_path: Path) -> dict[str, Any]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "HF_ENDPOINT": DEFAULT_HF_ENDPOINT},
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    stdout_task = asyncio.create_task(_read_process_stream(process.stdout, stdout_lines))
    stderr_task = asyncio.create_task(_read_process_stream(process.stderr, stderr_lines))
    last_progress_payload = ""
    deadline = asyncio.get_running_loop().time() + 6 * 60 * 60

    while True:
        if progress_path.exists():
            progress_payload = progress_path.read_text(encoding="utf-8")
            if progress_payload and progress_payload != last_progress_payload:
                last_progress_payload = progress_payload
                try:
                    progress_data = json.loads(progress_payload)
                    await task_manager.update(
                        task_id,
                        stage=progress_data.get("stage", "transcribe"),
                        progress=float(progress_data.get("progress", 0.2)),
                        message=progress_data.get("message", "本地模型转写中"),
                    )
                except Exception:
                    pass

        if process.returncode is not None:
            break
        if asyncio.get_running_loop().time() > deadline:
            process.kill()
            await process.wait()
            raise RuntimeError("转写超时：任务运行超过 6 小时")
        try:
            await asyncio.wait_for(process.wait(), timeout=1)
        except asyncio.TimeoutError:
            continue

    await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
    if process.returncode != 0:
        stderr = "".join(stderr_lines).strip()
        stdout = "".join(stdout_lines).strip()
        raise RuntimeError(stderr or stdout or "WhisperX 子进程失败")
    return json.loads(result_path.read_text(encoding="utf-8"))


def _persist_result(media_id: str, request: TranscribeRequest, result: dict[str, Any]) -> str:
    transcript_id = str(uuid.uuid4())
    segments = result.get("segments") or []
    text = "\n".join((segment.get("text") or "").strip() for segment in segments).strip()

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO transcripts (id, media_id, engine, model, language, text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (transcript_id, media_id, "whisperx", request.model, result.get("language"), text, utc_now()),
        )

        for segment_index, segment in enumerate(segments):
            segment_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO segments (id, transcript_id, start_time, end_time, text, speaker, sort_index)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment_id,
                    transcript_id,
                    float(segment.get("start") or 0),
                    float(segment.get("end") or 0),
                    segment.get("text") or "",
                    segment.get("speaker"),
                    segment_index,
                ),
            )
            for word_index, word in enumerate(segment.get("words") or []):
                conn.execute(
                    """
                    INSERT INTO words (id, segment_id, start_time, end_time, text, confidence, sort_index)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        segment_id,
                        float(word.get("start") or 0),
                        float(word.get("end") or 0),
                        word.get("word") or word.get("text") or "",
                        word.get("score"),
                        word_index,
                    ),
                )

    return transcript_id
