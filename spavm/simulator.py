import math
import random
import simpy
import config
from . import delay_cost as dc
from .network import build_network
from .workload import (build_vnf_catalog, build_sfc_catalog, build_vehicles,
                       move_vehicles, generate_requests)
from .resources import ResourceManager
from .lyapunov import MigrationQueues
from .spvir import SPVIR
from .vima import VIMA
from .metrics import Metrics
from .attacker import Attacker
from .trust import TrustManager
from .mobility_attack import MobilityAttacker
from .confidence import ConfidenceEngine
from .followme import FollowMe

TRUST_MODES = ("none", "gate", "quarantine", "oracle")
MOBILITY_MODES = ("none", "ignore", "conf", "oracle")   # PHASE 2: how the serving RSU is chosen


class Simulator:
    def __init__(self, num_rsus, num_slots, num_vehicles, seed=config.SEED,
                 enable_vima=True, enable_reuse=True,
                 attack_fraction=0.0, attack_mode=None, trust_mode="none", share_limit=False,
                 phase2=False, mobility_mode="none", liar_fraction=0.0, liar_mode=None, storm_guard=False):
        assert trust_mode in TRUST_MODES and mobility_mode in MOBILITY_MODES
        self.share_limit = share_limit
        self.rng = random.Random(seed)                 # single RNG -> full reproducibility
        self.num_slots = num_slots
        self.enable_vima, self.enable_reuse = enable_vima, enable_reuse
        self.rsus, self.G, self.hop, self.side = build_network(num_rsus, self.rng)
        self.vnfs = build_vnf_catalog(self.rng)
        self.sfcs = build_sfc_catalog(self.rng, self.vnfs)
        self.vehicles = build_vehicles(num_vehicles, self.side, self.rng)
        self.rm = ResourceManager(self.rsus)
        self.queues = MigrationQueues(num_rsus)
        self.containers, self._cid, self._rid = [], 0, 0
        self.spvir, self.vima, self.metrics = SPVIR(self), VIMA(self), Metrics()
        # ---- PHASE 1 (separate RNGs so the request stream is IDENTICAL for every scheme) ----
        self.trust_mode = trust_mode
        self.srng = random.Random(seed * 7919 + 1)     # attack events, probes
        self.attacker = Attacker(num_rsus, random.Random(seed * 104729 + 3), self.srng,
                                 fraction=attack_fraction, mode=attack_mode)
        self.trust = TrustManager(num_rsus)
        self.trust_log = []                            # per-slot trust of every RSU
        self.detect_slot = {r: None for r in self.attacker.malicious}
        # ---- PHASE 2 (own RNGs again, so requests and Phase 1 events stay identical) ----
        self.phase2, self.mobility_mode, self.storm_guard = phase2, mobility_mode, storm_guard
        self.conf_log = []                             # (is_liar, attack type, confidence, parts) per report
        if phase2:
            self.p2rng = random.Random(seed * 15485863 + 5)
            self.liars = MobilityAttacker(self.vehicles, self.side, random.Random(seed * 32452843 + 7),
                                          self.p2rng, fraction=liar_fraction, mode=liar_mode)
            learning = trust_mode in ("gate", "quarantine")
            self.conf_engine = ConfidenceEngine(self.rsus, len(self.vehicles), self.p2rng,
                                                rsu_weight=(self.trust.T if learning else None))
            self.sessions = FollowMe(self)

    # ------------------------------------------------------------------ PHASE 2 helpers
    def nearest_rsu(self, pos):
        d, rid = min((math.dist(pos, (r.x, r.y)), r.rid) for r in self.rsus)
        return rid, d

    def choose_ingress(self, req):
        """Which RSU serves this request (SPVIR Alg. 1 line 1).  Returns (rsu, distance used for the coverage check)."""
        if not self.phase2:                                          # plain SPAVM, exactly as before
            d0, n_init = min((dc.distance(req.vehicle, r), r.rid) for r in self.rsus)
            return n_init, d0
        return self.ingress_for((req.vehicle.x, req.vehicle.y), req.reported, req.receiver, req.conf)

    def ingress_for(self, true_pos, claim, receiver, conf):
        """PHASE 2 Step 3: pick the serving RSU for a vehicle, depending on the scheme.
        none   : SPAVM as published - nearest RSU to the REPORTED position (trusts the report)
        ignore : never use reports - the RSU that physically received the message
        conf   : ours - if confidence >= P2_CONF_USE, use the report, but only to choose among
                 RSUs that physically heard the vehicle; otherwise the receiving RSU
        oracle : magically knows the true position (best possible)"""
        if receiver is None:                                         # nobody heard the message at all
            return None, None
        mode = self.mobility_mode
        if mode == "oracle":
            return self.nearest_rsu(true_pos)
        if mode == "ignore" or (mode == "conf" and conf < config.P2_CONF_USE):
            return receiver, 0.0
        if mode == "conf":
            heard = [rid for rid, _ in self.conf_engine.hearers(true_pos)]
            d, rid = min((math.dist(claim, (self.rsus[r].x, self.rsus[r].y)), r) for r in heard)
            return rid, 0.0
        return self.nearest_rsu(claim)

    def _attach_reports(self, t, reqs, row):
        """Every vehicle beacons its position each slot; the controller scores each report (Step 2)."""
        cache = {}
        for v in self.vehicles:
            claim = self.liars.report(v)
            heard = self.conf_engine.hearers((v.x, v.y))
            receiver = self.conf_engine.pick_receiver(heard)
            liar = self.liars.is_liar(v.vid)
            if receiver is None:
                conf, parts = 0.0, None
            else:
                conf, parts = self.conf_engine.score(v.vid, (v.x, v.y), claim, heard, receiver)
                self.conf_log.append((liar, self.liars.kind.get(v.vid, "honest"), conf, parts))
                flagged = conf < config.P2_CONF_USE
                row["liar_reports" if liar else "honest_reports"] += 1
                row["liar_flagged" if liar else "honest_flagged"] += flagged
            cache[v.vid] = (claim, receiver, conf, liar)
        for req in reqs:
            req.reported, req.receiver, req.conf, req.is_liar = cache[req.vehicle.vid]
        self.conf_engine.end_slot()
        self._reports = cache

    def security_summary(self):
        """Detection time and false blocking, computed over the whole run."""
        rows, mal = self.metrics.rows, self.attacker.malicious
        honest = len(self.rsus) - len(mal)
        det = [s for s in self.detect_slot.values() if s is not None]
        slots = max(len(rows), 1)
        return dict(
            malicious=len(mal),
            detected=f"{len(det)}/{len(mal)}",
            avg_detect_slot=round(sum(det) / len(det), 2) if det else None,
            bad_blocked_share=round(sum(r["bad_blocked"] for r in rows) / (slots * len(mal)), 3) if mal else None,
            false_block_share=round(sum(r["good_blocked"] for r in rows) / (slots * honest), 3) if honest else 0.0)

    def share_cap(self, rid):
        """PHASE 1 Step 5: how many SFCs one container on this RSU may serve per slot.
        Without the sharing limit: the fixed SPAVM cap (MAX_SHARE) for everyone.
        With it: less-trusted -> fewer SFCs share it, so one bad container infects fewer chains."""
        full = config.MAX_SHARE if config.MAX_SHARE is not None else 10 ** 9
        if not (self.share_limit and self.trust_mode in ("gate", "quarantine")):
            return full
        tr = self.trust
        if tr.n(rid) < config.N_MIN:
            return config.SHARE_UNKNOWN                 # untested RSU: minimal exposure
        frac = (tr.T(rid) - config.TRUST_THETA) / (1.0 - config.TRUST_THETA)
        return max(1, min(full, 1 + round(frac * (full - 1))))

    def gate(self, rid):
        """PHASE 1 Step 3: may we use this RSU (reuse, cold start, migration target)?"""
        if self.trust_mode == "none":
            return True                                 # plain SPAVM: trusts everyone
        if self.trust_mode == "oracle":
            return not self.attacker.is_malicious(rid)  # magically knows the bad RSUs
        return self.trust.allowed(rid)

    def new_cid(self):
        self._cid += 1
        return self._cid

    def _assert_hops(self, p):
        prev = p.n_init
        for r in p.rsus:
            ref = prev if config.HOP_REFERENCE == "predecessor" else p.n_init
            assert self.hop[ref][r] <= config.MU_HOPS, "hop constraint violated"
            prev = r

    def _slot(self, t):
        for c in self.containers:
            c.load = 0
        drained = self._drain_quarantined()                        # PHASE 1: empty quarantined RSUs
        move_vehicles(self.vehicles, self.side)
        reqs = generate_requests(self.vehicles, self.sfcs, self.rng, self._rid)
        self._rid += len(reqs)
        row = dict(slot=t, arrived=len(reqs), accepted=0, cloud_uncovered=0, cloud_infeasible=0,
                   reuse=0, cold=0, migrations=0, deleted=0, containers=0,
                   D_tra=0.0, D_hop=0.0, D_dep=0.0, D_mig=0.0,
                   R_comp=0.0, R_mig=0.0, R_keep=0.0, Q_sum=0.0,
                   poisoned=0, poisoned_on_reuse=0, probes=0, lies_caught=0,
                   drained=drained, bad_blocked=0, good_blocked=0,
                   honest_reports=0, honest_flagged=0, liar_reports=0, liar_flagged=0,
                   misdirected=0, wasted_cold=0, honest_reqs=0, honest_accepted=0,
                   honest_served=0, honest_net_delay=0.0, corrupt_mig=0,
                   sess_mig=0, sess_corrupt=0, sess_cost=0.0, sess_honest=0, sess_access_delay=0.0)
        if self.phase2:
            self._attach_reports(t, reqs, row)                     # PHASE 2: reports + confidence
        placements, per_req = [], {}
        for req in reqs:                                           # SFC placement (SPVIR)
            p, info = self.spvir.place(req)
            if self.phase2 and not req.is_liar:
                row["honest_reqs"] += 1
                row["honest_accepted"] += p is not None
            if p is None:
                row[info] += 1
                continue
            self._assert_hops(p)
            placements.append(p)
            cold = [c.vnf for c, is_cold in p.steps if is_cold]
            row["accepted"] += 1
            row["cold"] += len(cold)
            row["reuse"] += len(p.steps) - len(cold)
            d_link = dc.distance(req.vehicle, self.rsus[p.n_init])   # TRUE vehicle-to-RSU distance
            if self.phase2 and d_link > config.COVERAGE_R:
                row["misdirected"] += 1                            # sent to an RSU it cannot reach
                row["wasted_cold"] += len(cold)                    # containers started for nothing
                per_req[id(p)] = None
            else:
                row["D_tra"] += dc.d_tra(req.size_bits, d_link)
                per_req[id(p)] = dc.d_tra(req.size_bits, d_link)
            row["D_dep"] += dc.d_dep(len(cold))
            row["R_comp"] += dc.r_comp(cold)
        R = [0.0] * len(self.rsus)
        if self.enable_vima and self.enable_reuse:                 # VNF migration (VIMA)
            moves, R = self.vima.run(placements)
            if self.phase2:
                row["corrupt_mig"] = self.vima.last_corrupt
            row["migrations"] = len(moves)
            row["D_mig"] = dc.d_mig(len(moves))
            row["R_mig"] = sum(R)
        if self.phase2:                                            # PHASE 2: follow-me service migration
            self.sessions.step(t, row)
        # multi-hop delay measured on FINAL positions (after any migration)
        for p in placements:
            self._assert_hops(p)
            row["D_hop"] += dc.d_hop(dc.path_hops(p.n_init, p.rsus, self.hop))
            if self.phase2 and not p.request.is_liar and per_req[id(p)] is not None:
                row["honest_served"] += 1                          # network delay = transmission + hops
                row["honest_net_delay"] += per_req[id(p)] + dc.d_hop(dc.path_hops(p.n_init, p.rsus, self.hop))
        self._security(t, placements, row)                         # PHASE 1: attacks + trust
        self.queues.update(R)                                      # eq. 20
        row["Q_sum"] = sum(self.queues.Q)
        for c in list(self.containers):                            # eq. 4 idle deletion
            c.idle = 0 if c.load > 0 else c.idle + 1
            if c.idle >= config.IDLE_LIMIT or not self.enable_reuse:
                self.rm.release(c.rsu, c.vnf.demand())
                self.containers.remove(c)
                row["deleted"] += 1
        row["containers"] = len(self.containers)
        row["R_keep"] = dc.r_keep(len(self.containers))
        row["D_total"] = row["D_tra"] + row["D_hop"] + row["D_dep"] + row["D_mig"]   # eq. 14
        row["R_total"] = row["R_comp"] + row["R_mig"] + row["R_keep"] + row["sess_cost"]   # eq. 8
        self.rm.check_invariants(self.containers, tag=f"slot {t}")                  # every slot
        self.metrics.add(row)

    # ------------------------------------------------------------------ PHASE 1
    def _drain_quarantined(self):
        """Step 3 (quarantine): remove all containers from quarantined RSUs."""
        if self.trust_mode != "quarantine" or not self.trust.quarantined:
            return 0
        gone = [c for c in self.containers if c.rsu in self.trust.quarantined]
        for c in gone:
            self.rm.release(c.rsu, c.vnf.demand())
            self.containers.remove(c)
        return len(gone)

    def _security(self, t, placements, row):
        att, tr = self.attacker, self.trust
        learning = self.trust_mode in ("gate", "quarantine")
        # (a) what actually happened to each SFC (ground truth) + what the check observed (E2)
        for p in placements:
            seen, chain, poisoned, poisoned_reuse = set(), [], False, False
            for c, cold in p.steps:
                if c.cid in seen:
                    continue
                seen.add(c.cid)
                if c.rsu not in chain:
                    chain.append(c.rsu)
                if att.tampers(c.rsu, t):
                    poisoned = True
                    poisoned_reuse = poisoned_reuse or not cold
            fault = any(att.honest_fault(r) for r in chain)
            observed_fail = (poisoned and self.srng.random() < config.OUTCOME_DETECT) or fault
            row["poisoned"] += poisoned
            row["poisoned_on_reuse"] += poisoned_reuse
            if learning:
                tr.record_outcome(chain, success=not observed_fail)
        # (b) verification probes + lie detection (E1, E3)
        if learning:
            n = len(self.rsus)
            k = max(1, round(config.PROBE_FRACTION * n))
            for rid in self.srng.sample(range(n), k):
                failed = att.probe_fails(rid, t)
                tr.record_probe(rid, failed, att.self_report_healthy(rid, failed))
            row["probes"] = k
            before = tr.lies_caught
            tr.end_slot(use_quarantine=self.trust_mode == "quarantine")
            row["lies_caught"] = tr.lies_caught - before
            self.trust_log.append([tr.T(r) for r in range(n)])
        # (c) who is blocked right now?
        for r in range(len(self.rsus)):
            blocked = not self.gate(r)
            if att.is_malicious(r):
                row["bad_blocked"] += blocked
                if blocked and self.detect_slot[r] is None:
                    self.detect_slot[r] = t
            else:
                row["good_blocked"] += blocked

    def run(self):
        env = simpy.Environment()

        def clock(env):
            for t in range(self.num_slots):
                self._slot(t)
                yield env.timeout(1)
        env.process(clock(env))
        env.run()
        return self.metrics
