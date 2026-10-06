"""All tunable parameters.  [P] = from SPAVM paper   [A] = assumption (paper gives no value)."""
# WHAT THIS FILE DOES: holds every number (setting) the simulator uses, in one place.
# WHY WE NEED IT: if a value must change (e.g. RSU capacity), we change it here once,
#   instead of hunting through many files. It also documents which values come from the
#   SPAVM paper ([P]) and which ones we had to guess ([A]) because the paper does not say.
# WHO USES IT: almost every file does "import config" and then reads e.g. config.RSU_CPU
#   (run.py, spavm/simulator.py, spavm/spvir.py, spavm/vima.py, spavm/delay_cost.py, ...).
# Python note: a line like  NAME = value  creates a variable. ALL-CAPS names are a Python
#   convention meaning "a constant: please do not change this while the program runs".
# Python note: everything after a "#" on a line is a comment; Python ignores it.

SEED = 42  # [A] starting number for the random generator; same seed -> same random run (reproducible)

# ---- Scale: Stage A/B/C change ONLY these, never the constraints ----
# STAGES is a dict (dict = a key -> value lookup table). Key "A" gives the settings of Stage A.
# dict(num_rsus=5, ...) is another way to write {"num_rsus": 5, ...}.
# num_rsus = how many Road Side Units (edge servers), num_slots = how many time slots we simulate,
# num_vehicles = how many cars send requests. Stages grow from small (A, quick test) to big (C).
STAGES = {
    "A": dict(num_rsus=5,  num_slots=10, num_vehicles=20),  # [A] tiny run, good for debugging
    "B": dict(num_rsus=10, num_slots=20, num_vehicles=40),  # [A] medium run (4 vehicles per RSU)
    "C": dict(num_rsus=20, num_slots=20, num_vehicles=80),  # [A] large run (still 4 vehicles per RSU)
}
DEFAULT_STAGE = "A"  # stage used by run.py when you do not pass --stage

# ---- Network ----
RSU_SPACING = 250.0          # [A] area side = sqrt(N) * spacing (constant RSU density)
#                              unit: metres. So more RSUs -> bigger area, same crowding per RSU.
LINK_RADIUS = 350.0          # [A] RSUs closer than this are linked (+ MST so graph is connected)
#                              unit: metres. Two RSUs within 350 m get a wired/wireless link (one "hop").
COVERAGE_R = 300.0           # [A] R in Alg.1 line 1
#                              unit: metres. A vehicle farther than R from every RSU is "uncovered"
#                              and its request goes to the cloud. Paper uses R but gives no number.
RSU_CPU, RSU_MEM, RSU_BW = 96, 100, 96          # [P] Sec. V-A
# Python note: "a, b, c = 1, 2, 3" assigns three variables in one line (tuple unpacking).
# These are the capacities of ONE RSU: CPU units, memory units, bandwidth units.
# They are the caps in constraints 16 (CPU), 17 (memory) and 18 (bandwidth) of the paper.

# ---- VNFs / SFCs ----
# VNF = Virtual Network Function (a small program such as a firewall, running in a container).
# SFC = Service Function Chain = an ordered list of VNFs a request must pass through.
NUM_VNF_TYPES = 20                              # [P] how many different kinds of VNF exist
SFC_LEN_MIN, SFC_LEN_MAX = 2, 6                 # [P] an SFC has between 2 and 6 VNFs (inclusive)
NUM_SFC_TYPES = 10                              # [A] distinct chains in catalog
#                                                 (how many different chains vehicles can ask for;
#                                                 a small number makes reuse of containers possible)
CPU_LEVELS = [2, 4, 8, 16, 24, 32]              # [P] possible CPU demand of one VNF (a list = ordered values)
MEM_LEVELS = [1.56, 3.13, 6.25, 9.38, 18.75]    # [P] possible memory demand of one VNF
BW_LEVELS  = [2, 4, 8, 16, 24, 32]              # [P] possible bandwidth demand of one VNF
REQUEST_RATE = 0.2           # [P] Poisson lambda per vehicle per slot
#                              i.e. on average one vehicle sends 0.2 SFC requests each slot
#                              (one request every 5 slots), with Poisson randomness.
VEHICLE_SPEED = (10.0, 30.0) # [A] m/s
#                              (a, b) is a tuple = a fixed pair. Each vehicle gets a random speed
#                              between 10 and 30 m/s (36-108 km/h), typical urban/highway speeds.
SLOT_SECONDS = 5.0           # [A]
#                              length of one time slot in seconds; vehicles move speed*5 s per slot.

