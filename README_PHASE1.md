# Phase 1: Trust in Reused VNF Containers

**One-line idea:** SPAVM reuses any container that has space and is close enough. It never asks whether
the RSU hosting it can be **trusted**. Phase 1 adds that check, in 4 steps, on top of the SPAVM baseline.

**Analogy:** SPAVM is a shared taxi you jump into because it's nearby and has a free seat. Phase 1
checks the driver's licence first.

---

## How to run

| Command | What it does | Time |
|---|---|---|
| `pytest -v` | 40 tests (20 baseline + 20 Phase 1) | ~1 s |
| `python phase1_experiments.py` | All security experiments + 7 graphs in `results/phase1/` | ~30 s |
| `run_phase1.bat` | Double-click on Windows: both of the above | ~30 s |

All Phase 1 settings are at the bottom of `config.py`, under "PHASE 1".

---

## Step 1: Attacker model (`spavm/attacker.py`)

**What:** we decide which RSUs are bad and how they behave.

- **Who:** a fixed share of RSUs (default 20%) is compromised. The *same* RSUs are bad in every scheme we
  compare, and the *same* vehicle requests arrive, so the comparison is fair.
- **Tampering:** a container on a bad RSU corrupts an SFC passing through it with probability
  `P_TAMPER = 0.8`.
- **Lying:** a bad RSU **always claims "I'm healthy"**. This is the "lying node" of your thesis.
- **Attacker types:**
  - `always`: attacks every slot.
  - `onoff`: good for 5 slots, bad for 5 slots. It tries to rebuild trust between attacks.
  - stealthy: `always` with a low `P_TAMPER` (0.2), so it's harder to notice.
- **Honest RSUs aren't perfect:** they have small random faults (`P_FAULT = 0.02`) and report them
  truthfully. This noise is what makes trust a real problem. Without it, detection would be trivial.

**Why:** you can't measure a defence without a clear attacker. These three types cover the basic case
and the two classic ways to fool a reputation system.

---

## Step 2: Trust score (`spavm/trust.py`)

**What:** every RSU gets a trust score **T between 0 and 1**, updated every slot.

We keep two counters per RSU: **a** (good evidence) and **b** (bad evidence).

```
each slot:   a  <-  0.9 × a  +  good evidence
             b  <-  0.9 × b  +  3 × bad evidence
trust        T  =  (a + 1) / (a + b + 2)
confidence   n  =  a + b
```

**Where the evidence comes from** (never from what the RSU says about itself, because liars lie):

| Evidence | How it works | Why |
|---|---|---|
| **E1 Probes** | Each slot the controller sends a known test packet through 30% of RSUs and checks the answer | Direct, reliable evidence |
| **E2 SFC outcomes** | After each SFC, an end-to-end check (catches 90% of tampering). Success: small credit to every RSU on the chain. Failure: blame is **shared across the chain**, with more blame to RSUs that are already less trusted | Chain-level blame, the novel part |
| **E3 Lie detection** | The RSU said "healthy" but its probe just failed: extra penalty | Targets lying nodes directly |

**Why the formula looks like this (plain words):**

- **Starts at 0.5:** a new RSU is "unknown", neither trusted nor distrusted.
- **0.9 forgetting (γ):** old evidence slowly fades, so the score follows *current* behaviour (like EWMA).
- **Bad counts 3× (ρ = 3):** trust is slow to gain and fast to lose. This stops on-off attackers
  (see graph 6).
- **Confidence n:** 0.8 from 2 observations isn't the same as 0.8 from 200. Phase 2 reuses this.

This is a Beta reputation system with forgetting, a standard base in trust literature (Jøsang & Ismail,
2002). The asymmetric update against on-off attacks is also standard. Verify exact citations before the
thesis.

---

## Step 3: Trust-aware SPVIR and VIMA (`spvir.py`, `vima.py`, `simulator.py`)

**What:** one new check, the **trust gate**, added in three places.

```
SPAVM:          find container -> space & hops OK? -> REUSE
SPAVM + Trust:  find container -> space & hops OK? -> is its RSU trusted? -> REUSE
                                                                    no  -> skip it, use / create one on a trusted RSU
```

