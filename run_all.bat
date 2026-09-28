@echo off
REM One-click: install libraries, run all tests, run Stage A/B/C, run sweeps.
cd /d "%~dp0"
echo === Installing libraries ===
python -m pip install -r requirements.txt
echo.
echo === All tests (baseline + Phase 1) ===
python -m pytest -v
echo.
echo === Stage A (5 RSUs) ===
python run.py --stage A
echo.
echo === Stage B (10 RSUs) ===
python run.py --stage B
echo.
echo === Stage C (20 RSUs) ===
python run.py --stage C
echo.
echo === Paper-style sweeps (about 15 s) ===
python experiments.py
echo.
echo Done. Plots and CSVs are in the results folder.
pause
