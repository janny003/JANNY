from __future__ import annotations

import argparse
import csv
import math
import re
import sqlite3
import statistics
from pathlib import Path
from typing import Any

FEATURE_NAMES = [
    "voltage",
    "current",
    "response_time_ms",
    "fail_count",
    "crc_error_rate",
    "retry_count",
]

ALIASES = {
    "voltage": ["voltage", "전압", "volt", "v"],
    "current": ["current", "전류", "amp", "a"],
    "response_time_ms": ["response_time_ms", "response_ms", "응답시간", "응답시간_ms", "latency_ms"],
    "fail_count": ["fail_count", "failure_count", "실패횟수", "failures"],
    "crc_error_rate": ["crc_error_rate", "crc_errors", "CRC 오류율", "crc_error_pct"],
    "retry_count": ["retry_count", "retries", "통신 재시도 횟수", "재시도횟수"],
    "maintenance_case": ["maintenance_case", "정비사례", "정비 사례", "maintenance", "case"],
}

_ALIAS_LOOKUP = {alias.casefold().strip(): key for key, aliases in ALIASES.items() for alias in aliases}

FEATURE_KO = {
    "voltage": "전압",
    "current": "전류",
    "response_time_ms": "응답 시간",
    "fail_count": "실패 횟수",
    "crc_error_rate": "CRC 오류율",
    "retry_count": "재시도 횟수",
}

INSPECTION_ORDER = [
    ("voltage", "전원/전압 안정성 확인: 전원공급기, 접지, 과전압/저전압 이력을 먼저 점검"),
    ("current", "전류/부하 확인: 모터·센서 부하, 단락, 과열 흔적을 확인"),
    ("crc_error_rate", "통신 무결성 확인: 케이블, 커넥터 체결, 차폐/노이즈, CRC 오류 로그를 점검"),
    ("response_time_ms", "응답 시간 확인: 장비 부하, 타임아웃 설정, 프로세스 지연 구간을 확인"),
    ("retry_count", "재시도 이력 확인: 통신 재시도 증가 시점과 주변 이벤트를 대조"),
    ("fail_count", "실패 횟수 확인: 반복 실패 단계와 최근 정비 후 재발 여부를 확인"),
]


def load_records(path: Path | str, table: str = "test_logs") -> list[dict[str, Any]]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _load_csv(path)
    if suffix == ".txt":
        return _load_txt(path)
    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return _load_sqlite(path, table)
    raise ValueError(f"지원하지 않는 입력 형식입니다: {path.suffix}")


