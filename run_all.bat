@echo off
REM One-click baseline run: install libraries, run all tests, delete the old baseline results,
REM then make them again (Stage A/B/C, paper-style sweeps, network figures and request table).
REM Seeds are fixed (42 for stages, 1-5 for sweeps), so a fresh run gives the SAME numbers.
REM Phase 1 and Phase 2 results (results\phase1, results\phase2) are NOT touched here.
cd /d "%~dp0"
echo === Installing libraries ===
python -m pip install -r requirements.txt
echo.
echo === All tests (baseline + Phase 1 + Phase 2) ===
python -m pytest -v
echo.
echo === Deleting old baseline results ===
if not exist results mkdir results
del /q results\stage*.csv 2>nul
del /q results\sweep_*.csv 2>nul
del /q results\sweep_*.png 2>nul
if exist results\figures rmdir /s /q results\figures
echo Old baseline results deleted.
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
echo === Network figures and request table (about 10 s) ===
python baseline_figures.py
echo.
echo Done. New plots and CSVs are in the results folder.
pause
