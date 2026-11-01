# =====================================================================
# run_all.py  -  ONE command to get all results
# ---------------------------------------------------------------------
# Run:  python run_all.py
# It does, in order:
#   0) makes the SUMO car trace once, if data/mobility_trace_seed42.csv.gz is missing
#   1) Step 10 - all experiments (QUICK_MODE in config.py decides quick or full)
#   2) Step 11 - all graphs and summary tables
# Results: results/step10_all_runs.csv (or step10_quick_runs.csv) and results/final/ (or results/quick/)
# =====================================================================

import os, subprocess, sys, time
import config as cfg

HERE = os.path.dirname(os.path.abspath(__file__))          # the 'code' folder


def run(script):
    """Run one step script with the same Python and stop everything if it fails."""
    print("\n" + "=" * 60 + f"\nRUNNING {script}\n" + "=" * 60, flush=True)
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(HERE, script)], cwd=HERE)
    if r.returncode != 0:                                  # error -> stop here
        sys.exit(f"\n{script} FAILED (see the error above). Stopped.")
    print(f"{script} finished in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    start = time.time()
    print(f"Mode: {'QUICK (seeds 1-2)' if cfg.QUICK_MODE else 'FULL (5 seeds)'}   "
          f"FRESH_START = {cfg.FRESH_START}")
    if not os.path.isfile(cfg.TRACE_FILE):                 # car trace missing -> record it once (needs SUMO)
        run("step2b_record_trace.py")
    run("step10_experiments.py")                           # all experiments
    run("step11_graphs.py")                                # all graphs + tables
    out = "quick" if cfg.QUICK_MODE else "final"
    print(f"\nALL DONE in {(time.time() - start) / 60:.1f} min.  Graphs and tables: results/{out}/")
