# =====================================================================
# step2b_record_trace.py  -  run SUMO ONCE and save every car position
# ---------------------------------------------------------------------
# Run once:  python step2b_record_trace.py        (about 2-3 minutes)
# Output: data/mobility_trace_seed42.csv.gz  with columns  t, car, x, y, rsu
# After this, every simulation replays this file (config.USE_MOBILITY_TRACE = True).
# Run it again only if you change the map, the trips, the SUMO seed or the RSU positions.
# =====================================================================

import csv, gzip
import config as cfg
from network import load_network
from mobility import Mobility

net = load_network()
mob = Mobility(net, live=True)                       # force LIVE SUMO for recording
mob.start()
rows = 0
with gzip.open(cfg.TRACE_FILE, "wt", newline="") as f:   # compressed csv
    w = csv.writer(f)
    w.writerow(["t", "car", "x", "y", "rsu"])            # header
    while mob.t < cfg.SIM_DURATION_S:                    # every second of the hour
        for car, (x, y, rsu) in mob.step().items():      # every car on the road
            w.writerow([mob.t, car, round(x, 1), round(y, 1), rsu or ""])
            rows += 1
mob.close()
print(f"saved {cfg.TRACE_FILE}  ({rows} car-seconds)")
