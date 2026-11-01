# =====================================================================
# step3_requests.py  -  STEP 3: create normal SFC requests from live SUMO
# ---------------------------------------------------------------------
# Run:  python step3_requests.py        (about 1-2 minutes)
# No placement and no attack yet. Only checks that the requests look right.
# Outputs (in results/):
#   step3_requests_seed1.csv      - every request (open in Excel)
#   step3_demand_over_time.png    - total CPU that all alive SFCs ask for, every second
#   step3_requests_per_rsu.png    - how many requests entered through each RSU
# =====================================================================

import csv                                      # write csv
import os                                       # paths
from collections import Counter                 # counts things, e.g. requests per RSU
import numpy as np                              # averages
import matplotlib                               # plotting
matplotlib.use("Agg")                           # save to file
import matplotlib.pyplot as plt
import config as cfg                            # settings
from network import load_network                # Step 1
from mobility import Mobility                   # Step 2
from requests_gen import load_alibaba_vnfs, RequestGenerator   # this step's library

SEED = cfg.SEEDS[0]                             # use the first seed (1) for this check

os.makedirs(cfg.RESULTS_DIR, exist_ok=True)
net = load_network()                            # network
vnf_cpu, vnf_mem = load_alibaba_vnfs()          # real Alibaba demands
print(f"Alibaba containers loaded: {len(vnf_cpu)}  (CPU {vnf_cpu.min():g}-{vnf_cpu.max():g} cores, "
      f"memory {vnf_mem.min():g}-{vnf_mem.max():g})")
gen = RequestGenerator(SEED, vnf_cpu, vnf_mem, net)   # request maker with seed 1
mob = Mobility(net)
mob.start()                                     # launch SUMO

all_reqs = []                                   # every request made
alive = []                                      # requests whose holding time is not over
demand = []                                     # (t, total CPU asked by alive SFCs) per second
while mob.t < cfg.SIM_DURATION_S:               # one loop = 1 second
    cars = mob.step()                           # move cars
    new = gen.normal_requests(mob.t, cars)      # new requests this second
    all_reqs += new                             # keep them all
    alive = [r for r in alive if mob.t < r["arrival_s"] + r["hold_s"]] + new   # drop finished ones, add new ones
    demand.append((mob.t, sum(sum(r["cpu"]) for r in alive)))                   # CPU asked right now
mob.close()

# ---------------- summary ----------------
N = len(all_reqs)
via_cloud = sum(r["entry"] == cfg.CLOUD_ID for r in all_reqs)
print("=" * 60)
print("STEP 3 - normal SFC requests (seed %d)" % SEED)
print("=" * 60)
print(f"total requests          : {N}  (expected about {cfg.LAMBDA_NORMAL*cfg.SIM_DURATION_S:.0f})")
print(f"safety SFCs             : {sum(r['safety'] for r in all_reqs)} ({sum(r['safety'] for r in all_reqs)/N*100:.1f}%)")
print(f"entered via RSU / cloud : {N-via_cloud} / {via_cloud}")
print(f"chain length            : avg {np.mean([len(r['chain']) for r in all_reqs]):.2f} (min {min(len(r['chain']) for r in all_reqs)}, max {max(len(r['chain']) for r in all_reqs)})")
print(f"CPU per SFC             : avg {np.mean([sum(r['cpu']) for r in all_reqs]):.1f} cores")
print(f"memory per SFC          : avg {np.mean([sum(r['mem']) for r in all_reqs]):.1f}")
print(f"holding time            : avg {np.mean([r['hold_s'] for r in all_reqs]):.1f} s")
d = [x for _, x in demand]
print(f"CPU asked by alive SFCs : avg {np.mean(d):.0f}, peak {max(d):.0f} cores  "
      f"(all 25 RSUs together have {25*96} cores)")

# ---------------- save ----------------
p = os.path.join(cfg.RESULTS_DIR, f"step3_requests_seed{SEED}.csv")
with open(p, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["req_id", "arrival_s", "car_id", "x", "y", "entry", "chain", "cpu", "mem",
                "pkt_rate_pps", "hold_s", "safety", "is_attack"])
    for r in all_reqs:
        w.writerow([r["req_id"], r["arrival_s"], r["car_id"], r["x"], r["y"], r["entry"],
                    ">".join(r["chain"]), ";".join(f"{c:g}" for c in r["cpu"]),
                    ";".join(f"{m:g}" for m in r["mem"]), r["pkt_rate_pps"], r["hold_s"],
                    int(r["safety"]), int(r["is_attack"])])
print(f"saved {p}")

fig, ax = plt.subplots(figsize=(8, 4.5))                      # graph 1: demand over time
ax.plot([t for t, _ in demand], d)
ax.set_xlabel("simulation time (s)")
ax.set_ylabel("CPU asked by alive SFCs (cores)")
ax.set_title("Total CPU demand of normal SFCs (no attack)")
p = os.path.join(cfg.RESULTS_DIR, "step3_demand_over_time.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig)
print(f"saved {p}")

cnt = Counter(r["entry"] for r in all_reqs)                    # graph 2: requests per RSU
ids = sorted(net.rsus, key=lambda r: int(r.replace("RSU", "")))
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(range(len(ids)), [cnt[r] for r in ids], marker="o")
ax.set_xticks(range(len(ids))); ax.set_xticklabels([r.replace("RSU", "") for r in ids])
ax.set_xlabel("RSU number")
ax.set_ylabel("requests entered (requests)")
ax.set_title("Normal SFC requests entering through each RSU (1 hour)")
p = os.path.join(cfg.RESULTS_DIR, "step3_requests_per_rsu.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig)
print(f"saved {p}")
print("\nRESULT: Step 3 OK")
