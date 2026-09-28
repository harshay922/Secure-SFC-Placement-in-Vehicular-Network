@echo off
REM Phase 2: run all tests, then the migration-security experiments and graphs.
cd /d "%~dp0"
echo === Installing libraries ===
python -m pip install -r requirements.txt
echo.
echo === All tests (baseline + Phase 1 + Phase 2) ===
python -m pytest -v
echo.
echo === Phase 2 experiments (about 3 minutes) ===
python phase2_experiments.py
echo.
echo Done. Graphs and CSVs are in results\phase2
pause
