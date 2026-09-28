import argparse
import os
import config
from spavm.simulator import Simulator


def main():
    ap = argparse.ArgumentParser(description="SPAVM baseline single run")
    ap.add_argument("--stage", default=config.DEFAULT_STAGE, choices=list(config.STAGES))
    ap.add_argument("--seed", type=int, default=config.SEED)
    a = ap.parse_args()
    sc = config.STAGES[a.stage]

    sim = Simulator(**sc, seed=a.seed)
    m = sim.run()
    print(f"SPAVM | Stage {a.stage} | {sc} | mu={config.MU_HOPS} | seed={a.seed}\n")
    for r in m.rows:
        print(f"slot {r['slot']:2d} | arr={r['arrived']:2d} acc={r['accepted']:2d} "
              f"reuse={r['reuse']:2d} cold={r['cold']:2d} cloudU={r['cloud_uncovered']} "
              f"cloudF={r['cloud_infeasible']} mig={r['migrations']} del={r['deleted']:2d} "
              f"alive={r['containers']:2d} D={r['D_total']:7.3f}s R={r['R_total']:6.2f} Q={r['Q_sum']:.2f}")
    print("\n--- Final RSU state (constraints 16-18) ---")
    for r in sim.rsus:
        print(f"RSU{r.rid} deg={sim.G.degree[r.rid]} cpu {r.used['cpu']:.0f}/{r.cap['cpu']} "
              f"mem {r.used['mem']:.2f}/{r.cap['mem']} bw {r.used['bw']:.0f}/{r.cap['bw']}")

    print("\n--- Sanity comparison (same seed, same requests) ---")
    print("SPAVM (SPVIR+VIMA):", m.summary())
    print("SPVIR only        :", Simulator(**sc, seed=a.seed, enable_vima=False).run().summary())
    print("No reuse          :", Simulator(**sc, seed=a.seed, enable_reuse=False).run().summary())

    os.makedirs("results", exist_ok=True)
    out = f"results/stage{a.stage}_seed{a.seed}.csv"
    m.to_csv(out)
    print(f"\nPer-slot CSV saved to {out}")


if __name__ == "__main__":
    main()
