# =====================================================================
# step2_mobility.py  -  STEP 2: run SUMO live and check car-RSU coverage
# ---------------------------------------------------------------------
# Run:  python step2_mobility.py           (takes about 1 minute)
# No requests and no attack yet. We only check the cars and the RSUs.
# Outputs (in results/):
#   step2_cars_over_time.csv / .png   - cars on the road and cars inside an RSU range, every second
#   step2_cars_per_rsu.csv            - average and peak number of cars attached to each RSU
#   step2_cars_per_rsu.png            - average cars per RSU
# =====================================================================

import csv                                      # write csv files
import os                                       # output paths
from collections import defaultdict             # dictionary that starts every new key at 0
import matplotlib                               # plotting
matplotlib.use("Agg")                           # save pictures to file (no window)
import matplotlib.pyplot as plt                 # plotting functions
import config as cfg                            # our settings
from network import load_network                # Step 1 library
from mobility import Mobility                   # SUMO wrapper (mobility.py)

os.makedirs(cfg.RESULTS_DIR, exist_ok=True)     # make sure results/ exists
net = load_network()                            # 25 RSUs + links
mob = Mobility(net)                             # SUMO wrapper
mob.start()                                     # launch SUMO

timeline = []                                   # one row per second: (t, cars on road, cars covered by an RSU)
sum_per_rsu = defaultdict(int)                  # RSU -> sum over all seconds of attached cars (for the average)
peak_per_rsu = defaultdict(int)                 # RSU -> largest number of attached cars at any second
last_rsu = {}                                   # car -> RSU it was attached to in the previous second
handovers = 0                                   # how many times a car switched from one RSU to another
seen_cars = set()                               # every car that appeared at least once

while mob.t < cfg.SIM_DURATION_S:               # one loop = one second of traffic
    cars = mob.step()                           # move SUMO 1 s, get {car: (x, y, rsu)}
    seen_cars.update(cars)                      # remember all car ids
    count_now = defaultdict(int)                # RSU -> attached cars in THIS second
    covered = 0                                 # cars inside some RSU range in this second
    for car, (x, y, rsu) in cars.items():       # go through every car
        if rsu is not None:                     # the car is inside an RSU range
            covered += 1
            count_now[rsu] += 1
            old = last_rsu.get(car)             # RSU of this car one second ago
            if old is not None and old != rsu:  # it moved from one RSU to another
                handovers += 1
        last_rsu[car] = rsu                     # remember for the next second
    for rid in net.rsus:                        # update per-RSU statistics
        sum_per_rsu[rid] += count_now[rid]
        peak_per_rsu[rid] = max(peak_per_rsu[rid], count_now[rid])
    timeline.append((mob.t, len(cars), covered))   # store this second

mob.close()                                     # stop SUMO

# ---------------- summary on screen ----------------
T = len(timeline)                                                   # number of simulated seconds
on_road = [n for _, n, _ in timeline]                               # cars on the road per second
cov = [c for _, _, c in timeline]                                   # covered cars per second
total_car_seconds = sum(on_road)                                    # car-seconds on the road
print("=" * 60)
print("STEP 2 - SUMO mobility")
print("=" * 60)
print(f"simulated seconds        : {T}")
print(f"different cars seen      : {len(seen_cars)}")
print(f"cars on road             : avg {sum(on_road)/T:.1f}, peak {max(on_road)}")
print(f"cars inside an RSU range : {sum(cov)/max(total_car_seconds,1)*100:.1f}% of car-seconds "
      f"(the rest can only reach the cloud)")
print(f"RSU handovers            : {handovers}")

# ---------------- save files ----------------
p = os.path.join(cfg.RESULTS_DIR, "step2_cars_over_time.csv")
with open(p, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["time_s", "cars_on_road", "cars_in_rsu_range"])      # header
    w.writerows(timeline)                                            # all seconds
print(f"saved {p}")

p = os.path.join(cfg.RESULTS_DIR, "step2_cars_per_rsu.csv")
with open(p, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["rsu", "avg_cars_attached", "peak_cars_attached"])
    for rid in net.rsus:
        w.writerow([rid, round(sum_per_rsu[rid] / T, 2), peak_per_rsu[rid]])
print(f"saved {p}")

# graph 1: cars over time (plain line graph, named axes with units)
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot([t for t, _, _ in timeline], on_road, label="cars on the road")
ax.plot([t for t, _, _ in timeline], cov, label="cars inside an RSU range")
ax.set_xlabel("simulation time (s)")
ax.set_ylabel("number of cars")
ax.set_title("Cars in the Powai network over time")
ax.legend()
p = os.path.join(cfg.RESULTS_DIR, "step2_cars_over_time.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig)
print(f"saved {p}")

# graph 2: average attached cars per RSU (RSU number on x)
ids = sorted(net.rsus, key=lambda r: int(r.replace("RSU", "")))     # RSU0, RSU1, ... in number order
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(range(len(ids)), [sum_per_rsu[r] / T for r in ids], marker="o")
ax.set_xticks(range(len(ids)))
ax.set_xticklabels([r.replace("RSU", "") for r in ids])
ax.set_xlabel("RSU number")
ax.set_ylabel("average attached cars (cars)")
ax.set_title("Average number of cars attached to each RSU")
p = os.path.join(cfg.RESULTS_DIR, "step2_cars_per_rsu.png")
fig.savefig(p, dpi=150, bbox_inches="tight"); plt.close(fig)
print(f"saved {p}")
print("\nRESULT: Step 2 OK")