- **Gate rule:** an RSU is allowed if it has too little evidence yet (benefit of the doubt, it gets
  probed), **or** if `T ≥ 0.6`.
- **Where it applies:**
  1. reuse of existing containers,
  2. new cold-start containers,
  3. VIMA migration targets (never move a container *onto* an untrusted RSU).
- **Quarantine (optional mode):** RSUs with `T < 0.3` are emptied. They are still probed, so a good RSU
  that was wrongly flagged can recover.
- **Oracle (for comparison only):** a scheme that magically knows the bad RSUs. It shows the best
  possible result.

**Why:** it's the smallest change to SPAVM that closes the gap. Everything else in SPAVM stays exactly
as the paper describes. Test `test_p3_no_trust_mode_equals_plain_spavm` proves that with trust off,
results are identical to the baseline.

---

## Step 4: Experiments and graphs (`phase1_experiments.py` → `results/phase1/`)

**Setup:** 10 RSUs (paper scenario 1), 50 slots, 5 random seeds averaged. Same requests and same bad
RSUs for every scheme.

### Headline result (20% of RSUs compromised, always-bad)

| Scheme | SFCs poisoned | Avg delay | Accepted | Honest RSUs wrongly blocked |
|---|---|---|---|---|
| SPAVM (paper, no trust) | **29.4%** | 185.3 ms | 96.9% | 0% |
| **SPAVM + Trust (ours)** | **1.2%** | 177.7 ms | 96.0% | 4.4% |
| Oracle (knows attackers) | 0% | 158.9 ms | 96.9% | 0% |

**In one sentence:** trust cuts poisoned SFCs from about 29% to about 1%, at a small cost in wrongly
blocked honest RSUs.

### The 7 graphs

| File | What it shows | What to tell your professor |
|---|---|---|
| `1_poisoned_over_time.png` | Poisoned SFCs per slot | SPAVM stays at ~30% forever. Trust learns within **2–3 slots** and stays near 0. |
| `2_poisoned_vs_attacker_share.png` | Poisoned % vs attackers (0–40%) | SPAVM gets worse fast (**52%** at 40% attackers). Trust stays below **2.3%**. |
| `3_attacker_types.png` | Always-bad / on-off / stealthy | Trust works against all three (1.2%, 0.4%, 1.1%). |
| `4_trust_trajectories.png` | Trust score of every RSU over time | Honest RSUs stay high. The on-off attacker drops fast in bad periods and climbs back only slowly. |
| `5_price_of_security.png` | Delay and acceptance | The cost of security. At 40% attackers: ~7% more delay, ~2% fewer requests accepted. |
| `6_rho_tradeoff.png` | Effect of ρ | ρ = 3 is the sweet spot. ρ = 1 lets on-off attackers through; ρ = 5 blocks too many honest RSUs. |
| `7_sharing_limit.png` | Step 5 vs trust alone | The sharing limit adds 30–45% delay for little or negative safety gain, so it's rejected. |

CSV tables with the exact numbers are next to each graph.

---

## Step 5 (optional): Trust-based sharing limit (`share_cap` in `simulator.py`)

