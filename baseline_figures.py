"""Baseline figures (visual only, no simulation logic changed).

Makes three outputs in results/figures/:
  1_rsu_topology.png           RSU positions and links for 10, 20, 30, 40 RSUs (like paper Fig. 4)
  2_vehicles_two_slots.png     the 10-RSU map with vehicles (seen from above, pointing where they drive)
                               in one slot and in the next slot (5 s later), to show them moving
  3_requests_per_slot.csv      table: RSUs, vehicles, lowest / highest / average requests per slot
Run:  python baseline_figures.py      (about 10 seconds)
"""
# WHAT THIS FILE DOES: draws pictures and a table FROM the simulator. It only reads what the
#   simulator builds (RSU positions, links, vehicles, per-slot request counts). It changes nothing.
# WHY WE NEED IT: to show the network layout (paper Fig. 4) and the traffic load in the thesis/slides.
# WHO USES IT: nobody imports it; run it yourself. It uses spavm/simulator.py.
import csv  # to write the table as a .csv file (opens in Excel)
import math  # math.atan2 / math.degrees: turn a speed (vx, vy) into an angle
import os  # to create the output folder
import statistics  # statistics.mean() for the average
import matplotlib  # plotting library
matplotlib.use("Agg")  # save pictures to files, no window
import matplotlib.pyplot as plt  # short name plt
from matplotlib.patches import Rectangle  # a rectangle shape (the car seen from above)
from matplotlib.transforms import Affine2D  # used to rotate each car rectangle
from spavm.simulator import Simulator  # builds the network and vehicles exactly as in the experiments
from spavm.workload import move_vehicles  # the SAME function the simulator uses to move cars each slot

OUT = "results/figures"  # output folder
SIZES = [10, 20, 30, 40]  # RSU counts = the paper's 4 scenarios (Fig. 4)
SEED = 1  # layout seed used for the pictures (seed 1 = first seed of the experiments)
TABLE_SEEDS = [1, 2, 3, 4, 5]  # seeds used for the table (same as experiments.py)
TABLE_SLOTS = 50  # slots simulated for the table

# Colors: blue = RSU, grey = link, orange = vehicle (same palette as the other graphs).
RSU_C, LINK_C, CAR_C, INK = "#2a78d6", "#b9b8b3", "#eb6834", "#0b0b0b"
CAR_L, CAR_W, ARROW_L = 40.0, 18.0, 55.0  # car length/width and arrow length in metres (drawn larger
#                                             than real so they are visible; arrow length is FIXED,
#                                             it shows direction only, not speed)


def draw_topology(ax, sim, n, with_cars, title=None):
    """Draw one panel: links (lines), RSUs (numbered dots) and optionally the vehicles."""
    # Links: every edge (a, b) of the graph G is a straight line between the two RSU positions.
    for a, b in sim.G.edges:
        ra, rb = sim.rsus[a], sim.rsus[b]
        ax.plot([ra.x, rb.x], [ra.y, rb.y], color=LINK_C, lw=1.4, zorder=1)
    if with_cars:
        for v in sim.vehicles:  # each car: a rectangle rotated to its driving direction + an arrow
            ang = math.degrees(math.atan2(v.vy, v.vx))  # direction angle from the real speed (vx, vy)
            # Rectangle centred on the car: start at (x - L/2, y - W/2), then rotate around (x, y).
            rect = Rectangle((v.x - CAR_L / 2, v.y - CAR_W / 2), CAR_L, CAR_W, facecolor=CAR_C,
                             edgecolor="white", lw=0.6, zorder=3,
                             transform=Affine2D().rotate_deg_around(v.x, v.y, ang) + ax.transData)
            ax.add_patch(rect)
            sp = math.hypot(v.vx, v.vy) or 1.0  # speed, only used to make a unit direction
            dx, dy = v.vx / sp * ARROW_L, v.vy / sp * ARROW_L  # fixed-length arrow in that direction
            ax.annotate("", xy=(v.x + dx, v.y + dy), xytext=(v.x, v.y), zorder=4,
                        arrowprops=dict(arrowstyle="-|>", color=CAR_C, lw=1.2))
    # RSUs: dots with their number (rid) written inside.
    for r in sim.rsus:
        ax.scatter(r.x, r.y, s=260 if n <= 20 else 170, color=RSU_C, edgecolor="white", lw=1.5, zorder=5)
        ax.text(r.x, r.y, str(r.rid), color="white", fontsize=7 if n <= 20 else 6,
                ha="center", va="center", fontweight="bold", zorder=6)
    ax.set_xlim(-60, sim.side + 60)  # small margin around the square map
    ax.set_ylim(-60, sim.side + 60)
    ax.set_aspect("equal")  # 1 m in x = 1 m in y, so distances look right and the box is a square
    if title is None:
        title = f"{n} RSUs, {sim.G.number_of_edges()} links"
    ax.set_title(title, fontsize=11, loc="left", fontweight="bold")
    ax.set_xlabel("x (m)", fontsize=9)
    ax.set_ylabel("y (m)", fontsize=9)
    ax.tick_params(labelsize=8)
    for s in ("top", "right", "bottom", "left"):  # all four sides drawn = square boundary (like paper Fig. 4)
        ax.spines[s].set_visible(True)
        ax.spines[s].set_color(INK)
        ax.spines[s].set_linewidth(1.2)


