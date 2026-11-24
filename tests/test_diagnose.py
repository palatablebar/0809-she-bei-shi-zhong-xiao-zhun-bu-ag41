import csv
import io
import json

import pytest

from app.business import DomainIssue
from app.evidence.render import artifact
from app.intake.schema import HEADER
from app.modules.pipeline import run
from app.review.service import execute, review


def pack(records):
    stream = io.StringIO(newline="")
    csv.writer(stream).writerows([HEADER, *records])
    return stream.getvalue().encode()


# 检查点确认插值基准，读数偏离：设备漂移。
DRIFT = [
    ("D00101", "D001", "sync", "100", "1000", "0", "交接明细"),
    ("D00102", "D001", "sync", "200", "1200", "0", "复核底稿"),
    ("D00103", "D001", "reading", "150", "1106", "3", "夜间读数"),
    ("D00104", "D001", "check", "0", "1100", "0", "已对照来源"),
]
# 检查点确认读数，基准偏离，且相邻同步段速率突变：基准跳变。
JUMP = [
    ("J00101", "J001", "sync", "10", "40", "0", "交接明细"),
    ("J00102", "J001", "sync", "20", "50", "0", "复核底稿"),
    ("J00103", "J001", "sync", "30", "81", "0", "补录同步"),
    ("J00104", "J001", "reading", "25", "55", "2", "夜间读数"),
    ("J00105", "J001", "check", "0", "55", "0", "已对照来源"),
]
# 检查点确认读数，但同步段速率平滑：证据冲突，保留不确定。
SMOOTH = [
    ("U00101", "U001", "sync", "10", "40", "0", "交接明细"),
    ("U00102", "U001", "sync", "20", "50", "0", "复核底稿"),
    ("U00103", "U001", "sync", "30", "60", "0", "补录同步"),
    ("U00104", "U001", "reading", "15", "48", "2", "夜间读数"),
    ("U00105", "U001", "check", "0", "48", "0", "已对照来源"),
]
# 基准、读数、检查点三方互不一致：证据不足。
SPLIT = [
    ("U00201", "U002", "sync", "10", "40", "0", "交接明细"),
    ("U00202", "U002", "sync", "20", "50", "0", "复核底稿"),
    ("U00203", "U002", "reading", "15", "50", "2", "夜间读数"),
    ("U00204", "U002", "check", "0", "47", "0", "已对照来源"),
]
# 读数落在同步点覆盖范围外：结构性异常，无法归因。
GAP = [
    ("G00101", "G001", "sync", "10", "40", "0", "交接明细"),
    ("G00102", "G001", "sync", "20", "51", "0", "复核底稿"),
    ("G00103", "G001", "reading", "25", "60", "0", "夜间读数"),
    ("G00104", "G001", "check", "0", "60", "0", "已对照来源"),
]
# 一条坏行（列数不符）加一组漂移：隔离未清零不得发布。
DIRTY_LINE = ("ERR1", "D001", "sync", "0", "0", "0", "列多一项", "意外分隔")


def case_of(data, code, stage=5):
    return next(c for c in run(data, stage)["cases"] if c["case"] == code)


def test_drift_attributed_to_device():
    diagnosis = case_of(pack(DRIFT), "D001")["diagnosis"]
    assert diagnosis["cause"] == "DEVICE_DRIFT"
    assert diagnosis["affected"] == ["D00103"]
    assert diagnosis["evidence"] == {
        "status": "OFFSET_LIMIT",
        "residual_ms": -6,
        "check_delta_ms": 0,
        "reading_delta_ms": 6,
        "before_tick": 100,
        "after_tick": 200,
        "rate_break": None,
    }


def test_baseline_jump_corroborated_by_rate_break():
    diagnosis = case_of(pack(JUMP), "J001")["diagnosis"]
    assert diagnosis["cause"] == "BASELINE_JUMP"
    assert diagnosis["affected"] == ["J00104"]
    assert diagnosis["evidence"]["rate_break"] is True
    assert diagnosis["evidence"]["reading_delta_ms"] == 0


def test_smooth_segments_conflict_stays_uncertain():
    diagnosis = case_of(pack(SMOOTH), "U001")["diagnosis"]
    assert diagnosis["cause"] == "INSUFFICIENT_EVIDENCE"
    assert diagnosis["evidence"]["rate_break"] is False


