# =====================================================================
# step1_network.py  -  STEP 1: build and check the network
# ---------------------------------------------------------------------
# Run:  python step1_network.py
# Outputs (in results/):
#   step1_rsu_table.csv        - every RSU: position, CPU, memory, fibre degree, cloud delay
#   step1_neighbours_2hop.csv  - for every RSU: RSUs within 2 fibre hops (used by partial scale-out)
#   step1_network_map.png      - Powai roads + RSUs + 300 m ranges + fibre links
# =====================================================================

import csv                                      # to write csv files
import gzip                                     # the road network file is compressed (.gz)
import os                                       # to build output paths
import xml.etree.ElementTree as ET              # to read the SUMO .xml road network
import matplotlib                               # plotting library
matplotlib.use("Agg")                           # draw to a file, not to a window (works everywhere)
import matplotlib.pyplot as plt                 # the plotting functions
import config as cfg                            # our settings
from network import load_network                # our network library (network.py)

os.makedirs(cfg.RESULTS_DIR, exist_ok=True)     # make sure the results folder exists
net = load_network()                            # read rsus.csv + links.csv

# ---------------- 1) RSU table ----------------
print("=" * 60)
print("STEP 1 - network")
print("=" * 60)
print(f"RSUs: {len(net.rsus)}   cloud: CPU {net.cloud['cpu']:.0f}, mem {net.cloud['mem']:.0f}")
table_path = os.path.join(cfg.RESULTS_DIR, "step1_rsu_table.csv")       # output file path
with open(table_path, "w", newline="") as f:                             # create the file
    w = csv.writer(f)                                                    # csv writer
    w.writerow(["rsu", "x_m", "y_m", "cpu", "mem", "fibre_degree", "cloud_delay_ms"])   # header
    for rid, r in net.rsus.items():                                      # one row per RSU
        w.writerow([rid, r["x"], r["y"], r["cpu"], r["mem"], len(net.fibre[rid]), net.cloud_delay_ms[rid]])
print(f"saved {table_path}")

# ---------------- 2) is the fibre network connected? ----------------
groups = []                                     # list of connected groups (islands) of RSUs
done = set()                                    # RSUs already put in a group
for rid in net.rsus:                            # go through all RSUs
    if rid in done:                             # already in a group -> skip
        continue
    group = sorted(b for (a, b) in net.hops if a == rid)   # every RSU reachable from rid
    groups.append(group)                        # store this island
    done.update(group)                          # mark them as done
print(f"fibre islands: {len(groups)}  (1 = every RSU can reach every other RSU by fibre)")
for g in groups:                                # print each island
    print("   ", g)

# ---------------- 3) neighbours within 2 hops ----------------
nb_path = os.path.join(cfg.RESULTS_DIR, "step1_neighbours_2hop.csv")
counts = []                                     # how many 2-hop neighbours each RSU has
with open(nb_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["rsu", "neighbour", "hops", "fibre_delay_ms"])          # header
    for rid in net.rsus:
        nbs = net.neighbours_within(rid, cfg.MAX_OFFLOAD_HOPS)          # RSUs within 2 hops
        counts.append(len(nbs))                                         # remember the count
        for b, h, d in nbs:
            w.writerow([rid, b, h, round(d, 5)])                        # one row per neighbour
print(f"2-hop neighbours per RSU: min {min(counts)}, avg {sum(counts)/len(counts):.1f}, max {max(counts)}")
alone = [rid for rid in net.rsus if not net.neighbours_within(rid, cfg.MAX_OFFLOAD_HOPS)]
print(f"RSUs with NO neighbour within 2 hops (can only offload to cloud): {alone if alone else 'none'}")
print(f"saved {nb_path}")

# ---------------- 4) map ----------------
fig, ax = plt.subplots(figsize=(12, 9))          # one figure, 12 x 9 inches
with gzip.open(cfg.NET_FILE, "rt") as f:         # open the compressed SUMO network as text
    root = ET.parse(f).getroot()                 # parse the XML
for edge in root.iter("edge"):                   # every road segment
    if edge.get("function") == "internal":       # skip tiny internal junction pieces
        continue
    lane = edge.find("lane")                     # take the first lane of the road
    if lane is None:                             # no lane -> nothing to draw
        continue
    pts = [tuple(map(float, p.split(","))) for p in lane.get("shape").split()]   # "x,y x,y ..." -> list of (x, y)
    ax.plot([p[0] for p in pts], [p[1] for p in pts], color="lightgrey", linewidth=0.6, zorder=1)   # draw the road

drawn = set()                                    # fibre links already drawn (each link only once)
for a in net.fibre:
    for b in net.fibre[a]:
        if (b, a) in drawn:                      # already drawn from the other side
            continue
        drawn.add((a, b))
        ra, rb = net.rsus[a], net.rsus[b]
        ax.plot([ra["x"], rb["x"]], [ra["y"], rb["y"]], color="tab:green", linewidth=1.8, zorder=2)   # fibre link

for rid, r in net.rsus.items():                  # RSUs
    ax.add_patch(plt.Circle((r["x"], r["y"]), cfg.RSU_RANGE_M, color="tab:blue", alpha=0.08, zorder=2))   # 300 m range
    ax.plot(r["x"], r["y"], marker="^", color="tab:red", markersize=9, zorder=3)                          # RSU symbol
    ax.annotate(rid, (r["x"], r["y"]), textcoords="offset points", xytext=(5, 5), fontsize=8, zorder=4)   # RSU name

ax.set_xlabel("x position (m)")                  # axis names with units
ax.set_ylabel("y position (m)")
ax.set_title("Powai network: RSUs (red), 300 m range (blue), fibre links (green)")
ax.set_aspect("equal")                           # 1 m on x = 1 m on y
map_path = os.path.join(cfg.RESULTS_DIR, "step1_network_map.png")
fig.savefig(map_path, dpi=150, bbox_inches="tight")   # save the picture
print(f"saved {map_path}")
print("\nRESULT: Step 1 OK")
