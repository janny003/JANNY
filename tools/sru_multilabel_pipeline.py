from __future__ import annotations

import argparse
import csv
import json
import pickle
import re
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer


RULE_PATTERNS = [
    ("duplicate_testlog_skip", "rm_ate_gettestloginfo", "m_pcheck = \"SKIP\""),
    ("missing_equip_skip", "rm_ate_getequipinfo", "m_pcheck = \"SKIP\""),
]

SRU_KEYWORDS = {
    "sru_rf_frequency_chain": ["주파수", "span", "하향변환", "상향변환", "ocx"],
    "sru_ethernet_link": ["이더넷", "ethernet", "j4"],
    "sru_pps_timing": ["pps", "timing", "타이밍"],
    "sru_power_board": ["전원", "소모전력", "voltage", "current"],
    "sru_boot_control": ["부팅", "boot"],
    "sru_crc_comm": ["crc", "retry", "케이블", "통신"],
}


def extract_exclusion_rules(source_root: Path) -> list[dict[str, Any]]:
    files = list(source_root.rglob("*.cpp"))
    rules: list[dict[str, Any]] = []
    for file in files:
        try:
            text = file.read_text(encoding="cp949", errors="ignore")
        except Exception:
            text = file.read_text(encoding="utf-8", errors="ignore")

        lines = text.splitlines()
        for idx, line in enumerate(lines):
            for rule_name, cond_kw, skip_kw in RULE_PATTERNS:
                if skip_kw in line:
                    context = " ".join(lines[max(0, idx - 8) : idx + 2])
                    if cond_kw in context:
                        snippet = re.sub(r"\s+", " ", context)[:320]
                        rules.append({"rule": rule_name, "file": str(file), "line": idx + 1, "snippet": snippet})
    return rules


def infer_sru_labels_from_text(text: str) -> list[str]:
    labels: list[str] = []
    for sru, kws in SRU_KEYWORDS.items():
        if any(kw.lower() in text for kw in kws):
            labels.append(sru)
    if not labels:
        labels.append("sru_general")
    return sorted(set(labels))


def collect_logs(log_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in log_root.rglob("*.TXT"):
        name = p.name.lower()
        label_pass_fail = "fail" if "fail" in name else "pass" if "pass" in name else "unknown"
        text = p.stem.lower()
        sru_labels = infer_sru_labels_from_text(text)
        rows.append(
            {
                "log_path": str(p),
                "file_name": p.name,
                "module": p.parent.name,
                "pass_fail": label_pass_fail,
                "sru_labels": sru_labels,
                "candidate": 1 if label_pass_fail == "fail" else 0,
                "text": f"{p.parent.name} {p.name}".lower(),
            }
        )
    return rows


def make_estimator(algo: str):
    algo = algo.lower()
    if algo == "catboost":
        from catboost import CatBoostClassifier  # type: ignore

        return CatBoostClassifier(iterations=250, depth=6, learning_rate=0.05, verbose=False, random_seed=42)

    from lightgbm import LGBMClassifier  # type: ignore

    return LGBMClassifier(n_estimators=250, learning_rate=0.05, num_leaves=31, random_state=42)


def train_model(rows: list[dict[str, Any]], algo: str) -> dict[str, Any]:
    texts = [r["text"] for r in rows]
    y_labels = [r["sru_labels"] for r in rows]

    mlb = MultiLabelBinarizer()
    y = mlb.fit_transform(y_labels)
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    X = vec.fit_transform(texts)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)

    est = make_estimator(algo)
    clf = OneVsRestClassifier(est)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    report = classification_report(y_test, y_pred, target_names=list(mlb.classes_), zero_division=0, output_dict=True)

    return {"vectorizer": vec, "binarizer": mlb, "classifier": clf, "report": report, "algo": algo.lower()}


def predict_rows(model: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vec = model["vectorizer"]
    mlb = model["binarizer"]
    clf = model["classifier"]

    X = vec.transform([r["text"] for r in rows])
    pred_bin = clf.predict(X)
    pred_labels = mlb.inverse_transform(pred_bin)

    out: list[dict[str, Any]] = []
    for row, labels in zip(rows, pred_labels):
        if not labels:
            labels = ("sru_general",)
        out.append(
            {
                "log_path": row["log_path"],
                "pass_fail": row["pass_fail"],
                "true_labels": ";".join(row["sru_labels"]),
                "pred_labels": ";".join(labels),
                "candidate": row["candidate"],
            }
        )
    return out


def save_csv(rows: list[dict[str, Any]], path: Path) -> None:
    cols = ["log_path", "pass_fail", "true_labels", "pred_labels", "candidate"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def run(source_root: Path, log_root: Path, out_dir: Path, algo: str) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    rules = extract_exclusion_rules(source_root)
    logs = collect_logs(log_root)
    trained = train_model(logs, algo)
    preds = predict_rows(trained, logs)

    rules_path = out_dir / "fault_exclusion_rules.json"
    match_path = out_dir / "log_rule_sru_match.csv"
    model_path = out_dir / "sru_multilabel_model.pkl"
    summary_path = out_dir / "sru_multilabel_report.json"
    pred_path = out_dir / "sru_multilabel_predictions.csv"

    rules_path.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    save_csv(preds, match_path)
    with model_path.open("wb") as f:
        pickle.dump({"vectorizer": trained["vectorizer"], "binarizer": trained["binarizer"], "classifier": trained["classifier"], "algo": trained["algo"]}, f)
    summary_path.write_text(json.dumps(trained["report"], ensure_ascii=False, indent=2), encoding="utf-8")
    save_csv(preds, pred_path)

    return {
        "rules": str(rules_path),
        "match_csv": str(match_path),
        "model": str(model_path),
        "report": str(summary_path),
        "predictions": str(pred_path),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="소스 고장배제 규칙 추출 + 로그 매칭 + SRU multi-label 실학습")
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--log-root", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--algo", choices=["lightgbm", "catboost"], default="lightgbm")
    args = ap.parse_args()

    result = run(Path(args.source_root), Path(args.log_root), Path(args.out_dir), args.algo)
    for k, v in result.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
