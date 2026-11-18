"""5.1 업로드·전처리, 5.7 사진·클립 추출 — FFmpeg 래퍼.

명령은 인계서 첨부 media_commands.sh(FFmpeg 6.1.1 실행 확인)와 같다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

SEGMENT_SEC = 1500  # 단어 타임스탬프 요청당 30분 한도 → 25분 단위 분할
CLIP_MIN_SEC = 5.0
CLIP_MAX_SEC = 10.0


def _run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def extract_audio(video: Path, out_dir: Path) -> Path:
    """16kHz 모노 PCM WAV 로 음성 트랙을 분리한다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "audio.wav"
    _run(["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
    return wav


def split_audio(wav: Path, out_dir: Path, segment_sec: int = SEGMENT_SEC) -> list[tuple[Path, int]]:
    """WAV 를 segment_sec 단위로 나눈다. (파일, 원본 기준 시작 오프셋 ms) 목록을 돌려준다."""
    _run(["-i", str(wav), "-f", "segment", "-segment_time", str(segment_sec), "-c", "copy",
          str(out_dir / "part_%03d.wav")])
    parts = sorted(out_dir.glob("part_*.wav"))
    return [(p, i * segment_sec * 1000) for i, p in enumerate(parts)]


def clip_window(start_s: float, end_s: float, duration_s: float | None = None) -> tuple[float, float]:
    """근거 구간을 5~10초로 맞춘다. 짧으면 앞뒤로 늘리고, 길면 앞쪽 10초만 쓴다."""
    length = end_s - start_s
    if length > CLIP_MAX_SEC:
        return start_s, start_s + CLIP_MAX_SEC
    if length < CLIP_MIN_SEC:
        pad = (CLIP_MIN_SEC - length) / 2
        start_s, end_s = start_s - pad, end_s + pad
        if start_s < 0:
            end_s, start_s = end_s - start_s, 0.0
        if duration_s is not None and end_s > duration_s:
            start_s, end_s = max(0.0, start_s - (end_s - duration_s)), duration_s
    return start_s, end_s


def extract_frame(video: Path, at_s: float, out: Path) -> Path:
    """대표 사진: 근거 구간 안의 한 시점(기본 구간 중앙)에서 JPEG 한 장."""
    _run(["-ss", f"{at_s:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)])
    return out


def extract_clip(video: Path, start_s: float, end_s: float, out: Path) -> Path:
    """안내 클립: 소리 없는 웹 재생용 H.264 MP4."""
    _run(["-ss", f"{start_s:.3f}", "-to", f"{end_s:.3f}", "-i", str(video), "-c:v", "libx264",
          "-preset", "veryfast", "-an", "-movflags", "+faststart", str(out)])
    return out


def mmss_to_ms(value: str) -> int:
    """'MM:SS' 또는 'HH:MM:SS' → 밀리초."""
    parts = [int(p) for p in value.strip().split(":")]
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec * 1000


def ms_to_mmss(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"
