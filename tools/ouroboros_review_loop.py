from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else []


def _project_root_from_report(current: dict[str, Any]) -> Path:
    current_report = Path(str(current.get("__current_report_path", "")))
    if current_report.name:
        # expected: <project>/out/<report>.json
        return current_report.parent.parent
    memory_json = str(current.get("memory_json", ""))
    if memory_json:
        return Path(memory_json).parent.parent
    return Path.cwd()


def _shorten(text: str, limit: int = 80) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def infer_source_action_candidates(current: dict[str, Any]) -> list[dict[str, str]]:
    """Find source/config files that should be checked for the failed item.

    This keeps the interview grounded in concrete code/config evidence instead
    of asking generic maintenance questions.
    """
    root = _project_root_from_report(current)
    focus = current.get("focus") if isinstance(current.get("focus"), dict) else {}
    test_ids = [str(x) for x in _safe_list(focus.get("test_ids"))]
    focus_file = str(focus.get("file", ""))
    tokens = {t.lower() for t in test_ids}
    for part in Path(focus_file).stem.replace("-", " ").replace("_", " ").split():
        if len(part) >= 3:
            tokens.add(part.lower())

    candidates: list[dict[str, str]] = []
    priority_files = [
        root / "data" / "fault_exclusion_master_map.csv",
        root / "tools" / "generate_maintenance_report.py",
        root / "tools" / "ouroboros_review_loop.py",
        root / "tools" / "run_maintenance_with_review.py",
    ]
    for path in priority_files:
        if path.exists():
            candidates.append({
                "file": str(path),
                "reason": "고장배제 매핑/진단 질문/보고서 생성 로직 확인 대상",
                "action": "해당 불량 항목의 고장배제 목록과 판정 조건이 맞는지 확인",
            })

    searchable_ext = {".py", ".cpp", ".h", ".hpp", ".c", ".csv", ".md"}
    for path in root.rglob("*"):
        if len(candidates) >= 8:
            break
        if not path.is_file() or path.suffix.lower() not in searchable_ext:
            continue
        if any(str(path) == c["file"] for c in candidates):
            continue
        try:
            txt = path.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            continue
        if any(tok and tok in txt for tok in tokens):
            candidates.append({
                "file": str(path),
                "reason": f"focus/test token 매칭: {', '.join(sorted(tokens)[:4])}",
                "action": "불량 항목 처리 조건, 로그 파싱 키워드, 조치 문구 정합성 확인",
            })

    return candidates[:8]


def build_interview(current: dict[str, Any]) -> list[str]:
    focus = current.get("focus") if isinstance(current.get("focus"), dict) else {}
    fail_candidates = _safe_list(current.get("fail_candidates"))
    target = str(focus.get("file") or (fail_candidates[0].get("file") if fail_candidates and isinstance(fail_candidates[0], dict) else "불량 후보"))
    risk = str(focus.get("risk") or (fail_candidates[0].get("risk") if fail_candidates and isinstance(fail_candidates[0], dict) else "UNKNOWN"))
    cause = str(focus.get("cause") or (fail_candidates[0].get("cause") if fail_candidates and isinstance(fail_candidates[0], dict) else "unknown"))
    test_ids = ", ".join(str(x) for x in _safe_list(focus.get("test_ids"))) or "GLOBAL"
    exclusions = [str(x) for x in _safe_list(focus.get("recommended_exclusion_items"))]
    if not exclusions:
        exclusions = ["통신 경로", "전원 경로", "케이블/커넥터"]

    source_candidates = infer_source_action_candidates(current)
    src1 = Path(source_candidates[0]["file"]).name if source_candidates else "진단 소스"
    src2 = Path(source_candidates[1]["file"]).name if len(source_candidates) > 1 else src1

    # GUI에서 Yes/No 다이얼로그 4회로 받기 위해, 항상 4개의 폐쇄형 질문을 생성한다.
    # 질문 내용은 사용자가 요구한 대로 고장/불량 항목 + 고장배제 목록 + 소스코드 조치 확인 기준으로 구성한다.
    q1 = (
        f"불량/고장 의심 항목 '{_shorten(target)}'(시험ID {test_ids}, 위험도 {risk})에 대해 "
        f"고장배제 1순위 '{_shorten(exclusions[0])}'부터 실제 조치할까요? (Yes/No)"
    )
    q2 = (
        f"같은 항목의 고장배제 목록 '{_shorten(' / '.join(exclusions[:3]), 120)}' 순서로 "
        "현장 점검 체크리스트를 확정할까요? (Yes/No)"
    )
    q3 = (
        f"소스코드/설정 '{src1}'에서 해당 불량 항목의 판정·매핑 조건을 먼저 확인하고 "
        "필요 시 수정 조치로 등록할까요? (Yes/No)"
    )
    q4 = (
        f"원인분류 '{cause}'와 고장배제 결과가 맞지 않으면 '{src2}'의 로그 파싱/질문 생성 로직을 "
        "보강한 뒤 동일 조건 재시험을 진행할까요? (Yes/No)"
    )

    return [q1, q2, q3, q4]


