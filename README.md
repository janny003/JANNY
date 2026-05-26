# OrobrosTest

MFC dialog sample that launches Ouroboros interview as a child process and connects pipes:

1. C++/MFC starts `ouroboros init start ...` with redirected stdout/stderr/stdin.
2. Ouroboros questions are read from stdout pipe on a background thread.
3. The MFC dialog appends output to the transcript box and pops up likely questions.
4. The question popup uses a Yes/No dialog.
5. Yes sends `예`; No sends `아니요` to the child process stdin pipe.
6. Manual text answers can still be typed and sent with the Send button.
7. The next question/result is received in the transcript.

## Files

- `OrobrosTest.sln` / `OrobrosTest.vcxproj` - Visual Studio 2022 MFC project.
- `OrobrosTestDlg.cpp` / `.h` - pipe process implementation and UI handlers.
- `mock_ouroboros.py` - deterministic mock interview process for local testing.
- `PipeSelfTest.cpp` - console self-test for the same stdin/stdout pipe pattern.
- `build_debug.bat` - builds Debug x64 MFC executable.
- `run_pipe_selftest.bat` - builds/runs pipe self-test.
- `tools/inspection_pipeline.py` - Python CSV/TXT/SQLite 시험 로그 ML 점검 파이프라인.
- `run_inspection_pipeline.bat` - sample CSV를 점검 파이프라인으로 실행하는 QA 편의 스크립트.

## Sub-agent policy applied

Applied policy set (source: `C:\Users\yjs\Desktop\JAN\Policy`):
- `policies/subagent_planner_jenni.md`
- `policies/subagent_developer_jangli.md`
- `policies/subagent_qa_lucy.md`
- `policies/subagent_designer_hiyuki.md`

## Build

```bat
C:\Users\kangd\Desktop\OrobrosTest\build_debug.bat
```

Output:

```text
C:\Users\kangd\Desktop\OrobrosTest\x64\Debug\OrobrosTest.exe
```

## Run

Open:

```text
C:\Users\kangd\Desktop\OrobrosTest\x64\Debug\OrobrosTest.exe
```

Default command in the UI:

```text
C:\Users\kangd\.local\bin\ouroboros.exe init start --llm-backend codex
```

The context textbox is appended as the final command-line argument.

For a deterministic UI smoke test, replace the command field with:

```text
python C:\Users\kangd\Desktop\OrobrosTest\mock_ouroboros.py
```

Then click Start and send answers. You should see three questions and echoed `received:` lines.

## Verified

- MFC Debug x64 build: PASS
- Pipe roundtrip self-test with mock interview: PASS
- Real `ouroboros.exe init start --llm-backend codex` under redirected stdin/stdout: FAIL for interactive use
- Python ML inspection pipeline pytest/smoke: PASS

Self-test command:

```bat
C:\Users\kangd\Desktop\OrobrosTest\run_pipe_selftest.bat
```

## ML inspection pipeline

The existing Windows/MFC pipe prototype remains unchanged. A separate Python pipeline was added so QA can inspect equipment test logs without GUI automation and without changing the current MFC pipe behavior.

Supported inputs:

- CSV (`.csv`)
- TXT (`.txt`) with `key=value` or `key: value` tokens per line
- SQLite DB (`.db`, `.sqlite`, `.sqlite3`), default table `test_logs`

Normalized feature columns:

- `voltage` / `전압` / `volt` / `v`
- `current` / `전류` / `amp` / `a`
- `response_time_ms` / `response_ms` / `응답시간` / `응답시간_ms` / `latency_ms`
- `fail_count` / `failure_count` / `실패횟수` / `failures`
- `crc_error_rate` / `crc_errors` / `CRC 오류율` / `crc_error_pct`
- `retry_count` / `retries` / `통신 재시도 횟수` / `재시도횟수`
- optional `maintenance_case` for previous repair/maintenance notes

The scorer prefers `sklearn.ensemble.IsolationForest` when scikit-learn is installed. If scikit-learn is unavailable, it automatically uses a deterministic robust z-score fallback with rule checks for extreme fail/CRC/retry values.

Run the sample pipeline:

```bat
C:\Users\kangd\Desktop\OrobrosTest\run_inspection_pipeline.bat
```

Run directly:

```bat
python C:\Users\kangd\Desktop\OrobrosTest\tools\inspection_pipeline.py --input C:\Users\kangd\Desktop\OrobrosTest\tests\fixtures\sample_test_log.csv --output-dir C:\Users\kangd\Desktop\OrobrosTest\out\inspection_sample
```

Generated outputs:

- `inspection_results.csv` - row-level numeric features, anomaly score, normal/anomaly label, high-risk features
- `inspection_report.md` - Hermes Agent가 읽기 쉬운 한국어 리포트: `이상 판단 근거`, `유사 정비 사례`, `추천 점검 순서`

Default sample output directory:

```text
C:\Users\kangd\Desktop\OrobrosTest\out\inspection_sample
```

Python verification command:

```bat
python -m pytest tests/test_inspection_pipeline.py -q
```

## QA note

The mock process is line-oriented and works through anonymous pipes. The current real Ouroboros Codex interview path is console-interactive: when launched with redirected stdin/stdout and no Windows console, it can generate the first question, then fails at the answer prompt with:

```text
Interview failed: No Windows console found. Are you running cmd.exe?
```

In the GUI this means Start may briefly enable Send, then the child process exits and Send is disabled again. This is expected for the current real backend, not proof that the MFC Send button handler is broken. Use `mock_ouroboros.py` for deterministic pipe/UI testing unless Ouroboros provides a pipe-friendly/non-TTY mode.
