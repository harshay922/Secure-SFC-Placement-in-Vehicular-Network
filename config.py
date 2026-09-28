"""All tunable parameters.  [P] = from SPAVM paper   [A] = assumption (paper gives no value)."""
SEED = 42

# ---- Scale: Stage A/B/C change ONLY these, never the constraints ----
STAGES = {
    "A": dict(num_rsus=5,  num_slots=10, num_vehicles=20),
    "B": dict(num_rsus=10, num_slots=20, num_vehicles=40),
    "C": dict(num_rsus=20, num_slots=20, num_vehicles=80),
}
DEFAULT_STAGE = "A"

# ---- Network ----
RSU_SPACING = 250.0          # [A] area side = sqrt(N) * spacing (constant RSU density)
LINK_RADIUS = 350.0          # [A] RSUs closer than this are linked (+ MST so graph is connected)
COVERAGE_R = 300.0           # [A] R in Alg.1 line 1
RSU_CPU, RSU_MEM, RSU_BW = 96, 100, 96          # [P] Sec. V-A

# ---- VNFs / SFCs ----
NUM_VNF_TYPES = 20                              # [P]
SFC_LEN_MIN, SFC_LEN_MAX = 2, 6                 # [P]
NUM_SFC_TYPES = 10                              # [A] distinct chains in catalog
CPU_LEVELS = [2, 4, 8, 16, 24, 32]              # [P]
MEM_LEVELS = [1.56, 3.13, 6.25, 9.38, 18.75]    # [P]
BW_LEVELS  = [2, 4, 8, 16, 24, 32]              # [P]
REQUEST_RATE = 0.2           # [P] Poisson lambda per vehicle per slot
VEHICLE_SPEED = (10.0, 30.0) # [A] m/s
SLOT_SECONDS = 5.0           # [A]

# ---- Placement / container lifecycle ----
MU_HOPS = 2                  # [A] mu: max hops between consecutive VNFs
HOP_REFERENCE = "predecessor"  # "predecessor" (paper text) or "init" (Alg.1 line 7) - see README
IDLE_LIMIT = 3               # [A] lambda in eq. 4
MAX_SHARE = 4                # [A] SFCs one container may serve per slot (None = unlimited)

# ---- Delay model (eq. 9-14) ----
W, P_TX, H2, NOISE, THETA = 10e6, 0.2, 1.0, 1e-9, 2.0   # [A] eq. 10
SFC_SIZE_BITS = (0.5e6, 2e6) # [A] L_k range
D_HOP = 0.01                 # [A] d_hop per hop (s)
D_DEP = 0.5                  # [A] d_dep cold start per container (s)
D_MIG = 0.01                 # [A] d_mig per migrated container (s)

# ---- Cost model (eq. 5-8) ----
C_INST = 0.1                 # [A] cc per CPU unit instantiated
C_MIG_PER_HOP = 1.0          # [A] cm
C_KEEP = 0.05                # [A] cs per container per slot

# ---- Lyapunov / VIMA (eq. 20-32, Alg. 2) ----
MIG_BUDGET_C = 1.0           # [A] C: per-RSU migration-cost budget per slot
DELTA = 50.0                 # [A] delta: delay weight in drift-plus-penalty (eq. 31)
VIMA_MAX_CANDIDATES = 10     # [A] containers examined per slot (tractability)

# =====================================================================
# PHASE 1: Trust in reused VNF containers   (all [A] = our design choices)
# =====================================================================
# ---- Step 1: attacker model ----
ATTACK_FRACTION = 0.2        # share of RSUs that are compromised
ATTACK_MODE = "always"       # "always" = always malicious, "onoff" = good/bad in turns
ONOFF_PERIOD = 5             # on-off attacker: 5 slots good, 5 slots bad, ...
P_TAMPER = 0.8               # chance a malicious container tampers with an SFC it serves
P_FAULT = 0.02               # chance an HONEST RSU has a random benign fault (noise)
OUTCOME_DETECT = 0.9         # chance the end-to-end check notices a tampered SFC

# ---- Step 2: trust score ----
GAMMA = 0.9                  # forgetting factor (old evidence fades, EWMA-like)
RHO = 3.0                    # bad evidence counts RHO x more than good ("fast to lose")
LIE_PENALTY = 2.0            # extra bad evidence when a self-report contradicts a probe
PROBE_FRACTION = 0.3         # share of RSUs probed each slot
N_MIN = 3.0                  # evidence needed before trust is believed

# ---- Step 3: trust gate ----
TRUST_THETA = 0.6                 # minimum trust to reuse / place / migrate onto an RSU
TRUST_THETA_Q = 0.3               # below this (with enough evidence) -> quarantine

# ---- Step 5: trust-based sharing limit ----
# A container may serve at most share_cap(T) SFCs per slot:
#   RSU still unknown (little evidence)     -> SHARE_UNKNOWN SFCs
#   trusted RSU                              -> grows from 1 (at T = TRUST_THETA) to MAX_SHARE (at T = 1)
SHARE_UNKNOWN = 1
