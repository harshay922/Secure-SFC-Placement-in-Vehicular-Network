# WHAT THIS FILE DOES: runs ONE simulation of SPAVM and prints what happened slot by slot.
# WHY WE NEED IT: it is the quickest way to check the simulator works and to see the
#   numbers (delay, cost, reuse, migrations) for one stage and one random seed.
#   It also compares SPAVM against two simpler versions (no VIMA, no reuse).
# WHO USES IT: nobody imports it; you start it yourself:  python run.py --stage B --seed 7
#   It uses config.py and spavm/simulator.py.

import argparse  # argparse = standard Python library for reading command-line options like --stage
import os  # os = functions for the operating system (here: create folders)
import config  # our settings file (config.py)
from spavm.simulator import Simulator  # "from X import Y" = take only the name Y from module X


def main():  # def = define a function; main() holds the whole program
    ap = argparse.ArgumentParser(description="SPAVM baseline single run")  # object that reads options
    # --stage: which size to run (A, B or C). choices= refuses anything else. list(dict) = list of its keys.
    ap.add_argument("--stage", default=config.DEFAULT_STAGE, choices=list(config.STAGES))
    ap.add_argument("--seed", type=int, default=config.SEED)  # type=int converts the text "7" to number 7
    a = ap.parse_args()  # actually read the command line; a.stage and a.seed now hold the values
    sc = config.STAGES[a.stage]  # dict[key] = look up; e.g. {"num_rsus": 5, "num_slots": 10, ...}

    # **sc = "unpack the dict as named arguments": same as Simulator(num_rsus=5, num_slots=10, ...)
    sim = Simulator(**sc, seed=a.seed)  # build the network, vehicles, algorithms (SPVIR + VIMA)
    m = sim.run()  # run all time slots; m is a Metrics object with per-slot results
    # f-string: f"...{x}..." puts the value of x inside the text. "\n" = new line.
    print(f"SPAVM | Stage {a.stage} | {sc} | mu={config.MU_HOPS} | seed={a.seed}\n")
    for r in m.rows:  # for-loop: r takes each row (one dict per time slot) in turn
        # {x:2d} = print x as an integer 2 characters wide; {x:7.3f} = decimal, 7 wide, 3 decimals.
        # arr = requests arrived, acc = accepted, reuse = VNFs served by an existing container,
        # cold = new containers started (cold start, eq. 2), cloudU/cloudF = sent to cloud because
        # uncovered / infeasible, mig = migrations (eq. 3), del = idle containers deleted (eq. 4),
        # D = total delay (eq. 14), R = total cost (eq. 8), Q = sum of virtual queues (eq. 20).
        # Several f-strings next to each other inside ( ) are joined into one long string.
        print(f"slot {r['slot']:2d} | arr={r['arrived']:2d} acc={r['accepted']:2d} "
              f"reuse={r['reuse']:2d} cold={r['cold']:2d} cloudU={r['cloud_uncovered']} "
              f"cloudF={r['cloud_infeasible']} mig={r['migrations']} del={r['deleted']:2d} "
              f"alive={r['containers']:2d} D={r['D_total']:7.3f}s R={r['R_total']:6.2f} Q={r['Q_sum']:.2f}")
    print("\n--- Final RSU state (constraints 16-18) ---")  # show used vs capacity on each RSU
    for r in sim.rsus:  # r is now an RSU object (the name r is reused; the old value is gone)
        # deg = number of neighbour RSUs in the graph G. used/cap must satisfy used <= cap (eq. 16-18).
        print(f"RSU{r.rid} deg={sim.G.degree[r.rid]} cpu {r.used['cpu']:.0f}/{r.cap['cpu']} "
              f"mem {r.used['mem']:.2f}/{r.cap['mem']} bw {r.used['bw']:.0f}/{r.cap['bw']}")

    # Same seed = same vehicles and requests, so the three results are a fair comparison.
    print("\n--- Sanity comparison (same seed, same requests) ---")
    print("SPAVM (SPVIR+VIMA):", m.summary())  # full method: placement with reuse + migration
    # enable_vima=False turns off Alg. 2 (no migration); shows what migration adds.
    print("SPVIR only        :", Simulator(**sc, seed=a.seed, enable_vima=False).run().summary())
    # enable_reuse=False: every VNF gets a new container; shows what reuse (Alg. 1) saves.
    print("No reuse          :", Simulator(**sc, seed=a.seed, enable_reuse=False).run().summary())

    os.makedirs("results", exist_ok=True)  # create folder "results"; exist_ok=True = no error if it exists
    out = f"results/stage{a.stage}_seed{a.seed}.csv"  # file name, e.g. results/stageA_seed42.csv
    m.to_csv(out)  # save one row per slot so we can plot it later (e.g. in Excel)
    print(f"\nPer-slot CSV saved to {out}")


# __name__ is "__main__" only when this file is run directly (python run.py),
# not when it is imported by another file. So main() runs only in the first case.
if __name__ == "__main__":
    main()
