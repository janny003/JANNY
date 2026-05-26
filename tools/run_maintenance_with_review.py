from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> int:
    print("[RUN] " + " ".join(cmd), flush=True)
    p = subprocess.run(cmd)
    return p.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="정비 보고서 생성 + Ouroboros Step7~9 검토 연동 실행기")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--log-root", required=True)
    parser.add_argument("--out-doc", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--focus-log", default="")
    parser.add_argument("--operator-feedback", default="")
    parser.add_argument("--review-history-dir", default="")
    parser.add_argument("--review-out-dir", default="")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root)
    gen_script = project_root / "tools" / "generate_maintenance_report.py"
    review_script = project_root / "tools" / "ouroboros_review_loop.py"

    out_doc = Path(args.out_doc)
    out_json = Path(args.out_json) if args.out_json else out_doc.with_suffix(".json")
    review_history_dir = Path(args.review_history_dir) if args.review_history_dir else out_doc.parent
    review_out_dir = Path(args.review_out_dir) if args.review_out_dir else (project_root / "out" / "ouroboros_review")

    cmd_gen = [
        args.python,
        str(gen_script),
        "--project-root", str(project_root),
        "--log-root", str(Path(args.log_root)),
        "--out-doc", str(out_doc),
        "--out-json", str(out_json),
    ]
    if args.focus_log:
        cmd_gen += ["--focus-log", str(Path(args.focus_log))]
    if args.operator_feedback:
        cmd_gen += ["--operator-feedback", args.operator_feedback]

    rc = _run(cmd_gen)
    if rc != 0:
        return rc

    cmd_review = [
        args.python,
        str(review_script),
        "--current-report-json", str(out_json),
        "--history-dir", str(review_history_dir),
        "--out-dir", str(review_out_dir),
    ]
    rc = _run(cmd_review)
    if rc != 0:
        return rc

    review_json = review_out_dir / "ouroboros_review_result.json"
    if review_json.exists():
        try:
            review_data = json.loads(review_json.read_text(encoding="utf-8"))
            step7 = review_data.get("step7", {})
            evaluate = step7.get("evaluate", {})
            qa_checks = step7.get("qa_checks", [])
            interview_questions = step7.get("interview_questions", [])
            print(
                f"[REVIEW] score={evaluate.get('score', 'n/a')} verdict={evaluate.get('verdict', 'n/a')} qa_checks={len(qa_checks)}",
                flush=True,
            )
            for i, q in enumerate(interview_questions, 1):
                print(f"[INTERVIEW_Q{i}] {q}", flush=True)
        except Exception as ex:
            print(f"[REVIEW] summary parse skipped: {ex}", flush=True)

    print(f"[DONE] report_doc={out_doc}")
    print(f"[DONE] report_json={out_json}")
    print(f"[DONE] review_dir={review_out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