def figure_topology():
    """Figure 1: RSUs and links only, one square panel per network size (like paper Fig. 4)."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 12))  # 2 x 2 panels, one per network size
    for ax, n in zip(axes.flat, SIZES):  # axes.flat = the 4 panels in order
        sim = Simulator(n, 1, 4 * n, seed=SEED)  # builds network + vehicles only (run() is NOT called)
        draw_topology(ax, sim, n, with_cars=False)
    fig.tight_layout()
    fig.savefig(f"{OUT}/1_rsu_topology.png", dpi=150)
    plt.close(fig)
    print("saved", f"{OUT}/1_rsu_topology.png")


def figure_vehicles_two_slots(n=10):
    """Figure 2: the 10-RSU map with its vehicles in one slot and in the next slot."""
    sim = Simulator(n, 1, 4 * n, seed=SEED)  # same network and vehicles as panel 1 of Figure 1
    fig, axes = plt.subplots(1, 2, figsize=(14, 7.2))
    draw_topology(axes[0], sim, n, with_cars=True,
                  title=f"Slot t: {n} RSUs, {len(sim.vehicles)} vehicles")
    move_vehicles(sim.vehicles, sim.side)  # move every car by one slot (5 s), exactly as the simulator does
    draw_topology(axes[1], sim, n, with_cars=True,
                  title=f"Slot t+1 (5 s later): same RSUs, vehicles moved")
    fig.tight_layout()
    fig.savefig(f"{OUT}/2_vehicles_two_slots.png", dpi=150)
    plt.close(fig)
    print("saved", f"{OUT}/2_vehicles_two_slots.png")


def request_table():
    """Table 3: requests per slot for each network size (runs the plain SPAVM baseline)."""
    rows = []
    for n in SIZES:
        per_slot = []  # request count of every slot, for all seeds together
        for sd in TABLE_SEEDS:
            m = Simulator(n, TABLE_SLOTS, 4 * n, seed=sd).run()
            per_slot += [r["arrived"] for r in m.rows]  # "arrived" = requests created in that slot
        rows.append({"RSUs": n, "vehicles": 4 * n, "slots x seeds": f"{TABLE_SLOTS} x {len(TABLE_SEEDS)}",
                     "lowest requests in a slot": min(per_slot),
                     "highest requests in a slot": max(per_slot),
                     "average requests per slot": round(statistics.mean(per_slot), 2)})
    with open(f"{OUT}/3_requests_per_slot.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("saved", f"{OUT}/3_requests_per_slot.csv")
    for r in rows:
        print(r)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    figure_topology()
    figure_vehicles_two_slots()
    request_table()
