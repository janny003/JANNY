from __future__ import annotations

import argparse
import json
import pickle
import statistics
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.inspection_pipeline import FEATURE_NAMES, extract_features, load_records, score_anomalies

MODEL_ROLES = {
    "anomaly_detection": {
        "role_ko": "이상탐지 모델",
        "requested_algorithm": "Robust Z-score + IsolationForest",
        "artifact": "isolation_forest_anomaly_model.pkl",
    },
    "fault_cause_classification": {
        "role_ko": "고장 원인 분류 모델",
        "requested_algorithm": "LightGBM (fallback: CatBoost/XGBoost)",
        "artifact": "lightgbm_fault_cause_classifier.pkl",
    },
    "long_term_failure_prediction": {
        "role_ko": "단기 고장 예측 모델(30/60/90일)",
        "requested_algorithm": "LightGBM binary classifiers (30/60/90)",
        "artifact": "lightgbm_short_term_failure_predictor.pkl",
    },
}


def create_models_from_log(input_path: Path | str, output_dir: Path | str, table: str = "test_logs") -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_records(input_path, table=table)
    features = extract_features(records)
    if not features:
        raise ValueError("모델 생성에 사용할 로그 행이 없습니다.")

    matrix = [[float(row[name]) for name in FEATURE_NAMES] for row in features]
    scored_rows = score_anomalies(features)
    anomaly_labels = [1 if row.get("label") == "anomaly" else 0 for row in scored_rows]
    fault_labels = [_fault_cause_label(row) for row in scored_rows]

    anomaly_path = output_dir / MODEL_ROLES["anomaly_detection"]["artifact"]
    fault_path = output_dir / MODEL_ROLES["fault_cause_classification"]["artifact"]
    predictor_path = output_dir / MODEL_ROLES["long_term_failure_prediction"]["artifact"]

    anomaly_meta = _create_anomaly_combo_model(matrix, anomaly_path)
    fault_meta = _create_fault_classifier(matrix, fault_labels, fault_path)
    predictor_meta = _create_short_term_failure_predictor(scored_rows, predictor_path)

    manifest = {
        "input_path": str(Path(input_path)),
        "row_count": len(features),
        "feature_names": list(FEATURE_NAMES),
        "label_summary": {
            "anomaly_rows": int(sum(anomaly_labels)),
            "fault_causes": sorted(set(fault_labels)),
        },
        "models": {
            "anomaly_detection": {**MODEL_ROLES["anomaly_detection"], **anomaly_meta, "path": str(anomaly_path)},
            "fault_cause_classification": {**MODEL_ROLES["fault_cause_classification"], **fault_meta, "path": str(fault_path)},
            "long_term_failure_prediction": {**MODEL_ROLES["long_term_failure_prediction"], **predictor_meta, "path": str(predictor_path)},
        },
    }

    manifest_path = output_dir / "model_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "anomaly_model": anomaly_path,
        "fault_classifier": fault_path,
        "long_term_predictor": predictor_path,
        "manifest": manifest_path,
    }


def _create_anomaly_combo_model(matrix: list[list[float]], path: Path) -> dict[str, Any]:
    robust_profile = _numeric_profile(matrix)
    payload: dict[str, Any] = {
        "feature_names": FEATURE_NAMES,
        "robust_zscore_profile": robust_profile,
        "combo_logic": "robust_zscore_gate_then_iforest",
    }

    try:
        from sklearn.ensemble import IsolationForest  # type: ignore

        model = IsolationForest(contamination="auto", random_state=42)
        model.fit(matrix)
        payload["iforest_model"] = model
        _pickle_dump(payload, path)
        return {"actual_algorithm": "Robust Z-score + IsolationForest", "status": "trained"}
    except Exception as exc:
        payload["iforest_model"] = "not_available"
        payload["fallback_reason"] = str(exc)
        _pickle_dump(payload, path)
        return {
            "actual_algorithm": "Robust Z-score only fallback",
            "status": "fallback_saved",
            "fallback_reason": str(exc),
        }


