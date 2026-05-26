@echo off
setlocal
set "ROOT=C:\Users\kangd\Desktop\OrobrosTest"
set "OUT=%ROOT%\out\inspection_sample"

python "%ROOT%\tools\inspection_pipeline.py" --input "%ROOT%\tests\fixtures\sample_test_log.csv" --output-dir "%OUT%"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Inspection report: %OUT%\inspection_report.md
endlocal
