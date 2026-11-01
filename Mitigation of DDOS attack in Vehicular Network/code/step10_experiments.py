# =====================================================================
# step10_experiments.py  -  STEP 10: run every scenario x scheme x attacker share x seed
# ---------------------------------------------------------------------
# Run:  python step10_experiments.py
# FULL  (QUICK_MODE = False): 3 scenarios x 4 schemes x shares 5,10,20,30 % x 5 seeds = 240 runs
#                             + the no-attack reference (share 0, 4 schemes x 5 seeds)  =  20 runs
# QUICK (QUICK_MODE = True) : 3 scenarios x 4 schemes x shares 10,30 % x seeds 1-2     =  48 runs
#                             + no-attack reference (4 schemes x 2 seeds)               =   8 runs
# The no-attack runs do not depend on the scenario, so they are run once (scenario = "none").
# Scenario D_jam has fixed standing attackers (no attacker-share sweep): 4 schemes x seeds extra runs.
# Uses all CPU cores but one.
# FRESH_START = True (config.py): the old csv is deleted at start, every run is done again.
# FRESH_START = False: runs already in the csv are skipped (resume after a stop).
# Outputs (in results/):
#   step10_all_runs.csv  (or step10_quick_runs.csv)                      - one row per run
#   step10_timeline_<scenario>_<scheme>_10pct.csv                         - seed 1, 10%: latency every second
# =====================================================================

import csv, os
from multiprocessing import Pool, cpu_count
import config as cfg

SCHEMES = ["S0_no_defense", "S1_detect_only", "S2_detect_scaleout", "S3_proposed"]   # final schemes
SHARES = cfg.ATTACKER_SHARE_SWEEP                                                      # attack strengths
SEEDS = cfg.SEEDS
OUT = os.path.join(cfg.RESULTS_DIR, "step10_all_runs.csv")
if cfg.QUICK_MODE:                                       # quick test: fewer runs, separate file
    SHARES, SEEDS = [0.10, 0.30], cfg.SEEDS[:2]
    OUT = os.path.join(cfg.RESULTS_DIR, "step10_quick_runs.csv")


def one_run(job):
    """Runs ONE simulation in a separate process and returns its summary."""
    scenario, scheme, share, seed = job
    from simulator import Simulation                     # imported inside the worker process
    sim = Simulation(scheme, seed, attacker_share=share,
                     scenario=cfg.ATTACK_SCENARIOS[0] if scenario == "none" else scenario)
    res = sim.run()
    res["scenario"] = scenario                           # "none" for the no-attack reference
    if seed == cfg.SEEDS[0] and (abs(share - cfg.ATTACKER_SHARE) < 1e-9 or scenario == "D_jam"):   # one timeline each
        p = os.path.join(cfg.RESULTS_DIR, f"step10_timeline_{scenario}_{scheme}_10pct.csv")
        with open(p, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["time_s", "avg_latency_running_ms", "disrupted_sfcs", "flagged_rsus"])
            flags = dict(sim.det.flag_timeline) if sim.det else {}
            for t, l, d in sim.lat_timeline:
                w.writerow([t, round(l, 3), d, flags.get(t, 0)])
    return res


if __name__ == "__main__":
    os.makedirs(cfg.RESULTS_DIR, exist_ok=True)
    if cfg.FRESH_START and os.path.isfile(OUT):          # start from zero: remove the old results file
        os.remove(OUT)
        print(f"deleted old {os.path.basename(OUT)} (FRESH_START = True)")
    done = set()                                         # (scenario, scheme, share, seed) already in the csv
    if os.path.isfile(OUT):
        with open(OUT, newline="") as f:
            for r in csv.DictReader(f):
                done.add((r["scenario"], r["scheme"], round(float(r["attacker_share"]), 2), int(r["seed"])))
    jobs = [("none", sch, 0.0, sd) for sd in SEEDS for sch in SCHEMES]                  # no-attack reference
    jobs += [(sc, sch, sh, sd) for sd in SEEDS for sc in cfg.ATTACK_SCENARIOS if sc != "D_jam"
             for sh in SHARES for sch in SCHEMES]
    if "D_jam" in cfg.ATTACK_SCENARIOS:                  # D: fixed standing attackers, no moving attackers (share 0)
        jobs += [("D_jam", sch, 0.0, sd) for sd in SEEDS for sch in SCHEMES]
    jobs = [j for j in jobs if (j[0], j[1], round(j[2], 2), j[3]) not in done]
    print(f"{len(done)} runs already done, {len(jobs)} to go")
    old_header = None                                    # column names already in the csv (keep the same order!)
    if os.path.isfile(OUT):
        with open(OUT, newline="") as f:
            old_header = next(csv.reader(f), None)
    with Pool(max(1, cpu_count() - 1)) as pool, open(OUT, "a", newline="") as f:
        w = None
        for k, res in enumerate(pool.imap_unordered(one_run, jobs), 1):   # results arrive as runs finish
            if w is None:                                # every scheme returns the same columns (empty if not used)
                w = csv.DictWriter(f, fieldnames=old_header or list(res.keys()), extrasaction="ignore")
                if old_header is None:
                    w.writeheader()
            w.writerow(res); f.flush()                   # save immediately (safe to stop any time)
            print(f"[{k}/{len(jobs)}] {res['scenario']:10s} {res['scheme']:20s} share {res['attacker_share']:.2f} "
                  f"seed {res['seed']}  attack-window latency {res['window_running_latency_ms']:.1f} ms", flush=True)
    print(f"\nsaved {OUT}\nRESULT: Step 10 OK")