def _create_fault_classifier(matrix: list[list[float]], labels: list[str], path: Path) -> dict[str, Any]:
    encoded, classes = _encode_labels(labels)
    if len(classes) < 2:
        _pickle_dump({"model": "single_class_fault_classifier", "feature_names": FEATURE_NAMES, "classes": classes}, path)
        return {"actual_algorithm": "single_class_baseline", "status": "fallback_saved", "classes": classes}

    lgbm_exc = None
    try:
        from lightgbm import LGBMClassifier  # type: ignore

        model = LGBMClassifier(n_estimators=120, learning_rate=0.05, num_leaves=31, random_state=42)
        model.fit(matrix, encoded)
        _pickle_dump({"model": model, "feature_names": FEATURE_NAMES, "classes": classes}, path)
        return {"actual_algorithm": "LightGBM", "status": "trained", "classes": classes}
    except Exception as exc:
        lgbm_exc = exc

    try:
        from catboost import CatBoostClassifier  # type: ignore

        model = CatBoostClassifier(iterations=200, depth=6, learning_rate=0.05, verbose=False, random_seed=42)
        model.fit(matrix, encoded)
        _pickle_dump({"model": model, "feature_names": FEATURE_NAMES, "classes": classes}, path)
        return {
            "actual_algorithm": "CatBoost fallback",
            "status": "fallback_trained",
            "classes": classes,
            "fallback_reason": str(lgbm_exc),
        }
    except Exception as cat_exc:
        try:
            from xgboost import XGBClassifier  # type: ignore

            model = XGBClassifier(
                n_estimators=60,
                max_depth=4,
                learning_rate=0.07,
                objective="multi:softprob" if len(classes) > 2 else "binary:logistic",
                eval_metric="mlogloss" if len(classes) > 2 else "logloss",
                random_state=42,
            )
            model.fit(matrix, encoded)
            _pickle_dump({"model": model, "feature_names": FEATURE_NAMES, "classes": classes}, path)
            return {
                "actual_algorithm": "XGBoost fallback",
                "status": "fallback_trained",
                "classes": classes,
                "fallback_reason": f"{lgbm_exc}; {cat_exc}",
            }
        except Exception as xgb_exc:
            try:
                from sklearn.ensemble import RandomForestClassifier  # type: ignore

                model = RandomForestClassifier(n_estimators=80, random_state=42, class_weight="balanced")
                model.fit(matrix, encoded)
                _pickle_dump({"model": model, "feature_names": FEATURE_NAMES, "classes": classes}, path)
                return {
                    "actual_algorithm": "RandomForest fallback",
                    "status": "fallback_trained",
                    "classes": classes,
                    "fallback_reason": f"{lgbm_exc}; {cat_exc}; {xgb_exc}",
                }
            except Exception as sk_exc:
                rules = _fault_rules_from_labels(matrix, labels)
                _pickle_dump(
                    {
                        "model": "rule_based_fault_classifier",
                        "feature_names": FEATURE_NAMES,
                        "classes": classes,
                        "rules": rules,
                    },
                    path,
                )
                return {
                    "actual_algorithm": "rule_based_fallback",
                    "status": "fallback_saved",
                    "classes": classes,
                    "fallback_reason": f"{lgbm_exc}; {cat_exc}; {xgb_exc}; {sk_exc}",
                }


