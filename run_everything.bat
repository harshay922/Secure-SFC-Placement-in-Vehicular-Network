@echo off
REM ONE CLICK FOR EVERYTHING: install, test once, then baseline + Phase 1 + Phase 2.
REM Stops if any test fails, so you never get graphs from broken code.
REM Seeds are fixed, so the numbers are the same every time (reproducible).
REM Takes about 4-5 minutes. The separate run_all / run_phase1 / run_phase2 files still work on their own.
cd /d "%~dp0"
echo === [1/5] Installing libraries ===
python -m pip install -r requirements.txt
echo.
echo === [2/5] All tests (baseline + Phase 1 + Phase 2) ===
python -m pytest -v
if errorlevel 1 goto failed
echo.
echo === [3/5] BASELINE: deleting old baseline results ===
if not exist results mkdir results
del /q results\stage*.csv 2>nul
del /q results\sweep_*.csv 2>nul
del /q results\sweep_*.png 2>nul
if exist results\figures rmdir /s /q results\figures
echo.
echo --- Stage A (5 RSUs) ---
python run.py --stage A
echo --- Stage B (10 RSUs) ---
python run.py --stage B
echo --- Stage C (20 RSUs) ---
python run.py --stage C
echo --- Paper-style sweeps (about 15 s) ---
python experiments.py
echo --- Network figures and request table (about 10 s) ---
python baseline_figures.py
echo.
echo === [4/5] PHASE 1: security experiments (about 30 s) ===
python phase1_experiments.py
echo.
echo === [5/5] PHASE 2: migration-security experiments (about 3 min) ===
python phase2_experiments.py
echo.
echo ============================================================
echo Done. Results:
echo   results\           baseline (stages, sweeps)
echo   results\figures\   network maps and request table
echo   results\phase1\    Phase 1 graphs and CSVs
echo   results\phase2\    Phase 2 graphs and CSVs
echo ============================================================
pause
exit /b 0

:failed
echo.
echo ************************************************************
echo  A TEST FAILED. No experiments were run.
echo  Scroll up to see which test failed, fix it, then run again.
echo ************************************************************
pause
exit /b 1
