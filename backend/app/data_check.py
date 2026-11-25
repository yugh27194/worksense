"""data/curated·data/gold 표 형식 검사. 파이프라인을 돌리기 전에 실행한다.

실행: python -m app.data_check            (저장소 루트의 data/ 를 검사)
      python -m app.data_check path/to/data
노트북에서: from app.data_check import check_all; check_all("../data")
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

MMSS = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
JOB_KEY = re.compile(r"^[a-z0-9_]+$")

SCHEMAS = {
    "curated/jobs.csv": ["job_key", "job_name", "public_video_id", "video_file", "ncs_duty_cd", "job_cd", "status",
                         "note"],
    "curated/field_terms.csv": ["job_key", "term", "description"],
    "curated/vocab_overrides.csv": ["word", "action", "note"],
}
GOLD_COLUMNS = ["task_name", "order", "action", "tools", "location", "cautions", "evidence_start", "evidence_end"]


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def check_all(data_dir: str | Path = "data") -> list[str]:
    root = Path(data_dir)
    errors: list[str] = []

    for rel, cols in SCHEMAS.items():
        p = root / rel
        if not p.exists():
            errors.append(f"{rel}: 파일 없음")
            continue
        header, _ = _read(p)
        if header != cols:
            errors.append(f"{rel}: 열 이름이 다름. 기대값 {cols}, 실제 {header}")

    job_keys: set[str] = set()
    if (root / "curated/jobs.csv").exists():
        _, jobs = _read(root / "curated/jobs.csv")
        for i, row in enumerate(jobs, start=2):
            k = row.get("job_key", "")
            if not JOB_KEY.match(k):
                errors.append(f"jobs.csv {i}행: job_key '{k}' 는 영문 소문자·숫자·_ 만 쓴다")
            if k in job_keys:
                errors.append(f"jobs.csv {i}행: job_key '{k}' 중복")
            job_keys.add(k)
            if not row.get("job_name"):
                errors.append(f"jobs.csv {i}행: job_name 비어 있음")
            if row.get("status") not in ("candidate", "confirmed"):
                errors.append(f"jobs.csv {i}행: status 는 candidate 또는 confirmed")
            vf = row.get("video_file")
            if vf and not (root / "raw/media" / vf).exists():
                errors.append(f"jobs.csv {i}행: data/raw/media/{vf} 없음 (영상은 git 에 안 올라가므로 따로 전달)")

    if (root / "curated/field_terms.csv").exists():
        _, terms = _read(root / "curated/field_terms.csv")
        for i, row in enumerate(terms, start=2):
            if row.get("job_key") not in job_keys:
                errors.append(f"field_terms.csv {i}행: jobs.csv 에 없는 job_key '{row.get('job_key')}'")
            if not row.get("term") or " " in row["term"]:
                errors.append(f"field_terms.csv {i}행: term 은 띄어쓰기 없는 한 단어")

    if (root / "curated/vocab_overrides.csv").exists():
        _, vo = _read(root / "curated/vocab_overrides.csv")
        for i, row in enumerate(vo, start=2):
            if row.get("action") not in ("ignore", "hard"):
                errors.append(f"vocab_overrides.csv {i}행: action 은 ignore(검토 제외) 또는 hard(항상 검토)")

    for p in sorted((root / "gold").glob("*.csv")):
        if p.name.startswith("_"):
            continue
        if p.stem not in job_keys:
            errors.append(f"gold/{p.name}: 파일 이름이 jobs.csv 의 job_key 가 아님")
        header, rows = _read(p)
        if header != GOLD_COLUMNS:
            errors.append(f"gold/{p.name}: 열 이름이 다름. 기대값 {GOLD_COLUMNS}")
            continue
        for i, row in enumerate(rows, start=2):
            if not row["order"].isdigit():
                errors.append(f"gold/{p.name} {i}행: order 는 숫자")
            if not row["action"]:
                errors.append(f"gold/{p.name} {i}행: action 비어 있음")
            for c in ("evidence_start", "evidence_end"):
                if row[c] and not MMSS.match(row[c]):
                    errors.append(f"gold/{p.name} {i}행: {c} 는 MM:SS")
    return errors


def main() -> None:
    default = Path(__file__).resolve().parents[2] / "data"
    errs = check_all(sys.argv[1] if len(sys.argv) > 1 else default)
    for e in errs:
        print("✗", e)
    print("통과" if not errs else f"{len(errs)}건 수정 필요")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
