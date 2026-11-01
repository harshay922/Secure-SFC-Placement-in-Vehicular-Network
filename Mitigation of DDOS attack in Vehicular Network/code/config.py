# =====================================================================
# config.py  -  ALL settings of the DDoS-mitigation MTP simulation
# ---------------------------------------------------------------------
# Every number used anywhere in the project lives in THIS file only.
# If you want to change an experiment, change it here, nowhere else.
# Lines marked  [CONFIRMED]  = you agreed on 25 Oct 2026.
# Lines marked  [PENDING]    = waiting for your answer (default shown).
# Lines marked  [FROM FILE]  = value read from your input files.
# =====================================================================

import os                                   # 'os' helps us build file paths that work on Windows and Linux

# ---------------------------------------------------------------------
# 1. FILE PATHS
# ---------------------------------------------------------------------
CODE_DIR = os.path.dirname(os.path.abspath(__file__))      # folder where this config.py file sits (the 'code' folder)
PROJECT_DIR = os.path.dirname(CODE_DIR)                    # one level up = "MTP DDOS attack" folder

SUMO_CFG_FILE = os.path.join(PROJECT_DIR, "powai.sumocfg")          # SUMO settings file (map + cars + 1 hour)
NET_FILE = os.path.join(PROJECT_DIR, "osm.net.xml.gz")              # Powai road network from OpenStreetMap
TRIPS_FILE = os.path.join(PROJECT_DIR, "osm.passenger.trips.xml")   # car trips (start and end of each car)
RSU_FILE = os.path.join(PROJECT_DIR, "rsus.csv")                    # 25 RSU positions + CPU/memory (and the CLOUD row)
LINK_FILE = os.path.join(PROJECT_DIR, "links.csv")                  # RSU-RSU fibre links and RSU-CLOUD wireless links
ALIBABA_CONTAINER_FILE = os.path.join(PROJECT_DIR, "data", "container_meta.csv")  # real Alibaba 2018 container sizes (used for VNF CPU/memory)
ALIBABA_MACHINE_FILE = os.path.join(PROJECT_DIR, "data", "machine_meta.csv")      # real Alibaba 2018 machine sizes (RSU = 96 CPU, 100 mem)
RESULTS_DIR = os.path.join(PROJECT_DIR, "results")                  # every output (csv, png) of every step goes here

# ---------------------------------------------------------------------
# 2. SIMULATION TIME AND RANDOM SEEDS
# ---------------------------------------------------------------------
SIM_DURATION_S = 3600          # [CONFIRMED - my choice] 1 hour, same as powai.sumocfg and the old CB-DRL runs
SUMO_STEP_S = 1                # SUMO moves the cars forward 1 second at a time
SUMO_SEED = 42                 # [FROM FILE] same seed as powai.sumocfg, so car movement is the same in every run
SEEDS = [1, 2, 3, 4, 5]        # [CONFIRMED - my choice] 5 random seeds for requests/attacks; results are averaged over them
QUICK_MODE = False             # True = quick test while changing the design: Step 10 runs only seeds 1-2 and
                               #        attacker shares 0, 10, 30% (24 runs instead of 100), into separate files
FRESH_START = True             # True  = Step 10 deletes its old results csv at start and runs everything again
                               # False = keep the old csv and only run the missing runs (resume after a stop)
USE_SUMO_GUI = False           # False = run SUMO without the window (faster). Set True to watch the cars
USE_MOBILITY_TRACE = True      # True = replay the car positions recorded once from SUMO (about 10x faster, same cars)
                               # False = talk to SUMO live in every run (old way)
TRACE_FILE = os.path.join(PROJECT_DIR, "data", "mobility_trace_seed42.csv.gz")   # made by step2b_record_trace.py

# ---------------------------------------------------------------------
# 3. NETWORK  (Section A of the agreed table)
# ---------------------------------------------------------------------
CLOUD_ID = "CLOUD"             # [FROM FILE] name of the single cloud node in rsus.csv and links.csv
RSU_RANGE_M = 300              # [CONFIRMED] a car can talk to an RSU only if it is within 300 m
MAX_OFFLOAD_HOPS = 2           # [CONFIRMED] partial scale-out may use an RSU at most 2 fibre hops away
SCALEOUT_HOPS_UNDER_ATTACK = 4 # [CONFIRMED 25 Oct] if the car's RSU or any RSU within 2 hops is flagged, scale-out may go
                               # up to 4 hops (same as migration) before using the cloud
