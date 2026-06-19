import math
import statistics
import subprocess
from pathlib import Path


def ensure_wav(source_path: Path, wav_path: Path) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    if wav_path.exists() and wav_path.stat().st_mtime >= source_path.stat().st_mtime:
        return
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(wav_path),
    ]
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if process.returncode != 0:
        raise RuntimeError(process.stderr or process.stdout or "ffmpeg 音频转换失败")


def _valid_pitch(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def _pitch_at(pitch, time: float) -> float | None:
    try:
        value = pitch.get_value_at_time(time)
    except Exception:
        return None
    return value if _valid_pitch(value) else None


def _intensity_at(intensity, time: float) -> float | None:
    try:
        value = intensity.get_value(time)
    except Exception:
        return None
    return value if value is not None and math.isfinite(value) else None


def _pitch_contour_mark(start_pitch: float, end_pitch: float) -> tuple[str, str, float] | None:
    delta = end_pitch - start_pitch
    relative = abs(delta) / max(start_pitch, 1)
    if abs(delta) < 25 and relative < 0.15:
        return None
    confidence = min(0.95, max(0.35, abs(delta) / 90))
    if delta > 0:
        return "/", f"音高上升 {delta:.1f}Hz", confidence
    return "\\", f"音高下降 {abs(delta):.1f}Hz", confidence


def analyze_acoustic_candidates(wav_path: Path, segments: list[dict]) -> list[dict]:
    try:
        import parselmouth
    except Exception as exc:
        raise RuntimeError(f"Parselmouth 未安装或不可用：{exc}") from exc

    sound = parselmouth.Sound(str(wav_path))
    pitch = sound.to_pitch(time_step=0.01, pitch_floor=75, pitch_ceiling=500)
    intensity = sound.to_intensity(time_step=0.01)
    words = [word for segment in segments for word in segment["words"] if word.get("text", "").strip()]
    durations = [word["end_time"] - word["start_time"] for word in words if word["end_time"] > word["start_time"]]
    duration_median = statistics.median(durations) if durations else 0
    long_duration_threshold = max(0.55, duration_median * 2.2)
    word_intensity_values = []
    for word in words:
        center = (word["start_time"] + word["end_time"]) / 2
        value = _intensity_at(intensity, center)
        if value is not None:
            word_intensity_values.append(value)
    global_intensity_median = statistics.median(word_intensity_values) if word_intensity_values else 0
    segment_rates = []
    for segment in segments:
        duration = segment["end_time"] - segment["start_time"]
        char_count = sum(len(word["text"].strip()) for word in segment["words"])
        if duration > 0.5 and char_count >= 3:
            segment_rates.append(char_count / duration)
    rate_median = statistics.median(segment_rates) if segment_rates else 0
    candidates: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for segment in segments:
        segment_duration = segment["end_time"] - segment["start_time"]
        segment_char_count = sum(len(word["text"].strip()) for word in segment["words"])
        if rate_median and segment_duration > 0.5 and segment_char_count >= 3:
            segment_rate = segment_char_count / segment_duration
            if segment_rate >= max(rate_median * 1.55, 5.0):
                candidates.append(
                    {
                        "kind": "speech_rate",
                        "segment_id": segment["id"],
                        "word_id": segment["words"][0]["id"] if segment["words"] else "",
                        "text": segment["text"],
                        "start_time": segment["start_time"],
                        "end_time": segment["end_time"],
                        "mark": "<A ",
                        "end_mark": " A>",
                        "placement": "wrap_segment",
                        "reason": f"语速 {segment_rate:.2f} 字/秒，高于中位数 {rate_median:.2f}",
                        "confidence": min(0.95, segment_rate / max(rate_median * 2.2, 0.1)),
                    }
                )
            elif segment_rate <= min(rate_median * 0.65, 2.5):
                candidates.append(
                    {
                        "kind": "speech_rate",
                        "segment_id": segment["id"],
                        "word_id": segment["words"][0]["id"] if segment["words"] else "",
                        "text": segment["text"],
                        "start_time": segment["start_time"],
                        "end_time": segment["end_time"],
                        "mark": "<L ",
                        "end_mark": " L>",
                        "placement": "wrap_segment",
                        "reason": f"语速 {segment_rate:.2f} 字/秒，低于中位数 {rate_median:.2f}",
                        "confidence": min(0.95, rate_median / max(segment_rate * 1.8, 0.1)),
                    }
                )

        strongest_word = None
        strongest_intensity = None
        for word in segment["words"]:
            center = (word["start_time"] + word["end_time"]) / 2
            value = _intensity_at(intensity, center)
            if value is None:
                continue
            if strongest_intensity is None or value > strongest_intensity:
                strongest_word = word
                strongest_intensity = value
        if strongest_word and strongest_intensity is not None and strongest_intensity >= global_intensity_median + 6:
            key = (strongest_word["id"], "emphasis")
            if key not in seen:
                seen.add(key)
                candidates.append(
                    {
                        "kind": "emphasis",
                        "segment_id": segment["id"],
                        "word_id": strongest_word["id"],
                        "text": strongest_word["text"],
                        "start_time": strongest_word["start_time"],
                        "end_time": strongest_word["end_time"],
                        "mark": "!",
                        "placement": "before",
                        "reason": f"强度 {strongest_intensity:.1f}dB，高于中位数 {global_intensity_median:.1f}dB",
                        "confidence": min(0.95, (strongest_intensity - global_intensity_median) / 14),
                    }
                )

        for word in segment["words"]:
            duration = word["end_time"] - word["start_time"]
            if duration >= long_duration_threshold and len(word["text"].strip()) <= 4:
                key = (word["id"], "lengthening")
                if key not in seen:
                    seen.add(key)
                    candidates.append(
                        {
                            "kind": "lengthening",
                            "segment_id": segment["id"],
                            "word_id": word["id"],
                            "text": word["text"],
                            "start_time": word["start_time"],
                            "end_time": word["end_time"],
                            "mark": "=",
                            "placement": "after",
                            "reason": f"持续 {duration:.2f}s，高于阈值 {long_duration_threshold:.2f}s",
                            "confidence": min(0.95, duration / max(long_duration_threshold * 1.6, 0.1)),
                        }
                    )

        if not segment["words"]:
            continue
        final_word = segment["words"][-1]
        duration = final_word["end_time"] - final_word["start_time"]
        if duration < 0.18:
            continue
        start_time = final_word["start_time"] + duration * 0.25
        end_time = final_word["end_time"] - duration * 0.15
        start_pitch = _pitch_at(pitch, start_time)
        end_pitch = _pitch_at(pitch, end_time)
        if start_pitch is None or end_pitch is None:
            continue
        contour = _pitch_contour_mark(start_pitch, end_pitch)
        if not contour:
            continue
        mark, reason, confidence = contour
        key = (final_word["id"], f"pitch-{mark}")
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "kind": "pitch",
                "segment_id": segment["id"],
                "word_id": final_word["id"],
                "text": final_word["text"],
                "start_time": final_word["start_time"],
                "end_time": final_word["end_time"],
                "mark": mark,
                "placement": "after",
                "reason": reason,
                "confidence": confidence,
            }
        )

    return candidates
