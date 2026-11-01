# =====================================================================
# step4_baseline.py  -  STEP 4: greedy placement, NO attack (clean baseline)
# ---------------------------------------------------------------------
# Run:  python step4_baseline.py            (about 2 minutes, seed 1)
# Outputs (in results/):
#   step4_summary_seed1.csv        - the main numbers
#   step4_sfc_log_seed1.csv        - every SFC: where each VNF went, latency
#   step4_rsu_util_over_time.png   - CPU utilisation: average RSU, busiest RSU (RSU3)
#   step4_rsu_util_per_rsu.png     - average CPU utilisation of each RSU
# =====================================================================

import csv                                      # write csv
import os                                       # paths
import numpy as np                              # averages
import matplotlib                               # plotting
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as cfg                            # settings
from simulator import Simulation                # the engine

SEED = cfg.SEEDS[0]                             # seed 1
sim = Simulation("S0_no_defense", SEED, attacker_share=0.0)   # greedy, no attackers
res = sim.run()                                 # run 1 hour

print("=" * 60)
print("STEP 4 - greedy placement, no attack (seed %d)" % SEED)
print("=" * 60)
for k, v in res.items():                        # print every result line
    print(f"{k:24s}: {v:.2f}" if isinstance(v, float) else f"{k:24s}: {v}")

p = os.path.join(cfg.RESULTS_DIR, f"step4_summary_seed{SEED}.csv")
with open(p, "w", newline="") as f:
    w = csv.writer(f); w.writerow(res.keys()); w.writerow(res.values())
print(f"saved {p}")

p = os.path.join(cfg.RESULTS_DIR, f"step4_sfc_log_seed{SEED}.csv")
with open(p, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["req_id", "arrival_s", "entry", "safety", "n_vnfs", "nodes", "accepted", "latency_ms", "vnfs_on_cloud"])
    for r in sim.log:
        q, n = r["req"], r["nodes"]
        w.writerow([q["req_id"], q["arrival_s"], q["entry"], int(q["safety"]), len(q["chain"]),
                    ">".join(n) if n else "", int(n is not None),
                    round(r["latency_ms"], 3) if n else "", n.count(cfg.CLOUD_ID) if n else ""])
print(f"saved {p}")

rsus = list(sim.net.rsus)                                   # RSU order used in util_timeline
util = np.array([row[1:] for row in sim.util_timeline]) * 100   # seconds x RSUs, in %
times = [row[0] for row in sim.util_timeline]
busiest = rsus[int(util.mean(axis=0).argmax())]             # RSU with the highest average utilisation

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(times, util.mean(axis=1), label="average over all 25 RSUs")
ax.plot(times, util[:, rsus.index(busiest)], label=f"busiest RSU ({busiest})")
ax.set_xlabel("simulation time (s)"); ax.set_ylabel("CPU utilisation (%)")
ax.set_title("RSU CPU utilisation, greedy placement, no attack"); ax.legend()
p = os.path.join(cfg.RESULTS_DIR, "step4_rsu_util_over_time.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")

ids = sorted(rsus, key=lambda r: int(r.replace("RSU", "")))
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(range(len(ids)), [util[:, rsus.index(r)].mean() for r in ids], marker="o")
ax.set_xticks(range(len(ids))); ax.set_xticklabels([r.replace("RSU", "") for r in ids])
ax.set_xlabel("RSU number"); ax.set_ylabel("average CPU utilisation (%)")
ax.set_title("Average CPU utilisation of each RSU, no attack")
p = os.path.join(cfg.RESULTS_DIR, "step4_rsu_util_per_rsu.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig); print(f"saved {p}")
print("\nRESULT: Step 4 OK")
