from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from inspection_pipeline import extract_features, load_records, score_anomalies

CAUSE_LABELS = {
    "power": ["전원", "전압", "과전압", "저전압", "power"],
    "comm": ["통신", "crc", "retry", "이더넷", "link", "케이블", "connector"],
    "frequency": ["주파수", "span", "frequency"],
    "boot": ["부팅", "boot"],
    "port": ["포트", "port"],
    "sensor": ["센서", "sensor"],
}


def infer_cause_label(text: str) -> str:
    t = text.casefold()
    for label, keys in CAUSE_LABELS.items():
        if any(k.casefold() in t for k in keys):
            return label
    return "other"


def classify_causes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anomalies = [r for r in rows if r.get("label") == "anomaly"]
    if not anomalies:
        return []

    has_xgboost = False
    try:
        import xgboost  # type: ignore  # noqa:F401

        has_xgboost = True
    except Exception:
        has_xgboost = False

    # 현재 단계: 레이블 데이터 누적 전까지는 규칙 기반 분류를 사용하고,
    # xgboost 설치 여부를 기록해 다음 단계 학습 준비 상태를 표시한다.
    out: list[dict[str, Any]] = []
    for row in anomalies:
        case_text = str(row.get("maintenance_case", "") or "")
        high_risk = str(row.get("high_risk_features", "") or "")
        label = infer_cause_label(case_text + " " + high_risk)
        new_row = dict(row)
        new_row["cause_top1"] = label
        new_row["cause_method"] = "xgboost_ready_rule_bootstrap" if has_xgboost else "rule_bootstrap"
        out.append(new_row)
    return out


def forecast_long_term(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # 데이터 누적 초기 단계용 베이스라인: anomaly_score 기반 위험도 스케일링.
    # 추후 device_id + timestamp 시계열 정합 후 LSTM-Transformer로 대체.
    out: list[dict[str, Any]] = []
    for row in rows:
        score = float(row.get("anomaly_score", 0.0))
        h7 = min(1.0, max(0.0, score * 1.15))
        h30 = min(1.0, max(0.0, score * 1.35))
        new_row = dict(row)
        new_row["failure_risk_h7"] = round(h7, 6)
        new_row["failure_risk_h30"] = round(h30, 6)
        new_row["forecast_method"] = "baseline_until_lstm_transformer"
        out.append(new_row)
    return out


def run(input_path: Path, output_dir: Path, table: str = "test_logs") -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_records(input_path, table=table)
    features = extract_features(records)
    scored = score_anomalies(features)
    caused = classify_causes(scored)
    forecasted = forecast_long_term(caused)

    output_csv = output_dir / "maintenance_ml_results.csv"
    fieldnames = [
        "row_index",
        "voltage",
        "current",
        "response_time_ms",
        "fail_count",
        "crc_error_rate",
        "retry_count",
        "anomaly_score",
        "label",
        "high_risk_features",
        "scoring_method",
        "maintenance_case",
        "cause_top1",
        "cause_method",
        "failure_risk_h7",
        "failure_risk_h30",
        "forecast_method",
    ]
    with output_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in forecasted:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    return {"results_csv": str(output_csv), "rows": str(len(forecasted))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JAN 정비 ML 파이프라인 (IF + 원인분류 + 장기위험)")
    parser.add_argument("--input", required=True, help="CSV/TXT/SQLite 입력 파일")
    parser.add_argument("--output-dir", required=True, help="출력 디렉터리")
    parser.add_argument("--table", default="test_logs", help="SQLite 테이블명")
    args = parser.parse_args(argv)

    result = run(Path(args.input), Path(args.output_dir), table=args.table)
    print(f"maintenance_ml_results.csv: {result['results_csv']}")
    print(f"rows: {result['rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
