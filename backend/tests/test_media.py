import shutil
import subprocess

import pytest

from app.pipeline.media import clip_window, extract_audio, extract_clip, extract_frame, mmss_to_ms, ms_to_mmss


def test_clip_window():
    assert clip_window(12.0, 19.5) == (12.0, 19.5)       # 5~10초면 그대로
    assert clip_window(10.0, 30.0) == (10.0, 20.0)       # 길면 앞쪽 10초
    assert clip_window(10.0, 12.0) == (8.5, 13.5)        # 짧으면 앞뒤로 늘림
    assert clip_window(0.5, 1.5) == (0.0, 5.0)           # 영상 시작 경계
    assert clip_window(58.0, 59.0, duration_s=60.0) == (55.0, 60.0)


def test_mmss():
    assert mmss_to_ms("01:05") == 65_000
    assert mmss_to_ms("1:02:03") == 3_723_000
    assert ms_to_mmss(65_400) == "01:05"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 필요")
def test_ffmpeg_pipeline(tmp_path):
    video = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=12:size=320x240:rate=10",
                    "-f", "lavfi", "-i", "sine=duration=12", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                    str(video)], check=True)
    wav = extract_audio(video, tmp_path)
    assert wav.stat().st_size > 0
    assert extract_frame(video, 6.0, tmp_path / "f.jpg").stat().st_size > 0
    assert extract_clip(video, *clip_window(3.0, 4.0), tmp_path / "c.mp4").stat().st_size > 0
