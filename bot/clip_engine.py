"""Pure pipeline for auto-clipping long videos into vertical 9:16 shorts.

No Telegram dependencies. Given a source (URL or local file) and an LLM/Whisper
provider, produces N short vertical clips with burned-in subtitles.

Requires `ffmpeg` and `yt-dlp` available on PATH.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Iterable, Optional


logger = logging.getLogger(__name__)


# --- data types ---------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Highlight:
    start: float
    end: float
    title: str
    hook: str


@dataclass(frozen=True)
class ClipResult:
    path: Path
    highlight: Highlight


# Callable signatures used by the engine.
# Whisper verbose_json-like transcription.
TranscribeFn = Callable[[Path], Awaitable[list[Segment]]]
# LLM text completion: (system, user) -> str.
LLMFn = Callable[[str, str], Awaitable[str]]


# --- download -----------------------------------------------------------


_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def is_url(source: str) -> bool:
    return bool(_URL_RE.match(source.strip()))


_VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}


async def download_from_url(url: str, workdir: Path) -> Path:
    """Download video via cascade: yt-dlp → Cobalt API → pytubefix. First success wins."""
    errors: list[str] = []
    for label, fn in (
        ("yt-dlp", _download_with_yt_dlp),
        ("cobalt", _download_with_cobalt),
        ("pytubefix", _download_with_pytubefix),
    ):
        try:
            path = await fn(url, workdir)
            logger.info("download ok via %s: %s", label, path.name)
            return path
        except Exception as e:  # noqa: BLE001
            msg = str(e).splitlines()[-1][:300] if str(e) else e.__class__.__name__
            logger.warning("%s failed: %s", label, msg)
            errors.append(f"{label}: {msg}")
    raise RuntimeError("All downloaders failed.\n" + "\n".join(errors))


async def _download_with_yt_dlp(url: str, workdir: Path) -> Path:
    output_template = str(workdir / "source.%(ext)s")
    cmd = _yt_dlp_cmd() + [
        "--no-playlist",
        "--no-warnings",
        "-f",
        "bv*[height<=1080]+ba/b[height<=1080]/best",
        "--merge-output-format",
        "mp4",
        "--extractor-args",
        "youtube:player_client=default,android_tv,mweb",
    ]
    cookies = os.environ.get("YT_DLP_COOKIES", "").strip()
    if cookies and Path(cookies).is_file():
        cmd += ["--cookies", cookies]
    elif cookies:
        logger.warning("YT_DLP_COOKIES set but file not found: %s", cookies)
    cmd += ["-o", output_template, url]
    await _run(cmd, "yt-dlp")
    return _pick_downloaded(workdir, "yt-dlp")


async def _download_with_cobalt(url: str, workdir: Path) -> Path:
    """Cobalt API (https://github.com/imputnet/cobalt). Works without YouTube cookies."""
    import aiohttp

    api_base = os.environ.get("COBALT_API_URL", "https://api.cobalt.tools/").rstrip("/")
    payload = {
        "url": url,
        "videoQuality": "1080",
        "filenameStyle": "basic",
    }
    timeout = aiohttp.ClientTimeout(total=180)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            api_base + "/",
            json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        ) as r:
            data = await r.json(content_type=None)
        status = data.get("status")
        if status in ("error", "rate-limit"):
            raise RuntimeError(f"cobalt: {data.get('error', {}).get('code') or data}")
        if status not in ("tunnel", "redirect", "stream"):
            raise RuntimeError(f"cobalt: unexpected status {status!r}: {data}")
        stream_url = data.get("url")
        if not stream_url:
            raise RuntimeError(f"cobalt: no url in response: {data}")
        dest = workdir / "source.mp4"
        async with session.get(stream_url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"cobalt stream HTTP {resp.status}")
            with dest.open("wb") as fh:
                async for chunk in resp.content.iter_chunked(1 << 16):
                    fh.write(chunk)
    if dest.stat().st_size < 1024:
        raise RuntimeError("cobalt: downloaded file is empty")
    return dest


async def _download_with_pytubefix(url: str, workdir: Path) -> Path:
    """pytubefix (https://github.com/JuanBindez/pytubefix). YouTube-only."""
    if "youtube.com" not in url and "youtu.be" not in url:
        raise RuntimeError("pytubefix only supports YouTube")
    from pytubefix import YouTube

    def _run_blocking() -> Path:
        yt = YouTube(url)
        stream = (
            yt.streams.filter(progressive=True, file_extension="mp4")
            .order_by("resolution")
            .desc()
            .first()
        )
        if stream is None:
            raise RuntimeError("pytubefix: no progressive mp4 stream found")
        path = stream.download(output_path=str(workdir), filename="source.mp4")
        return Path(path)

    return await asyncio.to_thread(_run_blocking)


