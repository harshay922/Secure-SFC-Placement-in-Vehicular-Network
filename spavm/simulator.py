# =====================================================================================================
# simulator.py - the MAIN TIME-SLOT LOOP of the SPAVM reproduction (plus our Phase 1 and Phase 2 add-ons)
# =====================================================================================================
# WHAT : Builds one whole simulated vehicular edge network (RSUs, vehicles, VNF/SFC catalogs) and then
#        runs it slot by slot. In every slot vehicles move, send SFC requests, the requests are placed
#        (SPVIR, Alg. 1 of Hu et al., IEEE TSC 2025), containers may be migrated (VIMA, Alg. 2, with
#        Lyapunov optimisation), idle containers are deleted, and delay/cost numbers are recorded.
# WHY  : The paper's results are per-slot averages of delay (eq. 14) and cost (eq. 8). This file is the
#        "referee" that calls every algorithm in the right order and writes down what happened.
#        Our thesis adds:
#          PHASE 1 - some RSUs are compromised and tamper with SFCs. Every RSU gets a trust score
#                    (trust.py); untrusted RSUs are blocked (gate), sharing is limited (share_cap),
#                    and quarantined RSUs are emptied (_drain_quarantined).
#          PHASE 2 - some vehicles LIE about their position (VeReMi attacks). Every position report
#                    gets a confidence score, and the serving RSU is chosen using it (ingress_for).
#                    A "follow-me" service migration and a storm guard are also simulated.
# WHO USES IT : The experiment / run scripts and the tests create `Simulator(...)` and call `.run()`,
#        which returns a Metrics object (one row of numbers per slot). SPVIR (spvir.py), VIMA (vima.py)
#        and FollowMe (followme.py) get a reference to this object and read its fields (containers,
#        hop table, gate(), share_cap(), ...), so this class is also the "shared state" of the model.
# =====================================================================================================

import math                                                # built-in maths library (math.dist = distance)
import random                                              # built-in random numbers; random.Random(seed) = own stream
import simpy                                               # SimPy: gives us a SIMULATED clock (see run() below)
import config                                              # config.py: every tunable number lives there
from . import delay_cost as dc                             # "." = this same package (spavm); "as dc" = nickname
from .network import build_network                         # "from X import Y" = bring only the name Y in here
from .workload import (build_vnf_catalog, build_sfc_catalog, build_vehicles,
                       move_vehicles, generate_requests)   # brackets let one import span two lines
from .resources import ResourceManager                     # the ONLY code that changes RSU cpu/mem/bw counters
from .lyapunov import MigrationQueues                      # virtual queues Q_i(t) of eq. 20
from .spvir import SPVIR                                   # Algorithm 1: SFC placement with container reuse
from .vima import VIMA                                     # Algorithm 2: container migration
from .metrics import Metrics                               # collects one "row" of results per slot
from .attacker import Attacker                             # PHASE 1: which RSUs are malicious, when they tamper
from .trust import TrustManager                            # PHASE 1: trust score per RSU
from .mobility_attack import MobilityAttacker              # PHASE 2: vehicles that lie about their position
from .confidence import ConfidenceEngine                   # PHASE 2: confidence score for each position report
from .followme import FollowMe                             # PHASE 2: follow-me service migration (+ storm guard)

# A tuple (round brackets) is a fixed, read-only list. These list the allowed values of the two switches.
TRUST_MODES = ("none", "gate", "quarantine", "oracle")     # PHASE 1: none = plain SPAVM, oracle = knows the truth
MOBILITY_MODES = ("none", "ignore", "conf", "oracle")   # PHASE 2: how the serving RSU is chosen