# RSU CPU = 96 units and memory = 100 units come from rsus.csv (Alibaba machine size, same as SPAVM)
# Cloud CPU = 960 and memory = 1000 also come from rsus.csv
# Hop delays (fibre ~0.0015-0.003 ms) and cloud delay (20 ms) come from links.csv
CLOUD_ONE_WAY_MS = 50.0        # [CONFIRMED 26 Oct] RSU <-> cloud one-way delay (replaces the 20 ms in links.csv):
                               # round trip = 2 x 50 = 100 ms = measured LTE->cloud RTT, mean 85-124 ms
                               # [AdaptiveFog, arXiv 2106.15477, Sec. 4.1, Table 1]. A cloud SFC is then at/above the 100 ms ETSI limit.
                               # (Sensitivity check: 60.0 = 120 ms round trip = measured driving average.)
COUNT_RETURN_PATH = True       # [CONFIRMED 25 Oct] latency = car's RSU -> VNF1 -> ... -> VNFn -> back to the car's RSU
PKT_SIZE_BITS = 12000          # [old CB-DRL step4] one packet = 1500 bytes; transmission delay per link = size / bandwidth

# ---------------------------------------------------------------------
# 3b. DELAY MODEL  (same as old CB-DRL step5: hops + M/M/1 processing)
# ---------------------------------------------------------------------
CPU_CYCLES_PER_CORE = 1000     # [old CB-DRL step5] cycles per second that one CPU core gives a VNF
CYCLES_PER_PKT = 10            # [old CB-DRL step5] cycles one packet needs inside a VNF
# processing delay of one VNF (M/M/1 queue) = 1000 / (mu - packet_rate) ms,  mu = cpu * 1000 / 10 packets/s

# ---------------------------------------------------------------------
# 4. NORMAL SFC REQUESTS  (Section B)
# ---------------------------------------------------------------------
LAMBDA_NORMAL = 0.2            # [CONFIRMED] normal SFC requests per second for the WHOLE map (one random normal car asks)
SFC_LEN_MIN = 2                # [CONFIRMED - SPAVM] smallest SFC has 2 VNFs
SFC_LEN_MAX = 6                # [CONFIRMED - SPAVM] largest SFC has 6 VNFs
NUM_VNF_TYPES = 20             # [CONFIRMED - SPAVM] 20 different VNF types (VNF0 ... VNF19)
HOLD_MIN_S = 30                # [CONFIRMED - old CB-DRL step4] shortest time an SFC keeps its resources
HOLD_MAX_S = 120               # [CONFIRMED - old CB-DRL step4] longest time an SFC keeps its resources
USE_SAFETY_CLASSES = False     # [CONFIRMED 25 Oct] False = no safety / non-safety split for now (all SFCs treated the same)
SAFETY_SHARE = 0.20 if USE_SAFETY_CLASSES else 0.0   # share of normal SFCs tagged "safety" (0 when classes are off)
# VNF CPU and memory: sampled from real Alibaba container_meta rows (cpu_request/100 cores, mem_size)