def _create_short_term_failure_predictor(scored_rows: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    matrix = [[float(row[name]) for name in FEATURE_NAMES] for row in scored_rows]
    targets_30 = _future_failure_targets(scored_rows, horizon=3)
    targets_60 = _future_failure_targets(scored_rows, horizon=6)
    targets_90 = _future_failure_targets(scored_rows, horizon=9)

    try:
        from lightgbm import LGBMClassifier  # type: ignore

        models: dict[str, Any] = {}
        for key, target in (("h30", targets_30), ("h60", targets_60), ("h90", targets_90)):
            model = LGBMClassifier(n_estimators=100, learning_rate=0.05, num_leaves=31, random_state=42)
            model.fit(matrix, target)
            models[key] = model

        _pickle_dump(
            {
                "models": models,
                "feature_names": FEATURE_NAMES,
                "horizons": {"h30": 30, "h60": 60, "h90": 90},
            },
            path,
        )
        return {"actual_algorithm": "LightGBM 30/60/90", "status": "trained"}
    except Exception as exc:
        payload = {
            "model": "short_term_failure_rule_baseline",
            "actual_algorithm": "rule_based_fallback",
            "feature_names": FEATURE_NAMES,
            "horizons": {"h30": targets_30, "h60": targets_60, "h90": targets_90},
            "risk_profile": _sequence_risk_profile(matrix, targets_90),
            "fallback_reason": str(exc),
        }
        _pickle_dump(payload, path)
        return {
            "actual_algorithm": "rule_based_fallback",
            "status": "fallback_saved",
            "fallback_reason": str(exc),
        }


def _fault_cause_label(row: dict[str, Any]) -> str:
    risk = set(filter(None, str(row.get("high_risk_features", "")).split(";")))
    case = str(row.get("maintenance_case", "") or "")
    if {"crc_error_rate", "retry_count"}.intersection(risk) or "CRC" in case.upper() or "케이블" in case:
        return "communication_crc_or_cable"
    if "voltage" in risk or "전압" in case:
        return "power_voltage"
    if "current" in risk:
        return "current_load"
    if "response_time_ms" in risk:
        return "response_delay"
    if "fail_count" in risk:
        return "repeated_failure"
    return "normal"


def _future_failure_targets(scored_rows: list[dict[str, Any]], horizon: int = 3) -> list[int]:
    labels = [1 if row.get("label") == "anomaly" else 0 for row in scored_rows]
    targets: list[int] = []
    for index in range(len(labels)):
        future = labels[index + 1 : index + 1 + horizon]
        targets.append(1 if any(future) else labels[index])
    return targets


def _numeric_profile(matrix: list[list[float]]) -> dict[str, dict[str, float]]:
    columns = list(zip(*matrix))
    profile: dict[str, dict[str, float]] = {}
    for name, values_tuple in zip(FEATURE_NAMES, columns):
        values = [float(value) for value in values_tuple]
        median = statistics.median(values)
        deviations = [abs(value - median) for value in values]
        mad = statistics.median(deviations) or statistics.pstdev(values) or 1.0
        profile[name] = {"median": median, "mad": mad, "min": min(values), "max": max(values)}
    return profile


def _sequence_risk_profile(matrix: list[list[float]], targets: list[int]) -> dict[str, Any]:
    profile = _numeric_profile(matrix)
    return {
        "feature_profile": profile,
        "positive_target_count": int(sum(targets)),
        "sample_count": len(matrix),
        "risk_rule": "CRC 오류율/재시도/실패횟수/전압전류 변동 기반 단기 위험 스코어",
    }


def _encode_labels(labels: list[str]) -> tuple[list[int], list[str]]:
    classes = sorted(set(labels))
    lookup = {label: index for index, label in enumerate(classes)}
    return [lookup[label] for label in labels], classes


def _fault_rules_from_labels(matrix: list[list[float]], labels: list[str]) -> dict[str, Any]:
    rules: dict[str, Any] = {}
    for label in sorted(set(labels)):
        indexes = [i for i, item in enumerate(labels) if item == label]
        if not indexes:
            continue
        rows = [matrix[i] for i in indexes]
        rules[label] = _numeric_profile(rows)
    return rules


def _pickle_dump(payload: Any, path: Path) -> None:
    with path.open("wb") as handle:
        pickle.dump(payload, handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OrobrosTest 단기 기준 ML 모델 파일 생성")
    parser.add_argument("--input", required=True, help="CSV/TXT/SQLite DB 입력 파일")
    parser.add_argument("--output-dir", required=True, help="모델 파일 출력 디렉터리")
    parser.add_argument("--table", default="test_logs", help="SQLite 입력 시 읽을 테이블 이름")
    args = parser.parse_args(argv)

    output = create_models_from_log(args.input, args.output_dir, table=args.table)
    print(f"anomaly_model: {output['anomaly_model']}")
    print(f"fault_classifier: {output['fault_classifier']}")
    print(f"long_term_predictor: {output['long_term_predictor']}")
    print(f"manifest: {output['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