# ---- Placement / container lifecycle ----
MU_HOPS = 2                  # [A] mu: max hops between consecutive VNFs
#                              The paper limits how far apart (in hops) two consecutive VNFs of one
#                              chain may be placed, but gives no number; we assume 2 hops.
HOP_REFERENCE = "predecessor"  # "predecessor" (paper text) or "init" (Alg.1 line 7) - see README
#                              The mu-hop limit is measured from the previous VNF ("predecessor")
#                              or from the ingress RSU n_init ("init"). The paper is ambiguous.
IDLE_LIMIT = 3               # [A] lambda in eq. 4
#                              A container unused for 3 slots in a row is deleted (idle deletion),
#                              which frees RSU resources and stops the keep cost (eq. 7).
MAX_SHARE = 4                # [A] SFCs one container may serve per slot (None = unlimited)
#                              Reuse limit: one running container can serve at most 4 SFCs per slot.
#                              None is Python's "no value" marker.

# ---- Delay model (eq. 9-14) ----
W, P_TX, H2, NOISE, THETA = 10e6, 0.2, 1.0, 1e-9, 2.0   # [A] eq. 10
# Used in eq. 10 (Shannon rate): rate = W * log2(1 + P_TX*H2 / (NOISE * d^THETA)).
#   W     = channel bandwidth, 10e6 = 10 MHz (10e6 is scientific notation for 10 * 10^6)
#   P_TX  = vehicle transmit power, 0.2 W
#   H2    = channel gain |h|^2, set to 1 (no fading)
#   NOISE = noise power, 1e-9 W
#   THETA = path-loss exponent, 2 (free-space); signal weakens with distance d^2
# The paper names these symbols but gives no values, so these are common textbook choices.
SFC_SIZE_BITS = (0.5e6, 2e6) # [A] L_k range
#                              data size of one request: random between 0.5 and 2 megabits (eq. 9).
D_HOP = 0.01                 # [A] d_hop per hop (s)
#                              extra delay each time data crosses one RSU-to-RSU link (eq. 11).
D_DEP = 0.5                  # [A] d_dep cold start per container (s)
#                              time to start a NEW container (cold start, eq. 3 and eq. 12).
#                              Much larger than D_HOP: this is why reusing a warm container helps.
D_MIG = 0.01                 # [A] d_mig per migrated container (s)
#                              service interruption when a container is moved (eq. 1 and eq. 13).

# ---- Cost model (eq. 5-8) ----
C_INST = 0.1                 # [A] cc per CPU unit instantiated
#                              cost to create a container = 0.1 * its CPU demand (eq. 5).
C_MIG_PER_HOP = 1.0          # [A] cm
#                              cost to migrate a container = 1.0 per hop moved (eq. 6).
C_KEEP = 0.05                # [A] cs per container per slot
#                              cost to keep one container alive for one slot (eq. 7).
#                              Small, so keeping a warm container is cheaper than recreating it.

# ---- Lyapunov / VIMA (eq. 20-32, Alg. 2) ----
MIG_BUDGET_C = 1.0           # [A] C: per-RSU migration-cost budget per slot
#                              In eq. 20 the virtual queue Q_i grows by (migration cost - C) each slot.
#                              If an RSU keeps spending more than C, its queue grows and VIMA
#                              avoids more migrations there. This keeps long-run migration cost bounded.
DELTA = 50.0                 # [A] delta: delay weight in drift-plus-penalty (eq. 31)
#                              Bigger DELTA -> VIMA cares more about lowering delay,
#                              less about staying inside the migration budget.
VIMA_MAX_CANDIDATES = 10     # [A] containers examined per slot (tractability)
#                              VIMA only tries to migrate at most 10 containers per slot so the
#                              simulation stays fast; the paper does not say how many.

# =====================================================================
# PHASE 1: Trust in reused VNF containers   (all [A] = our design choices)
# =====================================================================
# (Phase 1 is OUR extension beyond SPAVM: some RSUs may be malicious, so reusing their
#  containers is risky. None of these values are from the SPAVM paper.)
# ---- Step 1: attacker model ----
ATTACK_FRACTION = 0.2        # share of RSUs that are compromised
#                              0.2 = 20% of RSUs are bad.
ATTACK_MODE = "always"       # "always" = always malicious, "onoff" = good/bad in turns
ONOFF_PERIOD = 5             # on-off attacker: 5 slots good, 5 slots bad, ...
P_TAMPER = 0.8               # chance a malicious container tampers with an SFC it serves
#                              probability between 0 and 1; 0.8 = 80% of the time.
P_FAULT = 0.02               # chance an HONEST RSU has a random benign fault (noise)
#                              so honest RSUs sometimes look bad too (realistic false alarms).
OUTCOME_DETECT = 0.9         # chance the end-to-end check notices a tampered SFC

