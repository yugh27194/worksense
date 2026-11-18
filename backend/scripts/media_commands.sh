#!/usr/bin/env bash
# 일머RE 미디어 전처리 명령 (인계서 5.1·5.7절). FFmpeg 6.1.1에서 실행 확인.
# 사용: bash media_commands.sh input.mp4 out_dir
set -euo pipefail
IN="$1"; OUT="${2:-out}"; mkdir -p "$OUT"

# 1) 음성 트랙 분리: Gemini 3.5 Transcribe 입력용 16kHz 모노 WAV
ffmpeg -loglevel error -y -i "$IN" -vn -ac 1 -ar 16000 -c:a pcm_s16le "$OUT/audio.wav"

# 2) 단어 타임스탬프 사용 시 요청당 30분 한도 → 25분(1500초) 단위로 분할
#    분할 파일의 시작 오프셋(n*1500초)을 전사 결과 시각에 더해 원본 시각으로 되돌린다.
ffmpeg -loglevel error -y -i "$OUT/audio.wav" -f segment -segment_time 1500 -c copy "$OUT/part_%03d.wav"

# 3) 단계별 대표 프레임: 근거 구간 안의 한 시점(예: 12.4초)
ffmpeg -loglevel error -y -ss 12.4 -i "$IN" -frames:v 1 -q:v 2 "$OUT/step03.jpg"

# 4) 단계별 안내 클립: 근거 구간을 5~10초로 맞춰 자른다(예: 12.0~19.5초), 소리 제거, 웹 재생용 faststart
ffmpeg -loglevel error -y -ss 12.0 -to 19.5 -i "$IN" -c:v libx264 -preset veryfast -an -movflags +faststart "$OUT/step03.mp4"

# 5) 결과 확인
for f in "$OUT"/audio.wav "$OUT"/step03.jpg "$OUT"/step03.mp4; do
  ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,sample_rate,channels -of compact "$f"
done
