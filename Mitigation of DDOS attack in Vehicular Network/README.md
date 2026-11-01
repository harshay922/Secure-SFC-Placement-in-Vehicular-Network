# Mitigation of DDoS Attacks on SFCs in Vehicular Networks

M.Tech Project (MTP-1), ISRDC Lab, CSE, IIT Bombay.
Guide: Prof. Virendra Singh. Mentor: Dr. Sarath Babu.

Attacker cars put hidden CPU/memory load on Roadside Units (RSUs) and flood their radio,
so the VNFs of normal cars' Service Function Chains (SFCs) slow down or stop.
This project simulates the attack on the real Powai map (SUMO) and tests a three-layer defence:

1. **Detect** – RSUs report real CPU/memory demand; adjusted change
   `Δ = w_cpu·|ΔCPU − ΔL_cpu| + w_mem·|ΔMEM − ΔL_mem|` is compared with
   `φ = max(φ_min, α·σ + β·λ)` (idea from CB-DRL, without blockchain).
2. **Protect** – flagged RSUs get no new VNFs; VNFs scale out to healthy RSUs within 2 hops (4 if an attack is nearby).
3. **Move** – running VNFs on a flagged RSU migrate to a healthy RSU; cars re-associate to a healthy RSU in range.

## Folder layout

| Path | What it is |
|---|---|
| `code/` | Python simulator (`config.py` settings, `simulator.py`, `detection.py`, `network.py`, `mobility.py`, `requests_gen.py`, `step10_experiments.py`, `step11_graphs.py`, `run_all.py`) |
| `data/` | Alibaba cluster-trace-v2018 machine/container files and the recorded SUMO mobility trace |
| `rsus.csv`, `links.csv` | 25 RSUs (Powai junctions) and fibre / RSU-cloud links |
| `osm.*`, `powai.sumocfg` | SUMO road network and trips for Powai (OpenStreetMap) |
| `results/` | Experiment results (`step10_all_runs.csv`) and graphs (`results/final/`) |
| `IMAGES/` | Figures used in slides and report |
| `code_backup_with_ratefilter/` | Older code version that still had the per-car rate filter |

## How to run

```bash
pip install numpy pandas matplotlib
cd code
python run_all.py          # all 360 runs (5 attack scenarios + no attack, 4 schemes, 4 attacker levels, 5 seeds), then graphs
python step11_graphs.py    # graphs only
```

Set `QUICK_MODE = True` in `config.py` for a short test run.

## Schemes

| Scheme | Detection | Scale-out | Migration + re-association |
|---|---|---|---|
| S0 no defence | – | – | – |
| S1 detect + exclude | ✓ | – | – |
| S2 detect + scale-out | ✓ | ✓ | – |
| S3 proposed | ✓ | ✓ | ✓ |