# ---- Step 2: trust score ----
GAMMA = 0.9                  # forgetting factor (old evidence fades, EWMA-like)
#                              each slot old evidence is multiplied by 0.9, so recent behaviour matters more.
RHO = 3.0                    # bad evidence counts RHO x more than good ("fast to lose")
#                              trust is slow to earn and fast to lose.
LIE_PENALTY = 2.0            # extra bad evidence when a self-report contradicts a probe
PROBE_FRACTION = 0.3         # share of RSUs probed each slot
#                              30% of RSUs get an independent test each slot.
N_MIN = 3.0                  # evidence needed before trust is believed
#                              below this amount of evidence, the RSU is treated as "unknown".

# ---- Step 3: trust gate ----
TRUST_THETA = 0.6                 # minimum trust to reuse / place / migrate onto an RSU
#                                   trust is a number from 0 (bad) to 1 (good).
TRUST_THETA_Q = 0.3               # below this (with enough evidence) -> quarantine
#                                   quarantine = the RSU is not used at all.

# ---- Step 5: trust-based sharing limit ----
# A container may serve at most share_cap(T) SFCs per slot:
#   RSU still unknown (little evidence)     -> SHARE_UNKNOWN SFCs
#   trusted RSU                              -> grows from 1 (at T = TRUST_THETA) to MAX_SHARE (at T = 1)
SHARE_UNKNOWN = 1  # an unknown RSU's container may serve only 1 SFC per slot (limits damage if bad)

# =====================================================================
# PHASE 2: Secure VNF migration under falsified mobility reports
# All names start with P2_ so they can never overwrite a SPAVM / Phase 1 setting.
# =====================================================================
# (Phase 2 is also OUR extension: some vehicles lie about where they are, which could
#  trick the system into migrating services to the wrong RSU.)
# ---- Step 1: mobility attacker (attack types and parameters from the VeReMi dataset paper) ----
P2_LIAR_FRACTION = 0.2        # share of vehicles that falsify their reported position
P2_LIAR_MODE = "mixed"        # "const_pos" | "const_offset" | "random_pos" | "random_offset" | "eventual_stop" | "mixed"
#                               which kind of lie liars tell; "mixed" = each liar gets one of the five types.
P2_CONST_OFFSET = (250.0, -150.0)   # [VeReMi] constant offset attack, metres
#                                     liar always reports true position + (250 m in x, -150 m in y).
P2_RANDOM_OFFSET = 300.0      # [VeReMi] random offset drawn from [-300, 300] m in x and y
P2_STOP_STEP = 0.025          # [VeReMi] eventual stop: probability of freezing grows by this each report
#                               the liar at some point keeps reporting the same (old) position.
P2_GPS_NOISE_M = 5.0          # honest GPS error (std dev, metres)
#                               honest vehicles are also a little wrong, like real GPS.
P2_GPS_FAULT_P = 0.02         # chance an honest vehicle's GPS is badly wrong in one slot
P2_GPS_FAULT_M = 150.0        # size of such an honest GPS fault, metres

# ---- Step 2: confidence score ----
P2_SHADOW_DB = 4.0            # random signal fluctuation (log-normal shadowing), dB
#                               dB = decibels, a log scale for signal strength.
P2_RSSI_TOL_DB = 8.0          # tolerance when comparing measured vs expected signal, dB
#                               RSSI = received signal strength; if the measured signal does not
#                               match the claimed distance by more than this, the claim is doubtful.
P2_V_MAX = 40.0               # fastest plausible vehicle speed, m/s
#                               a claimed jump that implies > 40 m/s (144 km/h) is suspicious.
P2_SPEED_TOL = 10.0           # softness of the speed check, m/s
P2_CONF_USE = 0.5             # below this confidence, the reported position is not used

# ---- Step 3b: follow-me service migration (each vehicle's service follows the vehicle) ----
P2_FOLLOW_HOPS = 1            # migrate a vehicle's service when it is more than 1 hop from the vehicle's RSU

# ---- Step 4: migration storm guard ----
P2_STABLE_SLOTS = 2           # only migrate if the new target RSU is the same for 2 slots in a row
#                               stops a service from bouncing back and forth every slot.
