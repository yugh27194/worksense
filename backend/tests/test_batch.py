"""일괄 생성 파이프라인 전체 흐름 (Gemini 는 가짜 응답으로 대체). 영상은 ffmpeg 로 합성한다."""
import csv
import shutil
import subprocess

import pytest

from app import batch
from app.schemas.llm import (
    EasyTextBatch,
    EasyTextItem,
    ExtractedStep,
    Gap,
    GapReport,
    StepExtraction,
    TaskExtraction,
    Transcript,
    TranscriptSegment,
)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 필요")


def fake_generate(model, contents, schema, system=None):
    if schema is Transcript:
        return Transcript(segments=[TranscriptSegment(start="00:01", end="00:04", text="식기세척기에 세제를 50ml 넣어요")])
    if schema is TaskExtraction:
        return TaskExtraction(tasks=[StepExtraction(task_name="마감 정리", steps=[
            ExtractedStep(order=1, action="식기세척기에 세제 50ml 넣기", tools=["식기세척기"], location="주방",
                          cautions=[], evidence_start="00:01", evidence_end="00:03", needs_review=False),
            ExtractedStep(order=2, action="바닥 물기 닦기", tools=["밀대"], location=None, cautions=["미끄럼 주의"],
                          evidence_start="00:05", evidence_end="00:20", needs_review=True, review_reason="밀대 위치 불명"),
        ])])
    if schema is GapReport:
        return GapReport(gaps=[Gap(source="JOBCODE", criterion="쓰레기를 분리 배출한다", related_step_order=None,
                                   gap_type="missing", note="")])
    if schema is EasyTextBatch:
        return EasyTextBatch(items=[
            EasyTextItem(order=1, easy_text="식기세척기에 세제를 넣어요.", easier_text="세제를 넣어요.", caution_text=None,
                         source_numbers=["50ml"]),
            EasyTextItem(order=2, easy_text="밀대로 바닥 물을 닦아요.", easier_text="바닥을 닦아요.",
                         caution_text="미끄러지지 않게 조심해요.", source_numbers=[]),
        ])
    raise AssertionError(schema)


