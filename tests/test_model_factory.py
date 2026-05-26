import json
from pathlib import Path

from tools.model_factory import create_models_from_log

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_create_three_model_artifacts_from_sample_log(tmp_path):
    output = create_models_from_log(FIXTURE_DIR / "sample_test_log.csv", tmp_path)

    assert output["anomaly_model"].exists()
    assert output["fault_classifier"].exists()
    assert output["long_term_predictor"].exists()
    assert output["manifest"].exists()

    manifest = json.loads(output["manifest"].read_text(encoding="utf-8"))
    assert manifest["models"]["anomaly_detection"]["requested_algorithm"] == "Robust Z-score + IsolationForest"
    assert "LightGBM" in manifest["models"]["fault_cause_classification"]["requested_algorithm"]
    assert "30/60/90" in manifest["models"]["long_term_failure_prediction"]["requested_algorithm"]


def test_model_manifest_records_roles_and_features(tmp_path):
    output = create_models_from_log(FIXTURE_DIR / "sample_test_log.csv", tmp_path)
    manifest = json.loads(output["manifest"].read_text(encoding="utf-8"))

    assert manifest["feature_names"] == [
        "voltage",
        "current",
        "response_time_ms",
        "fail_count",
        "crc_error_rate",
        "retry_count",
    ]
    assert manifest["models"]["anomaly_detection"]["role_ko"] == "이상탐지 모델"
    assert manifest["models"]["fault_cause_classification"]["role_ko"] == "고장 원인 분류 모델"
    assert manifest["models"]["long_term_failure_prediction"]["role_ko"] == "단기 고장 예측 모델(30/60/90일)"
