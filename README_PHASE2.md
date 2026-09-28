# Phase 2: Secure VNF Migration under False Position Reports

**One-line idea:** migration decisions depend on **where vehicles say they are**. A lying vehicle can
make the network move services to the wrong place, over and over. Phase 2 scores how believable each
report is (the **confidence score**) and only lets believable reports drive decisions.

---

## How to run

| Command | What it does | Time |
|---|---|---|
| `pytest -v` | 57 tests (20 baseline + 20 Phase 1 + 17 Phase 2) | ~5 s |
| `python phase2_experiments.py` | All Phase 2 experiments + 7 graphs in `results/phase2/` | ~3 min |
| `run_phase2.bat` | Double-click on Windows: both of the above | ~3 min |

All Phase 2 settings are at the bottom of `config.py`. Every name starts with `P2_`, so they can never
overwrite a SPAVM or Phase 1 setting (a test checks for duplicate names).

**Setup:** 20 RSUs (SPAVM scenario 2), 80 vehicles, 50 time slots of 5 s, averaged over 5 seeds.

---

## Step 1: Mobility attacker (`spavm/mobility_attack.py`)

Every vehicle has a **true position** (physics) and a **reported position** (what the controller is
told). SPAVM only ever sees the reported one.

**Attack types, with parameters from the VeReMi dataset paper** (van der Heijden, Lukaseder, Kargl,
SecureComm 2018):

| Attack | What the liar reports |
|---|---|
| Constant position | always the same fixed point |
| Constant offset | true position + (250 m, −150 m) |
| Random position | a random point anywhere in the area, every slot |
| Random offset | true position + random offset in [−300, 300] m |
| Eventual stop | honest at first, then "freezes" on one old position (freeze chance +0.025 per report) |

`mixed` (default) spreads liars evenly over all five types. Default: 20% of vehicles lie.

**Honest vehicles aren't perfect:** GPS noise of about 5 m, and 2% of the time a 150 m error. That's
why confidence is a score, not a yes/no.

**About the VeReMi dataset itself:** the download sites are blocked from the workspace these
experiments ran in, so the attack *types and parameters* come from the VeReMi paper and are generated
inside our simulator. This also gives exact ground truth. Feeding in the real VeReMi Extension traces
(SUMO, Luxembourg map) is a possible later upgrade.

---

## Step 2: Confidence score (`spavm/confidence.py`)

For each report, the controller computes **C between 0 and 1**:

| Part | What it checks | Matching VeReMi detector |
|---|---|---|
| **C_signal** | The RSU that received the message measures signal strength (RSSI). Path loss: `RSSI(d) = P0 − 10·θ·log10(d) + noise`, with the same θ = 2 as SPAVM eq. 10. Compare the measured RSSI with the RSSI expected at the *claimed* distance. A claim outside the RSU's radio range is impossible, so it scores 0. | Acceptance Range Threshold |
| **C_neighbours** | Every other RSU that heard it does the same check. An RSU that *should* have heard it (claim well inside its range) but didn't counts as a contradiction. | multi-RSU consistency |
| **C_physics** | Is the jump from the last report possible at ≤ 40 m/s? | Simple Speed Check |
| **T_v** (history) | The **same Beta trust formula as Phase 1**, applied to vehicles: good evidence = C_now, bad = 1 − C_now | (Phase 1 reuse) |

```
C_now = mean(C_signal, C_neighbours, C_physics)
C     = C_now × (0.5 + 0.5 × T_v)        history can at most halve confidence
```

- **Link to Phase 1:** when Phase 1 trust is on, each RSU's opinion in C_neighbours is weighted by
  that RSU's trust T.
- **Result (graphs 1, 2):** 91–100% of lying reports are flagged for four attack types (79% for
  eventual stop, which is honest before it freezes), with only **1.2% false alarms** on honest vehicles.

---

## Step 3: Confidence-aware placement and migration (`simulator.py`, `followme.py`)

**Where reports are used:** the controller picks each vehicle's **serving RSU** from its position.

| Scheme | How the serving RSU is chosen |
|---|---|
| **SPAVM** (as published) | nearest RSU to the **reported** position (trusts every report) |
| **Ignore reports** | the RSU that physically received the message (never trusts reports) |
| **Confidence (ours)** | if C ≥ 0.5: nearest to the report, **but only among RSUs that physically heard the vehicle**; otherwise the receiving RSU |
| **Oracle** | nearest to the **true** position (best possible, not realistic) |

**Important finding: SPAVM's own VIMA is almost immune to position lies.** VIMA only straightens chain
paths (removes loops); it never moves a service *because a vehicle moved*. With 40% random-position
liars, VIMA made no more migrations than without liars. So the migration threat applies to
**mobility-following migration**, not to SPAVM's path clean-up.