def extract_features(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        normalized = _normalize_record(record)
        row: dict[str, Any] = {"row_index": index}
        for name in FEATURE_NAMES:
            row[name] = _to_float(normalized.get(name), 0.0)
        row["maintenance_case"] = str(normalized.get("maintenance_case", "") or "")
        features.append(row)
    return features


def score_anomalies(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not features:
        return []

    robust_scores = [_robust_score(row, features) for row in features]
    model_scores: list[float] | None = None
    if len(features) >= 4:
        try:
            from sklearn.ensemble import IsolationForest  # type: ignore

            matrix = [[row[name] for name in FEATURE_NAMES] for row in features]
            model = IsolationForest(contamination="auto", random_state=42)
            model.fit(matrix)
            raw = [-float(value) for value in model.decision_function(matrix)]
            model_scores = _minmax(raw)
        except Exception:
            model_scores = None

    scored: list[dict[str, Any]] = []
    for row, robust in zip(features, robust_scores):
        model_score = model_scores[row["row_index"]] if model_scores is not None else min(1.0, robust / 10.0)
        extreme = _is_rule_extreme(row, features)
        combined = max(float(model_score), min(1.0, robust / 10.0))
        label = "anomaly" if robust >= 3.5 or extreme or combined >= 0.65 else "normal"
        high_risk = _dominant_features(row, features)
        new_row = dict(row)
        new_row["anomaly_score"] = round(combined, 6)
        new_row["label"] = label
        new_row["high_risk_features"] = ";".join(high_risk)
        new_row["scoring_method"] = "isolation_forest+rules" if model_scores is not None else "robust_zscore_fallback"
        scored.append(new_row)
    return scored


def generate_report(scored_rows: list[dict[str, Any]]) -> str:
    anomalies = [row for row in scored_rows if row.get("label") == "anomaly"]
    lines = [
        "# 시험 로그 ML 점검 리포트",
        "",
        f"- 총 분석 행: {len(scored_rows)}건",
        f"- 이상 의심 행: {len(anomalies)}건",
        "",
        "## 이상 판단 근거",
    ]

    if not anomalies:
        lines.append("- 현재 입력에서는 명확한 이상 패턴이 탐지되지 않았습니다.")
    else:
        for row in sorted(anomalies, key=lambda r: float(r.get("anomaly_score", 0)), reverse=True):
            reasons = _reason_sentences(row)
            lines.append(
                f"- 행 {int(row.get('row_index', 0)) + 1}: 이상 점수 {float(row.get('anomaly_score', 0)):.3f}, "
                f"주요 원인: {', '.join(reasons) if reasons else '복합 지표가 정상 범위를 벗어남'}"
            )

    lines.extend(["", "## 유사 정비 사례"])
    similar_cases = _find_similar_cases(scored_rows, anomalies)
    if similar_cases:
        for case in similar_cases:
            lines.append(f"- {case}")
    else:
        lines.append("- 입력 로그 내에서 직접 비교 가능한 이전 정비 사례가 없습니다. 케이블/전원/통신 이력 DB와 추가 대조가 필요합니다.")

    lines.extend(["", "## 추천 점검 순서"])
    order = _recommended_order(anomalies)
    for idx, item in enumerate(order, 1):
        lines.append(f"{idx}. {item}")

    lines.extend([
        "",
        "## Hermes Agent 참고",
        "- 본 리포트는 Python 기반 자동 점검 결과이며, GUI/Hermes 통합 호출은 후속 작업으로 남겨둡니다.",
        "- 현장 조치 전에는 실제 계측값과 장비 안전 절차를 우선 확인하세요.",
    ])
    return "\n".join(lines) + "\n"


def run_pipeline(input_path: Path | str, output_dir: Path | str, table: str = "test_logs") -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = load_records(input_path, table=table)
    features = extract_features(records)
    scored = score_anomalies(features)
    report = generate_report(scored)

    results_path = output_dir / "inspection_results.csv"
    report_path = output_dir / "inspection_report.md"
    _write_results_csv(results_path, scored)
    report_path.write_text(report, encoding="utf-8")
    return {"results_csv": str(results_path), "report_md": str(report_path)}


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _load_txt(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    token = re.compile(r'([^:=\s][^:=]*?)\s*[:=]\s*("[^"]*"|[^\s]+)')
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        record: dict[str, Any] = {}
        for key, value in token.findall(line):
            record[key.strip()] = value.strip().strip('"')
        if record:
            records.append(record)
    return records


def _load_sqlite(path: Path, table: str) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError("SQLite table 이름이 안전하지 않습니다.")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in record.items():
        canonical = _ALIAS_LOOKUP.get(str(key).casefold().strip(), str(key).strip())
        normalized[canonical] = value
    return normalized


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return default
    return float(match.group(0))


def _median_and_mad(values: list[float]) -> tuple[float, float]:
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations)
    if mad == 0:
        # Repeated zero counters are common in good test logs.  A single retry or
        # isolated low counter should not explode to an infinite z-score, but a
        # genuinely extreme counter is still caught by the explicit rule checks.
        mad = statistics.pstdev(values) or 1.0
    return median, mad


def _robust_score(row: dict[str, Any], rows: list[dict[str, Any]]) -> float:
    max_score = 0.0
    for name in FEATURE_NAMES:
        values = [float(other[name]) for other in rows]
        median, mad = _median_and_mad(values)
        z = abs(0.6745 * (float(row[name]) - median) / mad)
        max_score = max(max_score, z)
    return max_score


def _minmax(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    if math.isclose(low, high):
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def _is_rule_extreme(row: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    for name in ("fail_count", "crc_error_rate", "retry_count"):
        values = [float(other[name]) for other in rows]
        median, mad = _median_and_mad(values)
        value = float(row[name])
        if value > median and 0.6745 * (value - median) / mad >= 3.5:
            return True
    if float(row["fail_count"]) >= 3 or float(row["retry_count"]) >= 5 or float(row["crc_error_rate"]) >= 0.05:
        return True
    return False


def _dominant_features(row: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    dominant: list[str] = []
    for name in FEATURE_NAMES:
        values = [float(other[name]) for other in rows]
        median, mad = _median_and_mad(values)
        value = float(row[name])
        z = abs(0.6745 * (value - median) / mad)
        if z >= 3.0 or (name in {"fail_count", "retry_count"} and value >= 3) or (name == "crc_error_rate" and value >= 0.05):
            dominant.append(name)
    return dominant


def _reason_sentences(row: dict[str, Any]) -> list[str]:
    features = str(row.get("high_risk_features", "")).split(";") if row.get("high_risk_features") else []
    reasons: list[str] = []
    for name in features:
        if name in FEATURE_KO:
            reasons.append(f"{FEATURE_KO[name]}={float(row[name]):g}")
    return reasons


def _find_similar_cases(scored_rows: list[dict[str, Any]], anomalies: list[dict[str, Any]]) -> list[str]:
    anomaly_features = set()
    for row in anomalies:
        anomaly_features.update(filter(None, str(row.get("high_risk_features", "")).split(";")))
    cases: list[str] = []
    seen: set[str] = set()
    for row in scored_rows:
        case = str(row.get("maintenance_case", "") or "").strip()
        row_features = set(filter(None, str(row.get("high_risk_features", "")).split(";")))
        if case and (not anomaly_features or anomaly_features.intersection(row_features)) and case not in seen:
            seen.add(case)
            overlap = ", ".join(FEATURE_KO.get(name, name) for name in sorted(anomaly_features.intersection(row_features)))
            cases.append(f"행 {int(row.get('row_index', 0)) + 1} 사례와 유사: {case}" + (f" (공통 지표: {overlap})" if overlap else ""))
    return cases


def _recommended_order(anomalies: list[dict[str, Any]]) -> list[str]:
    high_risk = set()
    for row in anomalies:
        high_risk.update(filter(None, str(row.get("high_risk_features", "")).split(";")))
    selected = [text for feature, text in INSPECTION_ORDER if feature in high_risk]
    if not selected:
        selected = [text for _, text in INSPECTION_ORDER[:3]]
    if "전원/전압 안정성 확인: 전원공급기, 접지, 과전압/저전압 이력을 먼저 점검" not in selected:
        selected.insert(0, "기본 안전 확인: 전원 차단 가능 상태, 접지, 육안 손상 여부를 먼저 확인")
    return selected


def _write_results_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ["row_index", *FEATURE_NAMES, "anomaly_score", "label", "high_risk_features", "scoring_method", "maintenance_case"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OrobrosTest 시험 로그 ML 점검 파이프라인")
    parser.add_argument("--input", required=True, help="CSV/TXT/SQLite DB 입력 파일")
    parser.add_argument("--output-dir", required=True, help="결과 파일 출력 디렉터리")
    parser.add_argument("--table", default="test_logs", help="SQLite 입력 시 읽을 테이블 이름")
    args = parser.parse_args(argv)

    output = run_pipeline(args.input, args.output_dir, table=args.table)
    print(f"inspection_results.csv: {output['results_csv']}")
    print(f"inspection_report.md: {output['report_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
