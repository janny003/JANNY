import csv
import sqlite3
from pathlib import Path

from tools.inspection_pipeline import (
    FEATURE_NAMES,
    extract_features,
    generate_report,
    load_records,
    run_pipeline,
    score_anomalies,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_csv_and_txt_logs_are_loaded():
    csv_records = load_records(FIXTURE_DIR / "sample_test_log.csv")
    txt_records = load_records(FIXTURE_DIR / "sample_test_log.txt")

    assert len(csv_records) == 5
    assert len(txt_records) == 5
    assert csv_records[-1]["maintenance_case"]


def test_sqlite_log_is_loaded(tmp_path):
    db_path = tmp_path / "sample_test_log.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE test_logs (voltage REAL, current REAL, response_time_ms REAL, fail_count INTEGER, crc_error_rate REAL, retry_count INTEGER, maintenance_case TEXT)"
        )
        conn.execute(
            "INSERT INTO test_logs VALUES (12.0, 1.2, 45, 0, 0.001, 0, '')"
        )
        conn.commit()
    finally:
        conn.close()

    records = load_records(db_path)

    assert len(records) == 1
    assert float(records[0]["voltage"]) == 12.0


def test_features_include_required_columns():
    records = load_records(FIXTURE_DIR / "sample_test_log.csv")
    features = extract_features(records)

    assert len(features) == 5
    for feature_name in FEATURE_NAMES:
        assert feature_name in features[0]
        assert isinstance(features[0][feature_name], float)


def test_bad_row_is_labeled_anomaly():
    records = load_records(FIXTURE_DIR / "sample_test_log.csv")
    scored = score_anomalies(extract_features(records))

    assert scored[-1]["label"] == "anomaly"
    assert scored[-1]["anomaly_score"] > scored[0]["anomaly_score"]


def test_report_contains_required_korean_sections():
    scored = score_anomalies(extract_features(load_records(FIXTURE_DIR / "sample_test_log.csv")))
    report = generate_report(scored)

    assert "이상 판단 근거" in report
    assert "유사 정비 사례" in report
    assert "추천 점검 순서" in report
    assert "CRC" in report or "crc" in report


def test_cli_pipeline_writes_results_and_report(tmp_path):
    output = run_pipeline(FIXTURE_DIR / "sample_test_log.csv", tmp_path)

    results_path = Path(output["results_csv"])
    report_path = Path(output["report_md"])
    assert results_path.exists()
    assert report_path.exists()

    rows = list(csv.DictReader(results_path.open(encoding="utf-8-sig")))
    assert len(rows) == 5
    assert rows[-1]["label"] == "anomaly"
    assert "이상 판단 근거" in report_path.read_text(encoding="utf-8")