def build_qa(current: dict[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    summary = current.get("summary", {}) if isinstance(current.get("summary"), dict) else {}

    checks.append({
        "check": "요약 수치 존재(total_logs/fail_candidates/high_risk_count)",
        "result": "pass" if all(k in summary for k in ["total_logs", "fail_candidates", "high_risk_count"]) else "warn",
    })
    checks.append({
        "check": "FAIL 후보 상세 존재",
        "result": "pass" if len(_safe_list(current.get("fail_candidates"))) > 0 else "warn",
    })
    checks.append({
        "check": "원인 Top 리스트 존재",
        "result": "pass" if len(_safe_list(current.get("top_causes"))) > 0 else "warn",
    })
    focus = current.get("focus")
    checks.append({
        "check": "focus 분석 포함 여부",
        "result": "pass" if isinstance(focus, dict) and len(focus) > 0 else "warn",
    })
    return checks


def build_evaluate(qa_checks: list[dict[str, str]]) -> dict[str, Any]:
    total = len(qa_checks)
    passed = sum(1 for c in qa_checks if c.get("result") == "pass")
    score = round((passed / total) * 100, 1) if total else 0.0
    if score >= 85:
        verdict = "ready"
    elif score >= 60:
        verdict = "needs_review"
    else:
        verdict = "insufficient"
    return {"score": score, "verdict": verdict}


def load_history_reports(history_dir: Path, current_path: Path) -> list[dict[str, Any]]:
    if not history_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(history_dir.glob("*.json")):
        if p.resolve() == current_path.resolve():
            continue
        try:
            data = _load_json(p)
            data["__path"] = str(p)
            out.append(data)
        except Exception:
            continue
    return out


def compare_history(current: dict[str, Any], history_reports: list[dict[str, Any]]) -> dict[str, Any]:
    current_summary = current.get("summary", {}) if isinstance(current.get("summary"), dict) else {}
    current_high = int(current_summary.get("high_risk_count", 0) or 0)

    hist_high = []
    cause_counter: Counter[str] = Counter()
    for h in history_reports:
        s = h.get("summary", {}) if isinstance(h.get("summary"), dict) else {}
        hist_high.append(int(s.get("high_risk_count", 0) or 0))
        for c in _safe_list(h.get("top_causes")):
            if isinstance(c, dict):
                name = str(c.get("cause", "") or "").strip()
                if name:
                    cause_counter[name] += int(c.get("count", 1) or 1)

    avg_high = round(sum(hist_high) / len(hist_high), 2) if hist_high else 0.0
    trend = "up" if current_high > avg_high else "down_or_flat"
    return {
        "history_count": len(history_reports),
        "avg_high_risk_count": avg_high,
        "current_high_risk_count": current_high,
        "high_risk_trend": trend,
        "frequent_historical_causes_top5": [
            {"cause": k, "count": v} for k, v in cause_counter.most_common(5)
        ],
        "history_paths": [h.get("__path", "") for h in history_reports[:20]],
    }


def _risk_to_float(v: Any) -> float:
    s = str(v or "").strip().upper()
    if s == "HIGH":
        return 1.0
    if s == "MEDIUM":
        return 0.6
    if s == "LOW":
        return 0.3
    try:
        return float(s)
    except Exception:
        return 0.0


def prioritize_feedback(current: dict[str, Any], compare: dict[str, Any]) -> list[dict[str, Any]]:
    feedback: list[dict[str, Any]] = []
    fail_candidates = _safe_list(current.get("fail_candidates"))

    if compare.get("history_count", 0) == 0:
        feedback.append({"type": "evidence", "priority": 1, "message": "비교 가능한 과거 JSON 보고서가 부족합니다. 최소 3건 이상 누적 권장."})

    if len(fail_candidates) == 0:
        feedback.append({"type": "coverage", "priority": 1, "message": "FAIL 후보가 비어 있습니다. watch/anomaly 임계값과 파싱 규칙을 재검증하세요."})
    else:
        sorted_candidates = sorted(
            fail_candidates,
            key=lambda x: _risk_to_float(x.get("risk", 0.0)),
            reverse=True,
        )
        top3 = [
            {
                "file": str(c.get("file", "")),
                "risk": _risk_to_float(c.get("risk", 0.0)),
                "cause": str(c.get("cause", "")),
            }
            for c in sorted_candidates[:3]
        ]
        feedback.append({"type": "priority_reorder", "priority": 1, "top3_check_order": top3})

    if compare.get("high_risk_trend") == "up":
        feedback.append({"type": "risk_trend", "priority": 2, "message": "고위험 건수가 과거 평균 대비 증가했습니다. 전원/통신 라인 우선점검을 권장합니다."})

    if not _safe_list(current.get("top_causes")):
        feedback.append({"type": "root_cause", "priority": 2, "message": "원인 통계가 부족합니다. 원인분석 파이프라인(XGBoost/룰) 입력 품질을 재점검하세요."})

    return sorted(feedback, key=lambda x: int(x.get("priority", 99)))


def run(current_report_json: Path, history_dir: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    current = _load_json(current_report_json)
    current["__current_report_path"] = str(current_report_json)
    interview = build_interview(current)
    source_action_candidates = infer_source_action_candidates(current)
    qa = build_qa(current)
    evaluate = build_evaluate(qa)

    history_reports = load_history_reports(history_dir, current_report_json)
    compare = compare_history(current, history_reports)
    feedback = prioritize_feedback(current, compare)

    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "current_report": str(current_report_json),
        "step7": {
            "interview_questions": interview,
            "source_action_candidates": source_action_candidates,
            "qa_checks": qa,
            "evaluate": evaluate,
        },
        "step8": compare,
        "step9": {
            "feedback": feedback,
        },
        "next_steps": [
            "step10_user_confirmation",
            "step11_persist_memory_and_maintenance_history",
            "step12_use_in_next_diagnosis",
        ],
    }

    out_json = out_dir / "ouroboros_review_result.json"
    out_md = out_dir / "ouroboros_review_result.md"
    out_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Ouroboros Review Result (Step7~9)",
        "",
        f"- current_report: {current_report_json}",
        f"- generated_at: {output['generated_at']}",
        "",
        "## Step7 Interview",
    ]
    for i, q in enumerate(interview, 1):
        md_lines.append(f"{i}. {q}")
    md_lines += ["", "### Source/Config Action Candidates"]
    for item in source_action_candidates:
        md_lines.append(f"- {item.get('file', '')}: {item.get('action', '')} ({item.get('reason', '')})")
    md_lines += ["", "## Step7 QA"]
    for c in qa:
        md_lines.append(f"- [{c['result']}] {c['check']}")
    md_lines += ["", "## Step7 Evaluate", f"- score: {evaluate['score']}", f"- verdict: {evaluate['verdict']}"]
    md_lines += ["", "## Step8 Compare", f"- history_count: {compare['history_count']}", f"- avg_high_risk_count: {compare['avg_high_risk_count']}", f"- current_high_risk_count: {compare['current_high_risk_count']}", f"- high_risk_trend: {compare['high_risk_trend']}"]
    md_lines += ["", "## Step9 Feedback"]
    for item in feedback:
        md_lines.append(f"- (P{item.get('priority', '?')}) {json.dumps(item, ensure_ascii=False)}")

    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return {"json": str(out_json), "md": str(out_md)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JAN Step7~9 Ouroboros 검토 루프")
    parser.add_argument("--current-report-json", required=True, help="6단계에서 생성된 보고서 JSON 경로")
    parser.add_argument("--history-dir", default="C:/Users/yjs/Desktop/JAN/Policy/Data", help="과거 보고서 JSON 디렉터리")
    parser.add_argument("--out-dir", default="C:/Users/yjs/Desktop/JAN/OrobrosTest/out/ouroboros_review", help="출력 디렉터리")
    args = parser.parse_args(argv)

    result = run(Path(args.current_report_json), Path(args.history_dir), Path(args.out_dir))
    print(f"ouroboros_review_result.json: {result['json']}")
    print(f"ouroboros_review_result.md: {result['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