# "class" defines a new type of object. One Simulator object = one complete simulated run.
class Simulator:
    # __init__ is the CONSTRUCTOR: Python calls it automatically when you write Simulator(...).
    # "self" is the object being built; self.x = ... stores x inside the object so other methods can use it.
    # Arguments written as name=value have DEFAULT values: the caller may leave them out.
    # e.g. Simulator(5, 10, 20) runs plain SPAVM (no attacks, no Phase 2) with seed config.SEED.
    def __init__(self, num_rsus, num_slots, num_vehicles, seed=config.SEED,
                 enable_vima=True, enable_reuse=True,              # switches to turn off parts of SPAVM
                 attack_fraction=0.0, attack_mode=None, trust_mode="none", share_limit=False,   # PHASE 1
                 phase2=False, mobility_mode="none", liar_fraction=0.0, liar_mode=None, storm_guard=False):
        # (last line above = PHASE 2 knobs)
        # assert = "this must be true, otherwise stop with an error" (catches typos like trust_mode="gaet").
        assert trust_mode in TRUST_MODES and mobility_mode in MOBILITY_MODES
        self.share_limit = share_limit                     # PHASE 1 Step 5 on/off (used in share_cap)
        # WHY SEVERAL RANDOM GENERATORS? Each random.Random(seed) is an independent stream of random numbers.
        # self.rng builds the network and the vehicles and generates the requests. Attacks, probes and lies
        # use OTHER generators. So turning attacks or trust on/off never "steals" numbers from self.rng,
        # and every scheme we compare sees EXACTLY the same vehicles and requests -> a fair comparison.
        self.rng = random.Random(seed)                 # single RNG -> full reproducibility
        self.num_slots = num_slots                         # how many time slots run() will simulate
        # Tuple assignment: "a, b = x, y" sets a = x and b = y in one line.
        self.enable_vima, self.enable_reuse = enable_vima, enable_reuse
        # build_network returns 4 things at once; "tuple unpacking" puts each into its own variable:
        # rsus = list of RSU objects, G = graph of RSU links, hop = hop table hop[i][j], side = area size (m).
        self.rsus, self.G, self.hop, self.side = build_network(num_rsus, self.rng)
        self.vnfs = build_vnf_catalog(self.rng)            # the VNF types with their cpu/mem/bw needs
        self.sfcs = build_sfc_catalog(self.rng, self.vnfs) # the SFC types = ordered chains of VNFs
        self.vehicles = build_vehicles(num_vehicles, self.side, self.rng)   # vehicles: position + velocity
        self.rm = ResourceManager(self.rsus)               # reserve()/release() RSU resources (eq. 16-18)
        self.queues = MigrationQueues(num_rsus)            # one virtual queue Q_i per RSU (eq. 20)
        # [] = empty list. containers = every live VNF container in the network; _cid/_rid = id counters.
        # A leading underscore (_cid) is a Python convention for "internal, do not touch from outside".
        self.containers, self._cid, self._rid = [], 0, 0
        # SPVIR(self) hands THIS simulator to the algorithm, so the algorithm can read and change our state.
        self.spvir, self.vima, self.metrics = SPVIR(self), VIMA(self), Metrics()
        # ---- PHASE 1 (separate RNGs so the request stream is IDENTICAL for every scheme) ----
        self.trust_mode = trust_mode                       # "none" / "gate" / "quarantine" / "oracle"
        # The odd multipliers (7919, 104729 are prime numbers) just make seeds that differ from `seed`,
        # so each generator gives a different but still reproducible stream.
        self.srng = random.Random(seed * 7919 + 1)     # attack events, probes
        # Attacker gets two generators: one to PICK the malicious RSUs, one for events (tamper yes/no).
        # Inside brackets a call may continue on the next line; fraction=... are "keyword arguments".
        self.attacker = Attacker(num_rsus, random.Random(seed * 104729 + 3), self.srng,
                                 fraction=attack_fraction, mode=attack_mode)
        self.trust = TrustManager(num_rsus)                # trust T_i and evidence n_i per RSU (trust.py)
        self.trust_log = []                            # per-slot trust of every RSU
        # {key: value for ...} is a DICT COMPREHENSION: builds a dictionary (key -> value lookup table).
        # Here: malicious RSU id -> slot at which we first blocked it (None = "not detected yet").
        self.detect_slot = {r: None for r in self.attacker.malicious}
        # ---- PHASE 2 (own RNGs again, so requests and Phase 1 events stay identical) ----
        self.phase2, self.mobility_mode, self.storm_guard = phase2, mobility_mode, storm_guard
        self.conf_log = []                             # (is_liar, attack type, confidence, parts) per report
        if phase2:                                         # Phase 2 objects exist only when it is switched on
            self.p2rng = random.Random(seed * 15485863 + 5)   # Phase 2 events: GPS noise, lies, radio shadowing
            # MobilityAttacker decides which vehicles lie (own selection RNG) and what they report.
            self.liars = MobilityAttacker(self.vehicles, self.side, random.Random(seed * 32452843 + 7),
                                          self.p2rng, fraction=liar_fraction, mode=liar_mode)
            learning = trust_mode in ("gate", "quarantine")   # True/False: is Phase 1 trust being learned?
            # "A if cond else B" is Python's one-line if/else. self.trust.T (no brackets) passes the METHOD
            # itself, not a result, so the confidence engine can ask for an RSU's trust later: when trust
            # is learned, a report checked by a low-trust RSU counts less.
            self.conf_engine = ConfidenceEngine(self.rsus, len(self.vehicles), self.p2rng,
                                                rsu_weight=(self.trust.T if learning else None))
            self.sessions = FollowMe(self)                 # per-vehicle service that follows the vehicle

    # ------------------------------------------------------------------ PHASE 2 helpers
    # "def" defines a function. Inside a class it is called a METHOD; its first argument is always self.
    def nearest_rsu(self, pos):
        # (math.dist(...), r.rid) for r in self.rsus is a GENERATOR EXPRESSION: it yields one
        # (distance, rsu id) pair per RSU. min() on pairs compares distance first, then id (tie-break).
        # "d, rid = ..." unpacks the smallest pair into two variables.
        d, rid = min((math.dist(pos, (r.x, r.y)), r.rid) for r in self.rsus)
        return rid, d                                      # a tuple: (RSU id, distance in metres)

    def choose_ingress(self, req):
        """Which RSU serves this request (SPVIR Alg. 1 line 1).  Returns (rsu, distance used for the coverage check)."""
        if not self.phase2:                                          # plain SPAVM, exactly as before
            # Nearest RSU to the vehicle's TRUE position (in plain SPAVM nobody lies).
            d0, n_init = min((dc.distance(req.vehicle, r), r.rid) for r in self.rsus)
            return n_init, d0                              # SPVIR then checks d0 <= COVERAGE_R (Alg. 1 l. 2-3)
        # Phase 2: the choice depends on mobility_mode (see ingress_for below).
        return self.ingress_for((req.vehicle.x, req.vehicle.y), req.reported, req.receiver, req.conf)

    def ingress_for(self, true_pos, claim, receiver, conf):
        """PHASE 2 Step 3: pick the serving RSU for a vehicle, depending on the scheme.
        none   : SPAVM as published - nearest RSU to the REPORTED position (trusts the report)
        ignore : never use reports - the RSU that physically received the message
        conf   : ours - if confidence >= P2_CONF_USE, use the report, but only to choose among
                 RSUs that physically heard the vehicle; otherwise the receiving RSU
        oracle : magically knows the true position (best possible)"""
        if receiver is None:                                         # nobody heard the message at all
            return None, None                              # SPVIR turns this into "cloud_uncovered"
        mode = self.mobility_mode                          # short local name, just for readability
        if mode == "oracle":
            return self.nearest_rsu(true_pos)              # cheating upper bound: uses the true position
        if mode == "ignore" or (mode == "conf" and conf < config.P2_CONF_USE):
            return receiver, 0.0                           # distance 0.0: the receiver heard it, so in range
        if mode == "conf":
            # LIST COMPREHENSION: [expr for item in list] builds a new list in one line.
            # hearers() gives (rsu id, signal) pairs; "rid, _" keeps the id and throws the signal away
            # ("_" is the usual name for a value we do not need).
            heard = [rid for rid, _ in self.conf_engine.hearers(true_pos)]
            # Among RSUs that really heard the vehicle, take the one nearest to the CLAIMED position.
            # So a liar can only move itself between RSUs that could physically hear it.
            d, rid = min((math.dist(claim, (self.rsus[r].x, self.rsus[r].y)), r) for r in heard)
            return rid, 0.0
        return self.nearest_rsu(claim)                     # mode "none": blindly trust the reported position

    def _attach_reports(self, t, reqs, row):
        """Every vehicle beacons its position each slot; the controller scores each report (Step 2)."""
        cache = {}                                         # {} = empty dict: vehicle id -> its report this slot
        for v in self.vehicles:                            # for-loop: v takes each vehicle in turn
            claim = self.liars.report(v)                   # the (x, y) the vehicle SAYS it is at (maybe a lie)
            heard = self.conf_engine.hearers((v.x, v.y))   # RSUs that physically receive it (true position)
            receiver = self.conf_engine.pick_receiver(heard)   # RSU that handles the message (None if nobody)
            liar = self.liars.is_liar(v.vid)               # ground truth, used ONLY for measuring, not deciding
            if receiver is None:
                conf, parts = 0.0, None                    # unheard vehicle: zero confidence
            else:
                # score() returns the confidence in [0, 1] and its parts (signal check, speed check, ...).
                conf, parts = self.conf_engine.score(v.vid, (v.x, v.y), claim, heard, receiver)
                # dict.get(key, default) returns "honest" when the vehicle id is not a key of kind.
                self.conf_log.append((liar, self.liars.kind.get(v.vid, "honest"), conf, parts))
                flagged = conf < config.P2_CONF_USE        # True if we would refuse to use this report
                # "A if liar else B" picks which counter to increase; += adds to it.
                row["liar_reports" if liar else "honest_reports"] += 1
                # Adding a bool: True counts as 1 and False as 0 in Python arithmetic.
                row["liar_flagged" if liar else "honest_flagged"] += flagged
            cache[v.vid] = (claim, receiver, conf, liar)   # store a 4-tuple under this vehicle's id
        for req in reqs:
            # Copy the vehicle's report onto each of its requests (unpack the 4-tuple into 4 fields).
            req.reported, req.receiver, req.conf, req.is_liar = cache[req.vehicle.vid]
        self.conf_engine.end_slot()                        # keep this slot's positions for next slot's checks
        self._reports = cache                              # FollowMe.step() reads these later in the slot

    def security_summary(self):
        """Detection time and false blocking, computed over the whole run."""
        rows, mal = self.metrics.rows, self.attacker.malicious   # all per-slot rows, set of malicious ids
        honest = len(self.rsus) - len(mal)                 # len() = number of items
        # Keep only the malicious RSUs that were actually detected (slot is not None).
        det = [s for s in self.detect_slot.values() if s is not None]
        slots = max(len(rows), 1)                          # max(..., 1) avoids dividing by zero
        # dict(name=value, ...) builds a dictionary with those keys; returned to the caller.
        return dict(
            malicious=len(mal),
            # f"..." is an F-STRING: parts in {curly braces} are replaced by their values, e.g. "2/3".
            detected=f"{len(det)}/{len(mal)}",
            # round(x, 2) = 2 decimals. "if det else None": an empty list counts as False -> None.
            avg_detect_slot=round(sum(det) / len(det), 2) if det else None,
            # share of (slot, malicious RSU) pairs where the bad RSU was blocked -> higher is better
            bad_blocked_share=round(sum(r["bad_blocked"] for r in rows) / (slots * len(mal)), 3) if mal else None,
            # share of (slot, honest RSU) pairs where an honest RSU was wrongly blocked -> lower is better
            false_block_share=round(sum(r["good_blocked"] for r in rows) / (slots * honest), 3) if honest else 0.0)

    def share_cap(self, rid):
        """PHASE 1 Step 5: how many SFCs one container on this RSU may serve per slot.
        Without the sharing limit: the fixed SPAVM cap (MAX_SHARE) for everyone.
        With it: less-trusted -> fewer SFCs share it, so one bad container infects fewer chains."""
        # MAX_SHARE may be None (= unlimited); 10 ** 9 (** means "power") stands in for "no limit".
        full = config.MAX_SHARE if config.MAX_SHARE is not None else 10 ** 9
        if not (self.share_limit and self.trust_mode in ("gate", "quarantine")):
            return full                                    # limit off, or no learned trust -> same cap for all
        tr = self.trust                                    # short local name
        if tr.n(rid) < config.N_MIN:
            return config.SHARE_UNKNOWN                 # untested RSU: minimal exposure
        # frac = 0 when trust is exactly at the threshold THETA, 1 when trust is 1 (linear scale).
        frac = (tr.T(rid) - config.TRUST_THETA) / (1.0 - config.TRUST_THETA)
        # Cap grows from 1 (frac = 0) to full (frac = 1); max/min clamp it into [1, full].
        return max(1, min(full, 1 + round(frac * (full - 1))))

    def gate(self, rid):
        """PHASE 1 Step 3: may we use this RSU (reuse, cold start, migration target)?"""
        # Called by SPVIR (reuse + cold start), VIMA (migration target) and FollowMe (service target).
        if self.trust_mode == "none":
            return True                                 # plain SPAVM: trusts everyone
        if self.trust_mode == "oracle":
            return not self.attacker.is_malicious(rid)  # magically knows the bad RSUs
        return self.trust.allowed(rid)                     # gate/quarantine: decided by the learned trust score

    def new_cid(self):
        self._cid += 1                                     # "x += 1" is short for "x = x + 1"
        return self._cid                                   # unique id for a newly created container

    def _assert_hops(self, p):
        # Safety check: every VNF of placement p respects the hop limit mu (Alg. 1 line 7).
        prev = p.n_init                                    # the chain starts at the ingress RSU
        for r in p.rsus:                                   # RSU hosting each VNF, in chain order
            # Hops are counted from the previous VNF ("predecessor", paper text) or from n_init.
            ref = prev if config.HOP_REFERENCE == "predecessor" else p.n_init
            # assert cond, "message": crash with this message if broken (that would be a bug, not a result).
            assert self.hop[ref][r] <= config.MU_HOPS, "hop constraint violated"
            prev = r

    # =================================================================================================
    # _slot(t): EVERYTHING THAT HAPPENS IN ONE TIME SLOT t, in this exact order (matches the code below):
    #   1. Reset loads      - every container's load (SFCs served this slot) goes back to 0.
    #   2. Drain            - PHASE 1 (quarantine mode only): delete all containers on quarantined RSUs.
    #   3. Move vehicles    - each vehicle drives for SLOT_SECONDS and bounces off the area edges.
    #   4. New requests     - each vehicle sends a Poisson(REQUEST_RATE) number of SFC requests.
    #   5. Reports          - PHASE 2 only: every vehicle's position report (maybe a lie) and its
    #                         confidence score are attached to its requests.
    #   6. Placement        - SPVIR (Alg. 1) places each request: reuse a container or cold-start one;
    #                         failures go to the cloud. Transmission delay (eq. 9-10), deployment delay
    #                         and computation cost of new containers are added up.
    #   7. Migration        - VIMA (Alg. 2) may move containers (drift-plus-penalty, eq. 31).
    #                         Only if both VIMA and reuse are enabled.
    #   8. Follow-me        - PHASE 2 only: each vehicle's own service may migrate towards its serving
    #                         RSU (with the storm guard if enabled).
    #   9. Hop delay        - multi-hop delay of each chain, measured on FINAL positions (after step 7).
    #  10. Security         - PHASE 1: tampering (ground truth), end-to-end outcomes, probes, trust
    #                         update, and counting which RSUs are blocked right now.
    #  11. Lyapunov queues  - Q_i(t+1) = max(Q_i + R_i - C, 0)  (eq. 20).
    #  12. Idle deletion    - a container unused for IDLE_LIMIT (= lambda) slots in a row is deleted
    #                         (eq. 4); if reuse is disabled, every container is deleted after its slot.
    #  13. Totals           - cost R_total (eq. 8) and delay D_total (eq. 14) of this slot.
    #  14. Check invariants - used resources match the live containers and never exceed capacity
    #                         (eq. 16-18); then the row is saved into Metrics.
    # =================================================================================================
    def _slot(self, t):
        # Step 1: reset loads. load = number of SFCs a container serves THIS slot (compared with share_cap).
        for c in self.containers:
            c.load = 0
        drained = self._drain_quarantined()                        # PHASE 1: empty quarantined RSUs
        move_vehicles(self.vehicles, self.side)                    # Step 3: vehicles move (updates v.x, v.y)
        # Step 4: Poisson request arrivals. Uses self.rng, so every scheme gets the SAME requests.
        reqs = generate_requests(self.vehicles, self.sfcs, self.rng, self._rid)
        self._rid += len(reqs)                                     # next slot's request ids continue from here
        # "row" = one dictionary of counters for this slot; each starts at 0 and is filled in below.
        # D_* are delays (eq. 9-14), R_* are costs (eq. 5-8); the rest are Phase 1 / Phase 2 measurements.
        row = dict(slot=t, arrived=len(reqs), accepted=0, cloud_uncovered=0, cloud_infeasible=0,
                   reuse=0, cold=0, migrations=0, deleted=0, containers=0,
                   D_tra=0.0, D_hop=0.0, D_dep=0.0, D_mig=0.0,
                   R_comp=0.0, R_mig=0.0, R_keep=0.0, Q_sum=0.0,
                   poisoned=0, poisoned_on_reuse=0, probes=0, lies_caught=0,            # PHASE 1 counters
                   drained=drained, bad_blocked=0, good_blocked=0,
                   honest_reports=0, honest_flagged=0, liar_reports=0, liar_flagged=0,  # PHASE 2 counters
                   misdirected=0, wasted_cold=0, honest_reqs=0, honest_accepted=0,
                   honest_served=0, honest_net_delay=0.0, corrupt_mig=0,
                   sess_mig=0, sess_corrupt=0, sess_cost=0.0, sess_honest=0, sess_access_delay=0.0)
        if self.phase2:
            self._attach_reports(t, reqs, row)                     # PHASE 2: reports + confidence
        # placements = accepted SFC placements; per_req = placement -> its transmission delay (Phase 2 use).
        placements, per_req = [], {}
        for req in reqs:                                           # SFC placement (SPVIR)
            # place() returns 2 values: the Placement (or None if it failed) and "info"
            # (the ingress distance on success, or the failure reason such as "cloud_uncovered").
            p, info = self.spvir.place(req)
            if self.phase2 and not req.is_liar:
                row["honest_reqs"] += 1                            # Phase 2: count honest vehicles' requests...
                row["honest_accepted"] += p is not None            # ...and how many got placed (bool -> 0/1)
            if p is None:
                row[info] += 1                                     # info is the failure reason = a row key
                continue                                           # "continue" = skip to the next request
            self._assert_hops(p)                                   # double-check the hop limit mu
            placements.append(p)                                   # .append adds one item to the end of a list
            # For each (container, is_cold) step, keep the VNF of the cold-started ones.
            cold = [c.vnf for c, is_cold in p.steps if is_cold]
            row["accepted"] += 1
            row["cold"] += len(cold)                               # new containers started (cold start)
            row["reuse"] += len(p.steps) - len(cold)               # all other steps reused an existing container
            d_link = dc.distance(req.vehicle, self.rsus[p.n_init])   # TRUE vehicle-to-RSU distance
            if self.phase2 and d_link > config.COVERAGE_R:
                row["misdirected"] += 1                            # sent to an RSU it cannot reach
                row["wasted_cold"] += len(cold)                    # containers started for nothing
                # id(p) = Python's unique number for object p, used here as a dict key. None = not served.
                per_req[id(p)] = None
            else:
                row["D_tra"] += dc.d_tra(req.size_bits, d_link)    # transmission delay (eq. 9-10)
                per_req[id(p)] = dc.d_tra(req.size_bits, d_link)   # remember it for honest_net_delay below
            row["D_dep"] += dc.d_dep(len(cold))                    # deployment (cold-start) delay (eq. 12)
            row["R_comp"] += dc.r_comp(cold)                       # cost of instantiating new containers (eq. 5)
        # [0.0] * n makes a list of n zeros: migration cost R_i per RSU (stays 0 if VIMA does not run).
        R = [0.0] * len(self.rsus)
        if self.enable_vima and self.enable_reuse:                 # VNF migration (VIMA)
            moves, R = self.vima.run(placements)                   # moves = list of (container, new RSU)
            if self.phase2:
                row["corrupt_mig"] = self.vima.last_corrupt        # migrations that only looked good due to lies
            row["migrations"] = len(moves)
            row["D_mig"] = dc.d_mig(len(moves))                    # migration delay (eq. 13)
            row["R_mig"] = sum(R)                                  # migration cost (eq. 6)
        if self.phase2:                                            # PHASE 2: follow-me service migration
            self.sessions.step(t, row)                             # fills sess_mig, sess_cost, sess_corrupt, ...
        # multi-hop delay measured on FINAL positions (after any migration)
        for p in placements:
            self._assert_hops(p)                                   # migration must not break the hop limit
            row["D_hop"] += dc.d_hop(dc.path_hops(p.n_init, p.rsus, self.hop))   # eq. 11: hops x d_hop
            if self.phase2 and not p.request.is_liar and per_req[id(p)] is not None:
                row["honest_served"] += 1                          # network delay = transmission + hops
                row["honest_net_delay"] += per_req[id(p)] + dc.d_hop(dc.path_hops(p.n_init, p.rsus, self.hop))
        self._security(t, placements, row)                         # PHASE 1: attacks + trust
        self.queues.update(R)                                      # eq. 20
        row["Q_sum"] = sum(self.queues.Q)                          # total queue backlog (sum of Q_i)
        # list(...) makes a COPY: we remove items from self.containers inside the loop, and removing
        # from the list you are looping over directly would make Python skip items.
        for c in list(self.containers):                            # eq. 4 idle deletion
            c.idle = 0 if c.load > 0 else c.idle + 1               # used this slot -> reset, else count up
            if c.idle >= config.IDLE_LIMIT or not self.enable_reuse:   # idle lambda slots (or reuse off)
                self.rm.release(c.rsu, c.vnf.demand())             # give its cpu/mem/bw back to the RSU
                self.containers.remove(c)
                row["deleted"] += 1
        row["containers"] = len(self.containers)                   # containers still alive at slot end
        row["R_keep"] = dc.r_keep(len(self.containers))            # cost of keeping them running (eq. 7)
        row["D_total"] = row["D_tra"] + row["D_hop"] + row["D_dep"] + row["D_mig"]   # eq. 14
        row["R_total"] = row["R_comp"] + row["R_mig"] + row["R_keep"] + row["sess_cost"]   # eq. 8
        # (sess_cost is 0 unless Phase 2 is on, so plain SPAVM's R_total is exactly eq. 8)
        self.rm.check_invariants(self.containers, tag=f"slot {t}")                  # every slot
        self.metrics.add(row)                                      # save this slot's row of results

    # ------------------------------------------------------------------ PHASE 1
    def _drain_quarantined(self):
        """Step 3 (quarantine): remove all containers from quarantined RSUs."""
        # Nothing to do unless we are in quarantine mode AND the quarantined set is non-empty
        # (an empty set counts as False, so "not set()" is True).
        if self.trust_mode != "quarantine" or not self.trust.quarantined:
            return 0
        # List comprehension with a filter: keep only containers sitting on a quarantined RSU.
        gone = [c for c in self.containers if c.rsu in self.trust.quarantined]
        for c in gone:
            self.rm.release(c.rsu, c.vnf.demand())                 # free the RSU's resources
            self.containers.remove(c)                              # the container no longer exists
        return len(gone)                                           # stored in row["drained"]

    def _security(self, t, placements, row):
        att, tr = self.attacker, self.trust                        # short local names
        learning = self.trust_mode in ("gate", "quarantine")       # only these modes update trust scores
        # (a) what actually happened to each SFC (ground truth) + what the check observed (E2)
        for p in placements:
            # set() = empty SET (unordered, no duplicates, very fast "is x in it?" test).
            seen, chain, poisoned, poisoned_reuse = set(), [], False, False
            for c, cold in p.steps:                                # each (container, was it cold-started?)
                if c.cid in seen:
                    continue                                       # same container used twice: count once
                seen.add(c.cid)
                if c.rsu not in chain:
                    chain.append(c.rsu)                            # chain = distinct RSUs this SFC passed
                if att.tampers(c.rsu, t):                          # ground truth: did this RSU corrupt it?
                    poisoned = True
                    poisoned_reuse = poisoned_reuse or not cold    # corrupted by a REUSED container
            # any(...) is True if at least one item is True: a benign fault of an honest RSU on the chain.
            fault = any(att.honest_fault(r) for r in chain)
            # What the end-to-end check SEES: tampering caught with prob. OUTCOME_DETECT, or a benign fault.
            observed_fail = (poisoned and self.srng.random() < config.OUTCOME_DETECT) or fault
            row["poisoned"] += poisoned
            row["poisoned_on_reuse"] += poisoned_reuse
            if learning:
                tr.record_outcome(chain, success=not observed_fail)   # E2 evidence (blame split on failure)
        # (b) verification probes + lie detection (E1, E3)
        if learning:
            n = len(self.rsus)
            k = max(1, round(config.PROBE_FRACTION * n))           # how many RSUs to probe (at least 1)
            # srng.sample(range(n), k) picks k DIFFERENT RSU ids at random (range(n) = 0, 1, ..., n-1).
            for rid in self.srng.sample(range(n), k):
                failed = att.probe_fails(rid, t)                   # E1: test packet came back wrong?
                tr.record_probe(rid, failed, att.self_report_healthy(rid, failed))   # E3: compare with claim
            row["probes"] = k
            before = tr.lies_caught                                # counter before this slot...
            tr.end_slot(use_quarantine=self.trust_mode == "quarantine")   # apply evidence -> new T_i
            row["lies_caught"] = tr.lies_caught - before           # ...so the difference = lies this slot
            self.trust_log.append([tr.T(r) for r in range(n)])     # snapshot of every RSU's trust
        # (c) who is blocked right now?
        for r in range(len(self.rsus)):
            blocked = not self.gate(r)
            if att.is_malicious(r):
                row["bad_blocked"] += blocked                      # correct block (good)
                if blocked and self.detect_slot[r] is None:
                    self.detect_slot[r] = t                        # first time this bad RSU got blocked
            else:
                row["good_blocked"] += blocked                     # false block of an honest RSU (bad)

    def run(self):
        # SimPy provides a SIMULATED clock: env.now starts at 0 and only moves when a process waits.
        env = simpy.Environment()

        # A function defined inside another function. Because it contains "yield" it is a GENERATOR
        # FUNCTION: calling clock(env) does not run it yet; SimPy runs it step by step as a "process".
        def clock(env):
            for t in range(self.num_slots):                        # t = 0, 1, ..., num_slots - 1
                self._slot(t)                                      # do all the work of slot t
                # yield hands control back to SimPy; env.timeout(1) means "wait one slot of simulated time".
                yield env.timeout(1)
        env.process(clock(env))                                    # register the generator as a SimPy process
        env.run()                                                  # run until no process has anything left to do
        return self.metrics                                        # all per-slot rows, for plotting/tables
