@echo off
REM Phase 1: run all tests, then the security experiments and graphs.
cd /d "%~dp0"
echo === Installing libraries ===
python -m pip install -r requirements.txt
echo.
echo === All tests (baseline + Phase 1) ===
python -m pytest -v
echo.
echo === Phase 1 security experiments (about 30 s) ===
python phase1_experiments.py
echo.
echo Done. Graphs and CSVs are in results\phase1
pause
