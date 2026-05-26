# ML Inspection Pipeline Implementation Plan

> For Hermes: Use subagent-driven-development skill to implement this plan task-by-task.

Goal: Add a Python-based inspection pipeline beside the existing MFC OrobrosTest app that ingests test logs from CSV/TXT/SQLite DB, generates numeric features, scores anomalies with Isolation Forest, and produces a Hermes-friendly inspection report.

Architecture: Keep the existing C++/MFC pipe prototype intact. Add a separate Python module/CLI under `tools/inspection_pipeline.py` so the ML workflow is testable without GUI automation. The MFC app can later call this CLI or feed its report into Hermes/Ouroboros.

Tech Stack: Python 3 stdlib + optional scikit-learn. If scikit-learn is unavailable, the CLI must fall back to a deterministic robust z-score scorer so QA can still run offline.

---

## Data Contract

Input columns are flexible. The parser should normalize Korean/English aliases:

- voltage: `voltage`, `전압`, `volt`, `v`
- current: `current`, `전류`, `amp`, `a`
- response_time_ms: `response_time_ms`, `response_ms`, `응답시간`, `응답시간_ms`, `latency_ms`
- fail_count: `fail_count`, `failure_count`, `실패횟수`, `failures`
- crc_error_rate: `crc_error_rate`, `crc_errors`, `CRC 오류율`, `crc_error_pct`
- retry_count: `retry_count`, `retries`, `통신 재시도 횟수`, `재시도횟수`
- maintenance_case: optional previous maintenance text/case id

TXT parsing should extract `key=value` or `key: value` tokens per line.
SQLite DB parsing should accept a table name argument, defaulting to `test_logs`.

Output files:
- `inspection_results.csv`: row-level features + anomaly score + normal/anomaly label
- `inspection_report.md`: Korean report with why anomalous, similar maintenance cases, and recommended inspection order

## Task 1: Create test fixtures and failing tests

Files:
- Create: `tests/fixtures/sample_test_log.csv`
- Create: `tests/fixtures/sample_test_log.txt`
- Create: `tests/test_inspection_pipeline.py`

Tests must verify:
1. CSV and TXT logs are loaded.
2. Features include voltage/current/response_time_ms/fail_count/crc_error_rate/retry_count.
3. A clearly bad row is labeled anomaly.
4. Report contains Korean sections: `이상 판단 근거`, `유사 정비 사례`, `추천 점검 순서`.
5. CLI writes `inspection_results.csv` and `inspection_report.md`.

Run:
`python -m pytest tests/test_inspection_pipeline.py -q`
Expected RED first: fail because `tools.inspection_pipeline` does not exist.

## Task 2: Implement inspection pipeline module

Files:
- Create: `tools/__init__.py`
- Create: `tools/inspection_pipeline.py`

Functions:
- `load_records(path: Path, table: str = "test_logs") -> list[dict]`
- `extract_features(records: list[dict]) -> list[dict]`
- `score_anomalies(features: list[dict]) -> list[dict]`
- `generate_report(scored_rows: list[dict]) -> str`
- `run_pipeline(input_path, output_dir, table="test_logs") -> dict`
- CLI: `python tools/inspection_pipeline.py --input <file> --output-dir <dir> [--table test_logs]`

Scoring:
- Prefer `sklearn.ensemble.IsolationForest(contamination="auto", random_state=42)` when available and enough rows exist.
- Fallback: robust z-score based anomaly score using medians and MAD; mark row anomaly if score >= 3.5 or fail_count/crc/retry extreme.

Report logic:
- Explain dominant high-risk features in Korean.
- Similar maintenance cases: find rows with `maintenance_case` text and overlapping high-risk feature names.
- Recommended order: prioritize safety/electrical first, then communication integrity, then response-time/load, then retries/history.

## Task 3: Add developer/QA convenience scripts and docs

Files:
- Create: `run_inspection_pipeline.bat`
- Modify: `README.md`

Script should run sample CSV through the pipeline and print report path.
README should explain:
- Current MFC pipe prototype status remains unchanged.
- New ML pipeline usage.
- Where generated outputs are stored.

## Verification

Commands:
1. `python -m pytest tests/test_inspection_pipeline.py -q`
2. `python tools/inspection_pipeline.py --input tests/fixtures/sample_test_log.csv --output-dir out/inspection_smoke`
3. `python tools/inspection_pipeline.py --input tests/fixtures/sample_test_log.txt --output-dir out/inspection_txt_smoke`
4. `cmd //c "C:\Users\kangd\Desktop\OrobrosTest\run_pipe_selftest.bat"`
5. `cmd //c "C:\Users\kangd\Desktop\OrobrosTest\build_debug.bat"`

Acceptance criteria:
- Python tests pass.
- Sample CSV/TXT smoke outputs exist.
- C++ pipe self-test still passes.
- MFC app still builds.
- Final report distinguishes Python ML pipeline verification from manual GUI/Hermes integration that remains future work.