# ---------------------------------------------------------------------
# 5. ATTACK MODEL  (Section B)
# ---------------------------------------------------------------------
ATTACKER_SHARE = 0.10                      # [CONFIRMED] 10% of cars are attackers in the main run
ATTACKER_SHARE_SWEEP = [0.05, 0.10, 0.20, 0.30]   # [CONFIRMED] attacker shares used for the graphs
LAMBDA_ATTACK = 1.0                        # [CONFIRMED] attack requests per second sent by EACH attacker car
ATTACK_SIZE_FACTOR = 2.0                   # [CONFIRMED] an attack request asks for 2x the CPU and memory of a normal one
ATTACK_HOLD_FACTOR = 3.0                   # [CONFIRMED] an attack request keeps resources 3x longer than a normal one
ATTACK_FAKE_SAFETY_SHARE = 0.50 if USE_SAFETY_CLASSES else 0.0   # attack requests falsely saying "safety" (0 when off)
# ---- attack scenarios [CONFIRMED 25 Oct] ----
#   "A_wide"     : every attacker car floods whatever RSU it is attached to (worst case)
#   "B_targeted" : attacker cars flood ONLY when attached to one of TARGET_RSUS
#   "C_gradual"  : CB-DRL paper model - an RSU with an attacker in range gets hidden CPU load
#                  theta(t) = GAMMA * (1 - exp(-BETA_ATT * t)) of its capacity (slow ramp); it decays when attackers leave
ATTACK_SCENARIO = "A_wide"                 # scenario used by single runs (Steps 5-9)
#   "D_jam"      : traffic-jam zone - JAM_ATTACKERS_PER_RSU standing attackers flood EVERY RSU within
#                  JAM_RADIUS_HOPS of JAM_CENTER for the whole attack window (moving cars do not attack)
#   "A_light"    : same as A_wide but a lighter attacker: LAMBDA_ATTACK_LIGHT requests/s per attacker car
ATTACK_SCENARIOS = ["A_wide", "A_light", "B_targeted", "C_gradual", "D_jam"]   # scenarios run by Step 10
LAMBDA_ATTACK_LIGHT = 0.2                  # [CONFIRMED 25 Oct] A_light: attack requests/s per attacker = the normal rate
JAM_CENTER = "RSU3"                        # [my choice] D: centre of the jam = the hotspot RSU
JAM_RADIUS_HOPS = 2                        # [my choice] D: RSU3 + its 2-hop neighbours (RSU6, 12, 16, 20) are jammed
JAM_ATTACKERS_PER_RSU = 3                  # [CONFIRMED 25 Oct] D: standing attackers per jammed RSU
TARGET_RSUS = ["RSU3", "RSU0", "RSU16"]    # [my choice] B: the 3 busiest RSUs in different areas (hotspot RSU3 + RSU0 + RSU16)
GRADUAL_GAMMA = 0.65                       # [CB-DRL paper] C: maximum attack CPU occupancy = 65% of capacity
GRADUAL_BETA = 0.06                        # [CB-DRL paper] C: growth rate in theta(t) = gamma (1 - e^(-beta t)), per second
# ---- radio flood at the RSU (the attack also fills the RSU's request queue) [CONFIRMED 25 Oct, values = my choice] ----
RSU_INGRESS_PPS = 3000                     # packets/s an RSU can receive and handle (~36 Mbps of 1500-byte packets, C-V2X class)
ATTACK_FLOOD_PPS = 500                     # flood packets/s sent by EACH attacker to its RSU (A, B, D; C = CPU only, as in CB-DRL)
# access delay at the car's RSU (M/M/1):  1000 / (RSU_INGRESS_PPS - load) ms;  load = normal SFC packets + flood packets
# if load >= capacity: a NEW request is dropped with probability 1 - capacity/load, and running SFCs entering there stop
SERVICE_DEADLINE_MS = 100.0                # [ETSI TR 102 638] an SFC FAILS if it is dropped, or its latency ever goes above 100 ms
ATTACK_START_S = 1200                      # [CONFIRMED option 1, 25 Oct] attackers send requests only from t = 1200 s ...
ATTACK_END_S = 2400                        # [CONFIRMED option 1] ... until t = 2400 s (one 20-minute DDoS campaign)
ATTACK_BYPASSES_ORCHESTRATOR = True        # [CONFIRMED] attack requests go straight to the RSU (orchestrator does not know them),
                                           # so they appear as an 'unexplained' resource jump that the adjusted delta detects

# ---------------------------------------------------------------------
# 6. DETECTION - Layer 1  (Section C)  -  CB-DRL adjusted delta, no blockchain
# ---------------------------------------------------------------------
PHI_MIN = 0.05                 # [CONFIRMED] minimum threshold, so idle RSUs do not raise false alarms
REPORT_INTERVAL_S = 2          # [CONFIRMED 26 Oct] EVERY RSU reports every 2 s (regular check), so an attack is seen
                               # even when no new SFC arrives; un-flagged RSUs are ALSO checked before each placement.
                               # Flagged RSUs use the same 2-s reports for the recovery check.