**Idea (from PBHB's co-location risk):** one bad container shared by many SFCs infects all of them. So let
less-trusted containers be shared by fewer SFCs.

```
RSU still untested (little evidence)  -> container may serve 1 SFC per slot
trusted RSU                           -> cap grows from 1 (at T = 0.6) to 4 (at T = 1)
without Step 5 (default)              -> every container may serve 4 SFCs (SPAVM's cap)
```

Switch it on with `Simulator(..., share_limit=True)`. It's **off by default**.

**Result (graph `7_sharing_limit.png`): it does not pay off.**

| Attacker | Poisoned: Trust | Poisoned: + sharing limit | Delay: Trust | Delay: + sharing limit |
|---|---|---|---|---|
| Always-bad | 1.16% | 1.10% | 178 ms | 255 ms |
| On-off | 0.44% | **1.44% (worse)** | 181 ms | 240 ms |
| Stealthy | 1.13% | 0.90% | 172 ms | 250 ms |
| 40% attackers | 2.29% | 1.97% | 198 ms | 253 ms |

**Why (say this in the thesis):**
1. The trust gate already blocks bad RSUs within 1–2 slots, so almost no risky window is left to protect.
2. Limiting sharing forces many more cold starts (about +50%), which adds 30–45% delay.
3. Extra cold starts spread containers across **more** RSUs, including on-off attackers during their
   "good" phase, so there's more exposure when they turn bad. That's why on-off gets worse.

**Conclusion:** keep the plain trust gate (Steps 1–3) as the contribution, and report Step 5 as a tested
alternative that was rejected, with this explanation. A tested-and-rejected design is a legitimate result.

---

## Honest findings (say these, don't hide them)

1. **Why SPAVM is so vulnerable:** *reuse spreads one bad container to many chains*. One compromised
   container serves many SFCs, so 20% bad RSUs poison ~29% of SFCs. This is the core argument for
   Phase 1.
2. **Quarantine gave the same numbers as the plain gate.** The gate already stops all use of a bad RSU,
   so emptying it adds nothing measurable here. Keep it as an option, not a contribution.
3. **The Oracle has lower delay than SPAVM.** Removing a few RSUs made containers cluster on fewer RSUs,
   which increased reuse and reduced cold starts. It's a side effect of the reuse model, **not a benefit
   of security**. Don't claim trust reduces delay.
4. **False alarms exist:** about 3–4% of honest RSU-slots are wrongly blocked (random faults +
   shared blame). Graph 6 shows the dial (ρ) that trades this against safety.
5. **Detection is fast** (2–3 slots for always-bad) partly because the attacker tampers 80% of the time.
   The stealthy (20%) and on-off cases are the fairer tests.
6. **A bug was found and fixed during Phase 1:** the trust threshold was first named `THETA`, which
   silently overwrote the path-loss exponent `THETA` of eq. 10. It's now `TRUST_THETA`, and a test
   (`test_p0_...`) guards against this. The baseline was re-checked and matches the earlier run exactly.

---

## What each file does (Phase 1 only)

| File | Step | Change |
|---|---|---|
| `config.py` | all | new PHASE 1 section with every setting |
| `spavm/attacker.py` | 1 | new: who is bad, tampering, lying, on-off |
| `spavm/trust.py` | 2 | new: counters, trust formula, probes, blame, lies, quarantine |
| `spavm/spvir.py` | 3 | 2 lines: trust gate on reuse and cold start |
| `spavm/vima.py` | 3 | 2 lines: trust gate on migration target |
| `spavm/simulator.py` | 3 | runs attacks, outcome checks, probes, trust updates each slot |
| `spavm/metrics.py` | 4 | adds poisoned rate, probes, lies caught |
| `phase1_experiments.py` | 4 | all experiments + graphs |
| `tests/test_trust.py` | 1–5 | 20 tests |

---

## How to explain the sequence to your professor

1. "First I reproduced SPAVM (SPVIR + VIMA + Lyapunov); trends match the paper."
2. "SPAVM reuses containers without checking trust. I added an attacker model: compromised RSUs that
   tamper and lie."
3. "Result: reuse *amplifies* the attack. 20% bad RSUs poison ~29% of SFCs."
4. "I added an evidence-based trust score (probes, chain-level blame, lie detection) with 'fast to lose'
   updates."
5. "A trust gate in SPVIR and VIMA cuts poisoning to ~1%, for a small delay/acceptance cost."

## Next steps (planned upgrades from the papers)

- **Chain-level security requirement S_min** per SFC (from PBHB): `Π T ≥ S_min`.
- ~~Trust-dependent container sharing~~: done as Step 5, tested and rejected (see above).
- **DRLS-VNE trust (static + activity)** as a rival baseline, to show it fails against liars.
- **Defence Success Ratio** metric (from ID-SFCM).
- **Attacker that targets high-degree RSUs** (where VIMA moves containers), which bridges to Phase 2.