def test_all_sources_disagree_stays_uncertain():
    diagnosis = case_of(pack(SPLIT), "U002")["diagnosis"]
    assert diagnosis["cause"] == "INSUFFICIENT_EVIDENCE"


def test_structural_gap_stays_uncertain_and_marks_reading():
    item = case_of(pack(GAP), "G001")
    assert item["status"] == "OUTSIDE_SYNC"
    assert item["diagnosis"]["cause"] == "INSUFFICIENT_EVIDENCE"
    assert item["diagnosis"]["affected"] == ["G00103"]
    assert item["diagnosis"]["evidence"]["status"] == "OUTSIDE_SYNC"


def test_ready_cases_carry_no_diagnosis(clean):
    report = run(clean)
    assert all("diagnosis" not in case for case in report["cases"])
    assert report["balance"]["anomalies"] == 0


def test_conflict_does_not_block_unrelated_cases():
    report = run(pack(DRIFT + SMOOTH))
    causes = {case["case"]: case["diagnosis"]["cause"] for case in report["cases"]}
    assert causes == {"D001": "DEVICE_DRIFT", "U001": "INSUFFICIENT_EVIDENCE"}
    checks = report["balance"]
    assert (checks["anomalies"], checks["diagnosed"]) == (2, 2)
    assert checks["releasable"] is True


def test_rerun_of_same_source_adds_no_diagnostics(store):
    data = pack(DRIFT + JUMP)
    first = execute(store, data)
    second = execute(store, data)
    assert first == second and len(store.list()) == 1
    diagnoses = lambda run: {
        case["case"]: case["diagnosis"] for case in run["report"]["cases"]
    }
    assert diagnoses(second) == diagnoses(first)


def test_late_data_never_rewrites_published_conclusion(store):
    published = execute(store, pack(DRIFT))
    review(store, published["id"], dict(revision=0, status="APPROVED", note="夜班诊断已发布"))
    late = execute(store, pack(DRIFT + JUMP))
    assert late["id"] != published["id"] and len(store.list()) == 2
    kept = store.load(published["id"])
    assert (kept["status"], kept["revision"]) == ("APPROVED", 1)
    assert [case["case"] for case in kept["report"]["cases"]] == ["D001"]
    assert kept["report"]["cases"][0]["diagnosis"]["cause"] == "DEVICE_DRIFT"


def test_release_requires_reconciled_diagnoses(store):
    report = run(pack(DRIFT + JUMP + SMOOTH + SPLIT))
    checks = report["balance"]
    assert checks["balanced"] and checks["anomalies"] == 4 and checks["diagnosed"] == 4
    assert checks["causes"] == {
        "DEVICE_DRIFT": 1,
        "BASELINE_JUMP": 1,
        "INSUFFICIENT_EVIDENCE": 2,
    }
    assert checks["releasable"] is True
    batch = execute(store, pack(DRIFT + JUMP + SMOOTH + SPLIT))
    output = review(
        store, batch["id"], dict(revision=0, status="APPROVED", note="异常已全部归因")
    )
    assert output["status"] == "APPROVED"


def test_unresolved_isolation_still_blocks_publish(store):
    batch = execute(store, pack(DRIFT + [DIRTY_LINE]))
    assert batch["report"]["balance"]["releasable"] is False
    with pytest.raises(DomainIssue, match="UNRESOLVED_ISSUES"):
        review(store, batch["id"], dict(revision=0, status="APPROVED", note="试图带隔离签发"))


def test_published_evidence_carries_diagnosis(store):
    output = json.loads(artifact(execute(store, pack(DRIFT))))
    case = output["cases"][0]
    assert case["diagnosis"]["cause"] == "DEVICE_DRIFT"
    assert case["diagnosis"]["affected"] == ["D00103"]
    assert output["balance"]["causes"] == {"DEVICE_DRIFT": 1}


def test_shift_sample_is_diagnosable_and_releasable(client):
    response = client.get("/examples/shift")
    assert response.status_code == 200
    report = run(response.data)
    assert [case["diagnosis"]["cause"] for case in report["cases"]] == [
        "DEVICE_DRIFT",
        "BASELINE_JUMP",
        "INSUFFICIENT_EVIDENCE",
        "INSUFFICIENT_EVIDENCE",
    ]
    assert report["balance"]["releasable"] is True