@pytest.fixture
def data(tmp_path, monkeypatch):
    d = tmp_path / "data"
    (d / "curated").mkdir(parents=True)
    (d / "raw/media").mkdir(parents=True)
    (d / "raw/api").mkdir(parents=True)
    (d / "curated/jobs.csv").write_text(
        "job_key,job_name,public_video_id,video_file,ncs_duty_cd,job_cd,status,note\n"
        "kitchen_helper,주방보조원,15123777,kitchen_helper.mp4,,J1,confirmed,\n", encoding="utf-8")
    (d / "curated/field_terms.csv").write_text("job_key,term,description\nkitchen_helper,식기세척기,\n", encoding="utf-8")
    (d / "curated/vocab_overrides.csv").write_text("word,action,note\n", encoding="utf-8")
    (d / "raw/api/jobcode.csv").write_text("jobCd,jobCdNm,jobTask\nJ1,주방보조원,설거지와 주방 정리\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=25:size=320x240:rate=10",
                    "-f", "lavfi", "-i", "sine=duration=25", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                    str(d / "raw/media/kitchen_helper.mp4")], check=True)
    monkeypatch.setattr(batch, "DATA", d)
    from app.pipeline import gemini

    monkeypatch.setattr(gemini, "generate_structured", fake_generate)
    monkeypatch.setattr(gemini, "upload_file", lambda path: object())
    monkeypatch.setattr(gemini, "file_part", lambda f: "VIDEO")
    monkeypatch.setattr(gemini, "audio_part", lambda path: "AUDIO")
    monkeypatch.setenv("KRDICT_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()
    return d


def test_full_pipeline(data):
    for name in batch.STAGES:
        batch.STAGES[name]("kitchen_helper")

    tr = list(csv.DictReader((data / "review/kitchen_helper/transcript.csv").open(encoding="utf-8-sig")))
    assert tr[0]["start"] == "00:01"

    rows = list(csv.DictReader((data / "review/kitchen_helper/steps_review.csv").open(encoding="utf-8-sig")))
    assert [r["order"] for r in rows] == ["1", "2"]
    assert rows[0]["easier_text"] == "세제를 넣어요."
    assert "수치 누락: 50ml" in rows[0]["checks"]          # 5.6 자동 점검이 안내문에서 빠진 수치를 잡는다
    assert "더 쉽게 문장 도구명 누락: 식기세척기" in rows[0]["checks"]  # 「더 쉽게」 문장도 점검한다
    assert rows[1]["needs_review"] == "True"
    assert rows[0]["photo"] == "step001.jpg" and rows[0]["clip"] == "step001.mp4"
    assert (data / "work/kitchen_helper/media/step002.mp4").exists()
    assert (data / "review/kitchen_helper/gaps_unlinked.csv").exists()

    # 검수 열은 다시 내보내도 보존된다
    rows[0]["decision"] = "approve"
    batch.write_csv(data / "review/kitchen_helper/steps_review.csv", batch.REVIEW_COLUMNS, rows)
    batch.stage_export("kitchen_helper")
    again = list(csv.DictReader((data / "review/kitchen_helper/steps_review.csv").open(encoding="utf-8-sig")))
    assert again[0]["decision"] == "approve"


@pytest.mark.skipif(not __import__("os").environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL 없음")
def test_import_and_worker_screen(data, monkeypatch):
    """검수 → DB 반영 → 근로자 화면 API → 도움 단추 → 담당자 호출 목록."""
    import os

    from fastapi.testclient import TestClient

    from app import db
    from app.config import get_settings

    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    get_settings.cache_clear()
    db._pool = None

    for name in batch.STAGES:
        batch.STAGES[name]("kitchen_helper")
    path = data / "review/kitchen_helper/steps_review.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    rows[0].update(decision="edit", edited_easy_text="식기세척기에 세제를 50ml 넣어요.")
    rows[1].update(decision="reject")
    batch.write_csv(path, batch.REVIEW_COLUMNS, rows)

    from app.importer import import_job

    r = import_job("kitchen_helper")
    assert r["approved"] == 1
    import_job("kitchen_helper")  # 다시 넣어도 중복되지 않는다

    from app.main import app

    c = TestClient(app)
    wp = {"X-Workplace-Id": str(r["workplace_id"])}
    tok = c.post(f"/workplaces/{r['workplace_id']}/qr", headers=wp).json()["qr_token"]
    w = {"X-Worker-Token": tok}
    tasks = c.get("/w/manuals", headers=w).json()
    assert [t["task_name"] for t in tasks] == ["마감 정리"]
    cards = c.get(f"/w/tasks/{tasks[0]['task_id']}", headers=w).json()
    assert len(cards) == 1                                    # reject 된 단계는 안 보인다
    assert cards[0]["easy_text"] == "식기세척기에 세제를 50ml 넣어요."
    assert cards[0]["easier_text"] == "세제를 넣어요."
    assert c.get(f"/files/{cards[0]['photo_path']}").status_code == 200
    assert c.get("/files/kitchen_helper/audio.wav").status_code == 404   # 사진·클립 외 파일은 막는다

    assert c.post("/w/help", headers=w, json={"step_id": cards[0]["id"], "kind": "handoff"}).json() == {"ok": True}
    calls = c.get("/help/calls", headers=wp).json()
    assert calls[0]["task_name"] == "마감 정리"
    stats = c.get("/help/stats", headers=wp).json()
    assert stats[0]["handoff"] == 1


def test_easy_retries_only_flagged_steps(data, monkeypatch):
    """5.5: 수치·도구명 누락 단계만 문제를 알려 주고 다시 만들며, 나아진 결과만 받는다."""
    from app.pipeline import gemini

    batch.stage_preprocess("kitchen_helper")
    batch.stage_transcribe("kitchen_helper")
    batch.stage_extract("kitchen_helper")
    calls = []

    def gen(model, contents, schema, system=None):
        calls.append(contents[0])
        if len(calls) == 1:
            return fake_generate(model, contents, schema)
        return EasyTextBatch(items=[EasyTextItem(order=1, easy_text="식기세척기에 세제 50ml를 넣어요.",
                                                 easier_text="식기세척기에 세제 50ml를 넣어요.", caution_text=None,
                                                 source_numbers=["50ml"])])

    monkeypatch.setattr(gemini, "generate_structured", gen)
    batch.stage_easy("kitchen_helper")

    # 1·2번 모두 easier_text 에 도구명이 없다 → 둘 다 다시 부름. 1번만 고쳐지므로 다음 번엔 2번만 다시 부름.
    assert len(calls) == 1 + batch.EASY_RETRIES
    assert "1. 식기세척기에 세제 50ml 넣기" in calls[1] and "2. 바닥 물기 닦기" in calls[1]
    assert "easier_text 도구명 누락: 식기세척기" in calls[1]  # 문제를 프롬프트에 알려 준다
    assert "식기세척기에 세제" not in calls[2] and "2. 바닥 물기 닦기" in calls[2]
    items = {i["order"]: i for i in batch.load_json(data / "work/kitchen_helper/easy.json")["items"]}
    assert items[1]["easier_text"] == "식기세척기에 세제 50ml를 넣어요."  # 나아진 결과는 받는다
    assert items[2]["easier_text"] == "바닥을 닦아요."                    # 다시 만든 결과가 없으면 그대로


def test_public_reference_multiple_codes(data):
    """jobs.csv 코드 칸에 ';' 로 여러 코드 → 코드별로 묶고, NCS 는 수행준거만 넣는다."""
    (data / "curated/jobs.csv").write_text(
        "job_key,job_name,public_video_id,video_file,ncs_duty_cd,job_cd,status,note\n"
        "kitchen_helper,주방보조원,15123777,kitchen_helper.mp4,N1;N2,J1;J2;J9,confirmed,\n", encoding="utf-8")
    (data / "raw/api/jobcode.csv").write_text(
        "jobCd,jobCdNm,jobTask\nJ1,주방 보조원,주방정리와 기물세척\nJ2,설거지원,식기를 세척한다\n", encoding="utf-8")
    (data / "raw/api/ncs_classification.csv").write_text(
        "ncsLclasCd,ncsMclasCd,ncsSclasCd,ncsSubdCd,ncsSubdCdNm\nN,1,,,공통직무\n", encoding="utf-8")
    (data / "raw/api/ncs_ksa_N1.csv").write_text(
        "compUnitName,gbnName,gbnVal\n위생관리,수행준거,조리복을 착용할 수 있다\n위생관리,지식,미생물의 분류\n", encoding="utf-8")
    (data / "raw/api/ncs_ksa_N2.csv").write_text(
        "compUnitName,gbnName,gbnVal\n밥조리,수행준거,쌀을 씻을 수 있다\n", encoding="utf-8")

    jobcode, ncs = batch.public_reference("kitchen_helper")
    assert jobcode == "### [J1 주방 보조원]\n주방정리와 기물세척\n### [J2 설거지원]\n식기를 세척한다"  # 없는 J9 는 건너뜀
    assert "### [N1 공통직무]\n- [위생관리] 조리복을 착용할 수 있다" in ncs
    assert "### [N2 ]\n- [밥조리] 쌀을 씻을 수 있다" in ncs
    assert "미생물" not in ncs                                   # 지식·기술·태도는 제외