def _pick_downloaded(workdir: Path, label: str) -> Path:
    for candidate in workdir.glob("source.*"):
        if candidate.suffix.lower() in _VIDEO_SUFFIXES:
            return candidate
    raise RuntimeError(f"{label} finished but no output file was produced")


# --- audio extraction & transcription -----------------------------------


async def extract_audio_mp3(video_path: Path, out_path: Path, bitrate: str = "64k") -> Path:
    """Extract mono mp3 at low bitrate to stay under Whisper's 25 MB limit."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        bitrate,
        str(out_path),
    ]
    await _run(cmd, "ffmpeg audio extract")
    return out_path


# --- highlight picking --------------------------------------------------


HIGHLIGHT_SYSTEM_PROMPT = (
    "You select viral short-form highlights from long video transcripts. "
    "Return ONLY valid JSON: a list of objects with keys "
    "start (float seconds), end (float seconds), title (short catchy title, "
    "max 60 chars), hook (one-sentence TikTok/Reels hook, max 140 chars). "
    "Each highlight must be a self-contained moment with a clear idea, "
    "strong opening, and a payoff. Prefer moments with emotion, humor, "
    "surprise, or a concrete takeaway. No overlap between highlights. "
    "Respect the requested duration range."
)


def _format_transcript_for_llm(segments: Iterable[Segment], char_limit: int = 12000) -> str:
    lines: list[str] = []
    total = 0
    for seg in segments:
        line = f"[{seg.start:.1f}-{seg.end:.1f}] {seg.text.strip()}"
        total += len(line) + 1
        if total > char_limit:
            lines.append("...(truncated)")
            break
        lines.append(line)
    return "\n".join(lines)


async def pick_highlights(
    segments: list[Segment],
    count: int,
    target_duration_sec: int,
    llm: LLMFn,
) -> list[Highlight]:
    if not segments:
        return []

    transcript = _format_transcript_for_llm(segments)
    min_dur = max(10, target_duration_sec - 15)
    max_dur = target_duration_sec + 15

    user_prompt = (
        f"Pick exactly {count} highlights from this transcript. "
        f"Each highlight must be between {min_dur} and {max_dur} seconds long. "
        f"Target length ~{target_duration_sec}s.\n\n"
        f"Transcript (timestamps in seconds):\n{transcript}\n\n"
        "Return JSON only. No prose, no code fences."
    )

    raw = await llm(HIGHLIGHT_SYSTEM_PROMPT, user_prompt)
    data = _parse_json_list(raw)

    highlights: list[Highlight] = []
    for item in data:
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        highlights.append(
            Highlight(
                start=start,
                end=end,
                title=str(item.get("title", "")).strip()[:80] or "Clip",
                hook=str(item.get("hook", "")).strip()[:200],
            )
        )
    return highlights[:count]


def _parse_json_list(raw: str) -> list[dict]:
    """Forgiving JSON parser: strips code fences, finds the first [...] block."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if isinstance(parsed, dict) and "highlights" in parsed:
        parsed = parsed["highlights"]
    if not isinstance(parsed, list):
        raise ValueError("LLM did not return a JSON list")
    return parsed


# --- clip rendering -----------------------------------------------------


def _segments_for_window(
    segments: Iterable[Segment], start: float, end: float
) -> list[Segment]:
    """Slice segments to a [start, end] window, times rebased to 0."""
    result: list[Segment] = []
    for seg in segments:
        if seg.end <= start or seg.start >= end:
            continue
        s = max(seg.start, start) - start
        e = min(seg.end, end) - start
        if e - s < 0.2:
            continue
        result.append(Segment(start=s, end=e, text=seg.text.strip()))
    return result