**So we added the standard vehicular migration, "follow-me" (`spavm/followme.py`):** each vehicle's
service is kept near it; when the vehicle's serving RSU is more than 1 hop from its service, the
service migrates there (cost = hops × migration cost per hop, the same unit as VIMA's eq. 6). This is
the kind of migration a liar can abuse.

**Tested and removed:** a confidence-weighted VIMA objective (expected delay under "true vs false").
It did not help, and it raised misled VIMA decisions even with no liars (5.2% vs 1.4% for plain SPAVM).

---

## Step 4: Migration storm guard (`followme.py`)

**Storm:** a random-position liar "jumps" every slot, so SPAVM keeps migrating its service.
**Guard:** migrate only if the same target RSU is requested **2 slots in a row** (hysteresis). A
random jumper is never stable. An honest vehicle waits at most one extra slot.

---

## Step 5: Results (`results/phase2/`)

### Headline: 40% of vehicles lying (random position)

| Scheme | Migrations / slot | Migration cost / slot | Misled migrations | Honest access delay |
|---|---|---|---|---|
| SPAVM | **29.6** | **107.5** | **58.9%** | 5.1 ms |
| Ignore reports | 13.6 | 41.9 | 17.4% | 7.5 ms |
| **Confidence (ours)** | **12.2** | **37.3** | **9.1%** | **5.1 ms** |
| **Confidence + guard (ours)** | 9.5 | 30.7 | **1.2%** | 9.8 ms |
| Oracle | 11.2 | 33.8 | 0% | 4.8 ms |

With all five attack types mixed (40% liars), SPAVM sends **24%** of requests to RSUs the vehicle
can't reach, and wastes about 50 container cold starts. Every other scheme: 0.

### The 7 graphs

| File | What it shows |
|---|---|
| `1_confidence_distribution.png` | honest reports score high (~0.8), lies score low: a clear gap at the threshold |
| `2_detection_by_attack.png` | share of lies caught per VeReMi attack type, and honest false alarms (1.2%) |
| `3_migrations_per_slot.png` | the storm: SPAVM's migrations rise with liars; ours stay flat near the oracle |
| `4_migration_cost.png` | same story in cost units per slot |
| `5_corrupted_migrations.png` | % of migrations sent somewhere the vehicle isn't |
| `6_honest_access_delay.png` | the price for honest users of each defence |
| `7_unreachable_requests.png` | requests SPAVM sends to RSUs the vehicle can't reach |

CSV tables with all numbers are next to the graphs.

---

## Honest findings (say these)

1. **"Just ignore all reports" is not free.** It removes lies, but honest users' services sit farther
   away (7.5 ms vs 5.0 ms) and it makes wrong migrations even with no liars (~17%), because the
   receiving RSU isn't always the nearest. **The confidence score keeps the benefit of honest reports
   while rejecting lies.** This is the argument for Phase 2.
2. **The storm guard is a trade-off:** it cuts misled migrations to about 1% and cost below the
   oracle, but honest access delay roughly doubles (about 5 → 10 ms), because honest vehicles wait an
   extra slot. Use it when attacks are expected; tune `P2_STABLE_SLOTS`.
3. **SPAVM's VIMA is not the victim;** mobility-following migration is. Stated above; it's a finding,
   not a limitation to hide.
4. **Honest users' chain delay barely changes** under lies (about 30–33 ms in all schemes). The damage
   is to cost, wasted resources, lost requests and misled migrations.
5. **Assumptions:** RSUs measure RSSI honestly (Phase 1 trust covers dishonest RSUs); liars don't
   change their transmit power; follow-me cost is reported separately from VIMA's Lyapunov budget
   (sharing it made the queues grow even with no attackers, which starved VIMA in every scheme).

---

## Files added or changed in Phase 2

| File | Step | What |
|---|---|---|
| `config.py` | all | `P2_` settings |
| `spavm/mobility_attack.py` | 1 | VeReMi attack types, honest GPS noise |
| `spavm/confidence.py` | 2 | RSSI, neighbour and speed checks, vehicle trust, C |
| `spavm/simulator.py` | 3 | reports each slot, serving-RSU choice per scheme, metrics |
| `spavm/followme.py` | 3b, 4 | follow-me service migration and storm guard |
| `spavm/vima.py` | 3 | "misled migration" check (re-scores each decision with true positions) |
| `spavm/spvir.py`, `model.py`, `metrics.py` | 3 | small hooks and new numbers |
| `phase2_experiments.py` | 5 | experiments and graphs |
| `tests/test_phase2.py` | 1–4 | 17 tests |

With Phase 2 switched off (the default), the SPAVM baseline and Phase 1 results are **exactly
unchanged** (checked against the earlier run).
