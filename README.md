# SPAVM Baseline Reproduction (MTP Phase 1)

Reproduction of **SPAVM** (Hu, Zhang, Qu, Ye — IEEE TSC 2025): SFC placement with VNF
instance reuse (**SPVIR**, Alg. 1) + VNF instance migration (**VIMA**, Alg. 2) with
Lyapunov optimization, at reduced scale. This is the base for the trust-aware extension.

## 1. Setup (one time)
```bash
cd SPAVM_baseline
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Mac / Linux
pip install -r requirements.txt
```

## 2. Run (in this order)
| Command | What it does | Time |
|---|---|---|
| `pytest -v` | 20-point validation checklist. Run FIRST. | <1 s |
| `python run.py --stage A` | 5 RSUs, 10 slots: per-slot table + comparison + CSV | <1 s |
| `python run.py --stage B` / `--stage C` | 10 / 20 RSUs, 20 slots | ~1 s |
| `python experiments.py` | Paper-style sweeps, 5 seeds, CSV + PNG in `results/` | ~15 s |

## 3. Folder map
```
config.py          all parameters ([P] = from paper, [A] = our assumption)
run.py             single run of one stage
experiments.py     sweeps: slots 20-50 and RSUs 10-40 (paper Fig. 5-7 pattern)
spavm/
  model.py         data classes: VNFType, Container, RSU, Vehicle, SFCRequest, Placement
  network.py       random RSU graph G=(N,L), hop matrix
  workload.py      20 VNF types, SFC catalog (2-6 VNFs), Poisson requests, vehicle mobility
  resources.py     ONLY place that changes CPU/mem/BW (eq. 16-18) + per-slot invariant check
  delay_cost.py    eq. 5-14 (cost and delay)
  lyapunov.py      eq. 20-31 (virtual migration-cost queues, drift-plus-penalty)
  spvir.py         Algorithm 1 (placement with reuse)
  vima.py          Algorithm 2 (branch-and-bound migration)
  simulator.py     SimPy time-slot loop tying it all together
  metrics.py       per-slot rows, summary, CSV export
tests/test_spavm.py  the 20-point checklist as automatic tests
results/           outputs (CSV + PNG)
```

## 4. Reading the per-slot output
- `arr/acc`: requests arrived / accepted
- `cloudU`: vehicle outside RSU coverage R → sent to cloud (Alg. 1 lines 2-3)
- `cloudF`: no RSU within μ hops has resources → rejected, fully rolled back
- `reuse/cold`: warm reuse of an existing container vs new container from cloud
- `mig`: VIMA migrations. `del`: containers deleted after λ idle slots (eq. 4)
- `D`: total delay (eq. 14). `R`: total cost (eq. 8). `Q`: sum of migration-cost queues (eq. 20)

## 5. Results obtained (seed 42 / 5-seed averages)

**Stage A (5 RSUs, 10 slots):** 37/39 accepted, reuse ratio 0.78, avg delay 0.41 s/request
vs 1.81 s with no reuse. **0 migrations — this is correct, not a bug:** 23 of 37 chains
need 0 hops and only 2 contain a loop, so no move improves the objective. Migration needs
a larger network to matter.

**Stage B (10 RSUs):** 8 migrations, multi-hop delay 3.20 → 2.81 s (−12%) vs SPVIR-only.
**Stage C (20 RSUs):** 15 migrations, multi-hop delay 7.64 → 6.72 s (−12%).

**Trend check vs paper (all hold):**
| Paper claim | Our result |
|---|---|
| Delay rises with time slots (Fig. 6a) | 37 → 72 s over 20→50 slots |
| Delay rises with RSU count, more steeply (Fig. 6b) | 37 → 114 s over 10→40 RSUs |
| Migrations rise with time slots (Fig. 5) | 9.6 → 19.4 |
| Reuse (warm start) beats cold start | ~8-10x lower delay and cost |
| Migration trades short-term cost for delay | VIMA: lower hop delay, ~8-10% higher cost |

## 6. Interpretations of paper ambiguities (state these in thesis)
1. **Hop reference:** text says μ is between consecutive VNFs; Alg. 1 line 7 uses n_init. Default = text; switch with `HOP_REFERENCE`.
2. **Cold start (eq. 2):** eq. 2 says "no container on any RSU"; Fig. 2 text re-downloads when none exists *within μ hops*. We follow Fig. 2.
3. **VIMA objective:** eq. 32 drops the delay term, so migration could never look beneficial. We use eq. 31 (drift + δ·delay).
4. **Alg. 2** keeps only the argmin branch per container (lines 23-25) → sequential branch-and-bound; can hit local optima (paper admits this).
5. **Migration of in-use containers:** eq. 3 says only unused containers migrate; we migrate after the slot's placement decisions, and re-check every chain's hop limit after the move.
6. **Container sharing** capped by `MAX_SHARE` (paper silent).
7. All `[A]` values in `config.py` (μ, λ, C, δ, radio constants, delays, unit costs) are assumptions.

## 7. Thesis wording
Valid: *"I reproduced the SPAVM algorithms (SPVIR and VIMA with Lyapunov optimization)
under a reduced simulation scale with stated parameter assumptions; qualitative trends
match the paper."*
Not valid: *"I reproduced SPAVM's numerical results."*

## 8. Next step: trust hook
Trust enters in one place: the reuse candidate filter in `spvir.py`
(find reusable → check resources/hops → **check trust** → reuse or redeploy).

**Phase 1 is now implemented. See `README_PHASE1.md`.**
**Phase 2 is now implemented. See `README_PHASE2.md`.**
