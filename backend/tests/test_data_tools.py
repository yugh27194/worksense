import csv
from pathlib import Path

from app.data_check import GOLD_COLUMNS, SCHEMAS, check_all
from app.evaluate import evaluate_job


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _data(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    _write(d / "curated/jobs.csv", SCHEMAS["curated/jobs.csv"],
           [["kitchen_helper", "주방보조원", "15123777", "", "", "", "candidate", ""]])
    _write(d / "curated/field_terms.csv", SCHEMAS["curated/field_terms.csv"], [["kitchen_helper", "식기세척기", ""]])
    _write(d / "curated/vocab_overrides.csv", SCHEMAS["curated/vocab_overrides.csv"], [])
    _write(d / "gold/kitchen_helper.csv", GOLD_COLUMNS, [
        ["마감", "1", "식기세척기에 세제 50ml 넣기", "식기세척기", "", "", "00:10", "00:15"],
        ["마감", "2", "바닥 물기 닦기", "밀대", "", "미끄럼 주의", "00:20", "00:30"],
        ["마감", "3", "쓰레기 분리 배출하기", "", "", "", "00:40", "00:50"],
    ])
    return d


def test_data_check_passes_and_catches_errors(tmp_path):
    d = _data(tmp_path)
    assert check_all(d) == []
    _write(d / "curated/jobs.csv", SCHEMAS["curated/jobs.csv"],
           [["Kitchen Helper", "", "", "", "", "", "maybe", ""]])
    errs = check_all(d)
    assert any("job_key" in e for e in errs) and any("status" in e for e in errs)


def test_evaluate_job(tmp_path):
    d = _data(tmp_path)
    _write(d / "review/kitchen_helper/steps_review.csv",
           ["order", "action_source", "easy_text", "edited_easy_text", "decision"], [
               ["1", "바닥의 물기를 닦기", "밀대로 바닥 물을 닦아요.", "", "approve"],
               ["2", "식기세척기에 세제 50ml 넣기", "식기세척기에 세제를 넣어요.", "", "edit"],
           ])
    r = evaluate_job(d, "kitchen_helper")
    assert r["matched"] == 2
    assert r["missing_steps"] == ["쓰레기 분리 배출하기"]
    assert r["order_errors"] == 1
    assert "1번 단계: 50ml" in r["key_info_lost"]
    assert r["approved"] == 2