def _srt_timestamp(t: float) -> str:
    if t < 0:
        t = 0
    hours = int(t // 3600)
    minutes = int((t % 3600) // 60)
    seconds = int(t % 60)
    millis = int(round((t - int(t)) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def build_srt(segments: list[Segment]) -> str:
    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        lines.append(str(idx))
        lines.append(f"{_srt_timestamp(seg.start)} --> {_srt_timestamp(seg.end)}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


SUBTITLE_STYLE = (
    "FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
    "Alignment=2,MarginV=60"
)


async def render_clip(
    source_video: Path,
    segments: list[Segment],
    highlight: Highlight,
    output_path: Path,
    workdir: Path,
    burn_subtitles: bool = True,
) -> Path:
    """Cut, reframe to 9:16 via center-crop, and optionally burn subtitles."""
    duration = highlight.end - highlight.start
    clip_segments = _segments_for_window(segments, highlight.start, highlight.end)

    vf_parts = [
        # 9:16 center-crop then scale to 1080x1920.
        "crop=min(iw\\,ih*9/16):min(ih\\,iw*16/9)",
        "scale=1080:1920:force_original_aspect_ratio=decrease",
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
    ]
    if burn_subtitles and clip_segments:
        srt_path = workdir / f"{output_path.stem}.srt"
        srt_path.write_text(build_srt(clip_segments), encoding="utf-8")
        escaped = _escape_ffmpeg_filter_path(str(srt_path))
        vf_parts.append(f"subtitles='{escaped}':force_style='{SUBTITLE_STYLE}'")

    vf = ",".join(vf_parts)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{highlight.start:.3f}",
        "-i",
        str(source_video),
        "-t",
        f"{duration:.3f}",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    await _run(cmd, "ffmpeg render")
    return output_path


def _escape_ffmpeg_filter_path(path: str) -> str:
    """ffmpeg subtitles filter is picky about Windows paths and colons."""
    # Replace backslashes, escape the drive-letter colon.
    normalized = path.replace("\\", "/")
    normalized = normalized.replace(":", "\\:")
    return normalized


# --- high-level orchestration ------------------------------------------


@dataclass(frozen=True)
class ClipJobInput:
    source_video: Path
    count: int
    target_duration_sec: int
    burn_subtitles: bool = True


async def run_clip_job(
    job: ClipJobInput,
    transcribe: TranscribeFn,
    llm: LLMFn,
    workdir: Path,
    progress: Optional[Callable[[str], Awaitable[None]]] = None,
) -> list[ClipResult]:
    async def _report(msg: str) -> None:
        if progress is not None:
            try:
                await progress(msg)
            except Exception:  # noqa: BLE001
                logger.warning("progress callback failed", exc_info=True)

    await _report("🎧 Извлекаю аудио...")
    audio_path = workdir / "audio.mp3"
    await extract_audio_mp3(job.source_video, audio_path)

    await _report("📝 Транскрибирую...")
    segments = await transcribe(audio_path)
    if not segments:
        raise RuntimeError("Транскрипция пустая — в видео не найдено речи")

    await _report(f"🧠 Ищу {job.count} лучших моментов...")
    highlights = await pick_highlights(segments, job.count, job.target_duration_sec, llm)
    if not highlights:
        raise RuntimeError("LLM не смог выделить хайлайты")

    results: list[ClipResult] = []
    for idx, highlight in enumerate(highlights, start=1):
        await _report(f"🎬 Рендерю клип {idx}/{len(highlights)}...")
        out_path = workdir / f"clip_{idx:02d}.mp4"
        await render_clip(
            job.source_video,
            segments,
            highlight,
            out_path,
            workdir,
            burn_subtitles=job.burn_subtitles,
        )
        results.append(ClipResult(path=out_path, highlight=highlight))
    return results


# --- utilities ----------------------------------------------------------


async def _run(cmd: list[str], label: str) -> None:
    logger.info("%s: %s", label, " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        tail = (stderr or b"").decode("utf-8", errors="replace")[-1500:]
        raise RuntimeError(f"{label} failed (exit {proc.returncode}): {tail}")


def _yt_dlp_cmd() -> list[str]:
    """Prefer the yt-dlp CLI if on PATH; fall back to `python -m yt_dlp`."""
    cli = shutil.which("yt-dlp")
    if cli:
        return [cli]
    return [sys.executable, "-m", "yt_dlp"]


def _yt_dlp_available() -> bool:
    return shutil.which("yt-dlp") is not None or importlib.util.find_spec("yt_dlp") is not None


def ensure_tools_available() -> list[str]:
    """Return list of missing binaries (ffmpeg, yt-dlp)."""
    missing: list[str] = []
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    if not _yt_dlp_available():
        missing.append("yt-dlp")
    return missing


def make_workdir(prefix: str = "clips_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))