EPISODE_MIN_S = 5              # scoring only: attack episodes shorter than 5 s are ignored (same as before)
RECOVERY_HEALTHY_S = 15        # [CONFIRMED] a flagged RSU is un-flagged after 15 s of only healthy reports (2-s reports)
W_CPU = 0.5                    # [CONFIRMED - old CB-DRL] weight of CPU in the deviation delta
W_MEM = 0.5                    # [CONFIRMED - old CB-DRL] weight of memory in the deviation delta
ALPHA = 2.0                    # [CONFIRMED - old CB-DRL] threshold weight on past volatility sigma
BETA = 0.5                     # [CONFIRMED - old CB-DRL] threshold weight on current load lambda
SIGMA_WINDOW = 20              # [CONFIRMED - old CB-DRL] sigma = volatility over the last 20 verified records
# [CONFIRMED 25 Oct] signed ledger REMOVED: RSUs report their load directly to the orchestrator (no signatures, no chain)

# ---------------------------------------------------------------------
# 7. LAYER 2a - CRITICALITY RESERVE  (Section D)
# ---------------------------------------------------------------------
SAFETY_RESERVE_SHARE = 0.30    # [CONFIRMED] 30% of a flagged RSU's CPU and memory is kept for safety SFCs only
# [CONFIRMED option (a), 25 Oct] a FLAGGED RSU gets NO new VNFs and ALL its running VNFs migrate away.
# Rule: the reserve is active on the un-flagged RSUs within 2 hops of a flagged RSU
#       (the RSUs that receive the moved / offloaded load), while that RSU stays flagged.
# Rule: non-safety SFCs cannot use the reserve; safety SFCs can use reserve + normal pool.
# Rule: if reserve is full -> safety SFC goes to a neighbour RSU first, the cloud only last.

# ---------------------------------------------------------------------
# 8. LAYER 2b - PARTIAL SCALE-OUT  (Section E)
# ---------------------------------------------------------------------
# Placement candidates of every VNF (Step 8):
#   1) the ENTRY RSU (the car's RSU) first - every VNF tries it first, so the chain stays together;
#   2) scale-out ON : only a VNF that does not fit there goes to an un-flagged RSU within 2 fibre hops (nearest first);
#      scale-out OFF: no neighbour RSUs;
#   3) the cloud last.
# Extra latency = fibre hop delays from links.csv.

# ---------------------------------------------------------------------
# 9. LAYER 3 - MIGRATION  (Section F)
# ---------------------------------------------------------------------
REASSOCIATE_ENTRY = True       # [CONFIRMED 25 Oct] part of migration (S3): if a car's RSU is flagged, the car connects to the
                               # nearest UN-flagged RSU still within 300 m of it, so its packets avoid the flooded radio
MAX_MIGRATION_HOPS = 4         # [CONFIRMED 25 Oct] migration after a detected DoS may go up to 4 fibre hops (cloud if none)
MIGRATION_TARGET = "nearest"   # [CONFIRMED] move the VNF to the nearest (fewest hops) un-flagged RSU with free resources
MIGRATION_DELAY_MS = 10.0      # [CONFIRMED] downtime of one VNF migration (much less than the 20 ms cloud link)
# Trigger [option (a)]: as soon as an RSU is flagged, ALL its running VNFs are migrated.
# Order: safety SFCs are migrated first, then non-safety. No cooldown, no heading-aware target (future work).

# ---------------------------------------------------------------------
# 10. SCHEMES TO COMPARE  (Section G)
# ---------------------------------------------------------------------
# [CONFIRMED 25 Oct] reserve removed for now (reserve=False everywhere; the code is kept for later)
SCHEMES = {                                                        # name -> which defence parts are ON
    "S0_no_defense":       dict(detect=False, reserve=False, scaleout=False, migrate=False),  # greedy only
    "S3_proposed":         dict(detect=True,  reserve=False, scaleout=True,  migrate=True),   # + migration + re-association
    "S1_detect_only":     dict(detect=True,  reserve=False, scaleout=False, migrate=False),  # ablation: detection + exclusion
    "S2_detect_scaleout": dict(detect=True,  reserve=False, scaleout=True,  migrate=False),  # ablation: + scale-out, no migration
    "D_detect_only":       dict(detect=True,  reserve=False, scaleout=False, migrate=False),  # old Step 6 test name (same as S1)
    "D_scaleout":          dict(detect=True,  reserve=False, scaleout=True,  migrate=False),  # old Step 8 test name (same as S2)
    "OLD_criticality":     dict(detect=True,  reserve=True,  scaleout=False, migrate=False),  # old Step 7 test (reserve), not used now
}
