# =====================================================================
# simulator.py  -  the main simulation engine (grows step by step)
# ---------------------------------------------------------------------
# Step 4: live SUMO + normal requests + GREEDY placement, release at end.
# Step 5 (this version adds): ATTACK.
#   - ATTACKER_SHARE of cars are attackers (chosen when the car first appears).
#   - Each attacker sends LAMBDA_ATTACK requests/s straight to its RSU.
#     The orchestrator does NOT know about them ("hidden load").
#   - MEMORY is a hard limit: an attack request is admitted only if the RSU's memory
#     is physically free (an RSU cannot start a container without memory).
#   - CPU is SHARED: attack load can push total CPU demand above 96 cores. Then every VNF on
#     that RSU only gets a fraction f = capacity / demand of its CPU, so it runs slower.
#     If a VNF becomes slower than its packet rate (mu_eff <= packet rate) the SFC is DISRUPTED that second.
# Step 6 adds: detection (RSU load reports, no ledger); flagged RSUs excluded from new placements.
# Attack scenarios: A_wide / B_targeted (attack requests) and C_gradual (CB-DRL theta(t) CPU occupancy).
# Step 7 adds: criticality RESERVE on the un-flagged RSUs within 2 hops of a flagged RSU.
# Step 8 adds: candidates = entry RSU first, then (scale-out) un-flagged RSUs within 2 hops, cloud last.
# Step 9 adds: MIGRATION - as soon as an RSU is flagged, ALL its running VNFs move (safety SFCs first)
#              to the nearest un-flagged RSU with enough resources (cloud if none), 10 ms downtime per VNF.
#
#     sim = Simulation(scheme="S0_no_defense", seed=1, attacker_share=0.10)
#     summary = sim.run()
# =====================================================================

import math                                     # infinity, isfinite
import numpy as np                              # averages, random numbers
import config as cfg                            # settings
from network import load_network                # Step 1
from mobility import Mobility                   # Step 2
from requests_gen import load_alibaba_vnfs, RequestGenerator   # Step 3 (+ attack requests, Step 5)
from detection import Detector, DET_KEYS        # Step 6: adjusted-delta detection

_VNF_POOL = None                                # Alibaba data is big: load it once and reuse it for every run


def vnf_pool():
    global _VNF_POOL                            # use the variable defined outside this function
    if _VNF_POOL is None:                       # first call -> read the csv
        _VNF_POOL = load_alibaba_vnfs()
    return _VNF_POOL                            # (cpu array, mem array)


class Simulation:
    def __init__(self, scheme="S0_no_defense", seed=1, attacker_share=cfg.ATTACKER_SHARE, scenario=cfg.ATTACK_SCENARIO):
        self.scenario = scenario                                # attack scenario: A_wide / B_targeted / C_gradual
        self.scheme = scheme                                    # which scheme (see config.SCHEMES)
        self.opts = cfg.SCHEMES[scheme]                         # dict: detect / reserve / scaleout / migrate on or off
        self.seed = seed                                        # random seed
        self.attacker_share = attacker_share                    # fraction of cars that are attackers (0 = no attack)
        self.net = load_network()                               # 25 RSUs + cloud
        self.nodes = list(self.net.rsus) + [cfg.CLOUD_ID]       # every node that can host a VNF
        self.cap_cpu = {r: v["cpu"] for r, v in self.net.rsus.items()}   # total CPU of each RSU
        self.cap_mem = {r: v["mem"] for r, v in self.net.rsus.items()}   # total memory of each RSU
        self.cap_cpu[cfg.CLOUD_ID] = self.net.cloud["cpu"]      # cloud CPU
        self.cap_mem[cfg.CLOUD_ID] = self.net.cloud["mem"]      # cloud memory
        self.used_cpu = {n: 0.0 for n in self.nodes}            # CPU of VNFs placed by the orchestrator (KNOWN load)
        self.used_mem = {n: 0.0 for n in self.nodes}            # memory of VNFs placed by the orchestrator
        self.att_cpu = {n: 0.0 for n in self.nodes}             # CPU taken by attack requests (HIDDEN load)
        self.att_mem = {n: 0.0 for n in self.nodes}             # memory taken by attack requests
        cpu, mem = vnf_pool()                                   # real Alibaba VNF sizes
        self.gen = RequestGenerator(seed, cpu, mem, self.net)            # normal requests (same as Step 4 for the same seed)
        self.att_gen = RequestGenerator(seed + 1000, cpu, mem, self.net) # attack requests: separate random stream
        self.att_rng = np.random.default_rng(seed + 2000)       # decides which cars are attackers
        self.is_attacker = {}                                   # car -> True/False (decided once per car)
        self.running = []                                       # normal SFCs placed and still holding resources
        self.att_running = []                                   # admitted attack requests still holding resources
        self.log = []                                           # one record per normal request (for results)
        self.att_sent = 0                                       # attack requests sent
        self.att_admitted = 0                                   # attack requests admitted by an RSU
        self.util_timeline = []                                 # per second: [t, known CPU % of each RSU ...]
        self.att_timeline = []                                  # per second: [t, attack CPU % of each RSU ...]
        self.lat_timeline = []                                  # per second: (t, average latency of running SFCs, disrupted SFCs)
        self.det = Detector(self) if self.opts["detect"] else None   # Step 6: detector only if the scheme uses it
        self.reserve_skips = 0                                  # Step 7: times a NON-safety VNF was refused by a reserve
        self.att_fake_into_reserve = 0                          # Step 7: fake-safety attack requests that got into a reserve
        self.reserve_timeline = []                              # Step 7: (t, number of RSUs with an active reserve)
        self.flood_pps = {r: 0.0 for r in self.net.rsus}        # radio flood packets/s arriving at each RSU (this second)
        self.ingress_pps = {r: 0.0 for r in self.net.rsus}      # normal SFC packets/s entering at each RSU (this second)
        self.access_rng = np.random.default_rng(seed + 3000)    # random drops when an RSU's queue is full
        self.dropped = 0                                        # new requests dropped at a flooded RSU
        self.reassociations = 0                                 # times a car moved its SFC entry to another RSU
        self.migrations = 0                                     # Step 9: VNFs migrated
        self.migrations_to_cloud = 0                            # Step 9: ... of which to the cloud (no RSU had room)
        self.migration_failed = 0                               # Step 9: VNFs that could not move anywhere (stay)

    # ---------------- small helpers ----------------
    def phys_free_mem(self, n):                                 # memory REALLY free (placed VNFs + attack counted)
        return self.cap_mem[n] - self.used_mem[n] - self.att_mem[n]

    def cpu_share(self, n):                                     # f = fraction of its CPU that each VNF on node n really gets
        demand = self.used_cpu[n] + self.att_cpu[n]             # total CPU asked on this node
        return 1.0 if demand <= self.cap_cpu[n] else self.cap_cpu[n] / demand   # 1 if not overloaded

    def reserve_zone(self):
        """Step 7: un-flagged RSUs within MAX_OFFLOAD_HOPS (2) of a flagged RSU = RSUs that receive the moved load.
        On these RSUs SAFETY_RESERVE_SHARE (30%) of CPU and memory is kept for safety SFCs only."""
        if not self.opts["reserve"] or self.det is None or not self.det.flagged:
            return set()                                        # no reserve anywhere
        key = frozenset(self.det.flagged)                       # the zone only changes when the flagged set changes
        if getattr(self, "_zone_key", None) == key:             # same flagged RSUs as last time -> reuse (faster)
            return self._zone
        zone = set()
        for f in self.det.flagged:                              # every flagged RSU ...
            for nb, h, d in self.net.neighbours_within(f, cfg.MAX_OFFLOAD_HOPS):   # ... its RSUs within 2 hops
                if nb not in self.det.flagged:
                    zone.add(nb)
        self._zone_key, self._zone = key, zone                  # remember for next time
        return zone

    def limit(self, n, safety, zone):
        """How much of node n's capacity this request may fill: 100% for safety (or no reserve), 70% otherwise."""
        if n in zone and not safety:                            # reserve active and this is NOT a safety request
            return 1.0 - cfg.SAFETY_RESERVE_SHARE               # only the normal pool (70%)
        return 1.0                                              # whole capacity

    def fits(self, n, cpu, mem, safety=False, zone=frozenset()):
        """Orchestrator's check: enough CPU in ITS OWN books (it does not know the attack load),
        AND the RSU accepts the container only if memory is physically free.
        Step 7: a non-safety VNF on a reserve RSU may only use 70% of CPU and memory."""
        k = self.limit(n, safety, zone)                         # 1.0 or 0.7
        cpu_ok = self.used_cpu[n] + cpu <= k * self.cap_cpu[n]
        mem_ok = self.used_mem[n] + self.att_mem[n] + mem <= k * self.cap_mem[n]
        if not (cpu_ok and mem_ok) and k < 1.0 and self.fits(n, cpu, mem, True, zone):
            self.reserve_skips += 1                             # it WOULD fit without the reserve -> refused by the reserve
        return cpu_ok and mem_ok

    def allowed_rsus(self, req):                                # RSUs the placement may use
        if self.det is None:                                    # no detection -> every RSU
            return list(self.net.rsus)
        return [r for r in self.net.rsus if r not in self.det.flagged]   # Step 6: flagged RSUs are excluded

    # ---------------- greedy placement (same rule as old CB-DRL step5) ----------------
    def candidates(self, req, allowed):
        """Step 8: RSUs a VNF of this request may use, in the order they are tried."""
        entry = req["entry"]
        if entry == cfg.CLOUD_ID:                               # car outside every RSU range -> cloud only
            return []
        cand = [entry] if entry in allowed else []              # 1) the car's own RSU (if not flagged)
        if self.opts["scaleout"]:                               # 2) scale-out: RSUs within 2 hops, nearest first
            hops = cfg.MAX_OFFLOAD_HOPS
            if self.det is not None and (entry in self.det.flagged or any(           # attack near this car ->
                    nb in self.det.flagged for nb, h, d in self.net.neighbours_within(entry, cfg.MAX_OFFLOAD_HOPS))):
                hops = cfg.SCALEOUT_HOPS_UNDER_ATTACK                                # look up to 4 hops
            cand += [nb for nb, h, d in self.net.neighbours_within(entry, hops) if nb in allowed]
        return cand

    def choose_node(self, cand, cpu, mem, safety=False, zone=frozenset()):
        """First candidate RSU (entry first, then nearest neighbours) with enough CPU + memory; cloud last.
        (So a safety VNF whose reserve is full goes to a neighbour RSU first and the cloud last.)"""
        for n in cand:                                          # in the order given by candidates()
            if self.fits(n, cpu, mem, safety, zone):
                return n                                        # first one that fits wins
        if self.fits(cfg.CLOUD_ID, cpu, mem):                   # no RSU fits -> try the cloud
            return cfg.CLOUD_ID
        return None                                             # nothing fits

    def place(self, req):
        """Place every VNF of the SFC in order. If one VNF fails, the whole SFC is rejected."""
        cand = self.candidates(req, self.allowed_rsus(req))     # Step 8: entry RSU, (neighbours), in order
        zone = self.reserve_zone()                              # Step 7: RSUs with an active safety reserve
        nodes = []
        for i in range(len(req["chain"])):                      # VNF by VNF
            n = self.choose_node(cand, req["cpu"][i], req["mem"][i], req["safety"], zone)
            if n is None:
                self.release(req, nodes)                        # undo earlier VNFs of this SFC
                return None
            self.used_cpu[n] += req["cpu"][i]                   # take the resources
            self.used_mem[n] += req["mem"][i]
            nodes.append(n)
        return nodes

    def release(self, req, nodes):                              # give the resources of a normal SFC back
        for i, n in enumerate(nodes):
            self.used_cpu[n] -= req["cpu"][i]
            self.used_mem[n] -= req["mem"][i]

    # ---------------- end-to-end delay ----------------
    def access_delay_ms(self, rsu):
        """Queueing delay of the car's packets at its RSU's radio/ingress (M/M/1). inf if the queue is full."""
        if rsu == cfg.CLOUD_ID:                                 # car out of range uses cellular -> no RSU queue
            return 0.0
        load = self.ingress_pps[rsu] + self.flood_pps[rsu]      # packets/s arriving at this RSU
        if load >= cfg.RSU_INGRESS_PPS:
            return math.inf
        return 1000.0 / (cfg.RSU_INGRESS_PPS - load)            # ms

    def update_flood(self, t, cars, attackers):
        """Radio flood this second: every attacker sends ATTACK_FLOOD_PPS packets to its RSU (scenario rules apply)."""
        self.flood_pps = {r: 0.0 for r in self.net.rsus}
        if not (cfg.ATTACK_START_S <= t < cfg.ATTACK_END_S) or self.scenario == "C_gradual":
            return                                              # outside the window, or C (CPU-only CB-DRL model)
        if self.scenario == "D_jam":                            # standing attackers in the jam zone
            zone = [cfg.JAM_CENTER] + [b for b, h, d in self.net.neighbours_within(cfg.JAM_CENTER, cfg.JAM_RADIUS_HOPS)]
            for r in zone:
                self.add_flood(r, cfg.ATTACK_FLOOD_PPS, cfg.JAM_ATTACKERS_PER_RSU)
            return
        for c in attackers:                                     # A / B: moving attacker cars
            r = cars[c][2]
            if r is None or (self.scenario == "B_targeted" and r not in cfg.TARGET_RSUS):
                continue
            self.add_flood(r, cfg.ATTACK_FLOOD_PPS)

    def add_flood(self, r, pps_per_sender, senders=1):
        """Flood from 'senders' attackers at RSU r: their junk packets are added to the RSU's radio load."""
        self.flood_pps[r] += pps_per_sender * senders

    def reassoc_on(self):                                       # is entry re-association active in this scheme?
        return cfg.REASSOCIATE_ENTRY and self.opts["migrate"] and self.det is not None

    def better_entry(self, car, cars):
        """Nearest UN-flagged RSU within 300 m of the car now (None if there is none)."""
        if car not in cars:                                     # car already left the map
            return None
        x, y, _ = cars[car]
        for rsu, d in self.net.rsus_in_range(x, y):             # in-range RSUs, nearest first
            if rsu not in self.det.flagged:
                return rsu
        return None

    def reassociate_running(self, cars):
        """Running SFCs whose entry RSU is flagged: the car connects to another (healthy) RSU in range."""
        for s in self.running:
            e = s["req"]["entry"]
            if e in self.det.flagged:
                new = self.better_entry(s["req"]["car_id"], cars)
                if new is not None:
                    s["req"]["entry"] = new
                    self.reassociations += 1

    def update_ingress(self):
        """Normal packets/s entering each RSU = packet rates of the running SFCs whose car is attached there."""
        self.ingress_pps = {r: 0.0 for r in self.net.rsus}
        for s in self.running:
            e = s["req"]["entry"]
            if e != cfg.CLOUD_ID:
                self.ingress_pps[e] += s["req"]["pkt_rate_pps"]

    def latency_ms(self, req, nodes):
        """Access delay at the car's RSU + network delay of all hops + M/M/1 processing of every VNF
        (using the CPU each VNF REALLY gets now)."""
        acc = self.access_delay_ms(req["entry"])                # flooded RSU -> long or infinite queue
        if not math.isfinite(acc):
            return math.inf
        path = [req["entry"]] + nodes                           # entry -> VNF1 -> VNF2 -> ...
        if cfg.COUNT_RETURN_PATH:
            path = path + [req["entry"]]                        # ... -> back to the car's RSU (round trip)
        net_d = sum(self.net.delay_ms(a, b) for a, b in zip(path[:-1], path[1:]))
        proc = 0.0
        for c, n in zip(req["cpu"], nodes):                     # every VNF and its node
            mu = c * self.cpu_share(n) * cfg.CPU_CYCLES_PER_CORE / cfg.CYCLES_PER_PKT   # packets/s it can serve now
            if mu <= req["pkt_rate_pps"]:                       # too slow -> queue grows forever -> service stops
                return math.inf
            proc += 1000.0 / (mu - req["pkt_rate_pps"])         # M/M/1 time in system, in ms
        return acc + net_d + proc

    # ---------------- Step 9: migration ----------------
    def after_check(self):
        """Called after every detection check: empty the RSUs that were just flagged (if the scheme migrates)."""
        if self.det is None:
            return
        new, self.det.newly_flagged = self.det.newly_flagged, []      # take the list and empty it
        if self.opts["migrate"]:
            for rsu in new:
                self.migrate_all_from(rsu)

    def migrate_all_from(self, bad):
        """Move every VNF on the flagged RSU 'bad' to the nearest un-flagged RSU that fits (cloud if none).
        Safety SFCs are moved first, so they get the best targets."""
        affected = [s for s in self.running if bad in s["nodes"]]       # SFCs with at least one VNF there
        affected.sort(key=lambda s: not s["req"]["safety"])             # safety (True) first
        zone = self.reserve_zone()                                      # reserve rules still apply (S3)
        targets = [b for b, h, d in self.net.neighbours_within(bad, cfg.MAX_MIGRATION_HOPS)
                   if b not in self.det.flagged]                        # un-flagged RSUs within 4 hops, nearest first
        for s in affected:
            req = s["req"]
            for i, n in enumerate(s["nodes"]):
                if n != bad:                                            # only VNFs on the flagged RSU move
                    continue
                c, m = req["cpu"][i], req["mem"][i]
                self.used_cpu[bad] -= c; self.used_mem[bad] -= m        # free them on the bad RSU first
                dest = next((r for r in targets if self.fits(r, c, m, req["safety"], zone)), None)
                if dest is None and self.fits(cfg.CLOUD_ID, c, m):      # no RSU has room -> cloud
                    dest = cfg.CLOUD_ID
                if dest is None:                                        # nowhere at all -> stays (rare)
                    self.used_cpu[bad] += c; self.used_mem[bad] += m
                    self.migration_failed += 1
                    continue
                self.used_cpu[dest] += c; self.used_mem[dest] += m      # take resources on the new node
                s["nodes"][i] = dest
                s["mig_ms"] = s.get("mig_ms", 0.0) + cfg.MIGRATION_DELAY_MS   # 10 ms service downtime
                self.migrations += 1
                self.migrations_to_cloud += dest == cfg.CLOUD_ID

    # ---------------- attack part ----------------
    def update_attackers(self, cars):                           # decide once for every NEW car if it is an attacker
        for car in cars:
            if car not in self.is_attacker:
                self.is_attacker[car] = bool(self.att_rng.random() < self.attacker_share)

    def admit_attack(self, req):
        """The target RSU starts the attack request only if its memory is physically free (no orchestrator involved)."""
        n = req["entry"]                                        # attacker's own RSU
        mem, cpu = sum(req["mem"]), sum(req["cpu"])             # whole request on that one RSU
        self.att_sent += 1
        zone = self.reserve_zone()                              # Step 7: the RSU itself enforces its reserve too
        k = self.limit(n, req["safety"], zone)                  # fake "safety" attack requests may enter the reserve
        if self.used_mem[n] + self.att_mem[n] + mem <= k * self.cap_mem[n]:   # memory available -> admitted
            if n in zone and req["safety"] and self.used_mem[n] + self.att_mem[n] + mem > (1 - cfg.SAFETY_RESERVE_SHARE) * self.cap_mem[n]:
                self.att_fake_into_reserve += 1                 # this fake-safety request is now eating the reserve
            self.att_cpu[n] += cpu
            self.att_mem[n] += mem
            self.att_running.append({"node": n, "cpu": cpu, "mem": mem, "end_s": req["arrival_s"] + req["hold_s"],
                                     "safety": req["safety"]})
            self.att_admitted += 1

    def update_gradual(self, t, cars, attackers):
        """Scenario C (CB-DRL paper): an RSU with at least one attacker car in range (during the attack window)
        gets hidden CPU load theta = GAMMA * (1 - e^(-BETA * seconds since the attack on it started)).
        When no attacker is in range any more, theta decays: theta = theta * e^(-BETA) every second."""
        if not hasattr(self, "theta"):                          # first call -> start the bookkeeping
            self.theta = {r: 0.0 for r in self.net.rsus}        # current attack occupancy (share of CPU) of every RSU
            self.theta_start = {}                               # rsu -> (start second, theta at start) of its current ramp
        in_window = cfg.ATTACK_START_S <= t < cfg.ATTACK_END_S
        hit = {cars[c][2] for c in attackers if c in cars and cars[c][2] is not None} if in_window else set()
        self.att_sent += len(hit)                               # here: RSU-seconds under attack
        for r in self.net.rsus:
            if r in hit:                                        # attacker in range -> ramp up towards GAMMA
                t0, th0 = self.theta_start.setdefault(r, (t, self.theta[r]))
                self.theta[r] = th0 + (cfg.GRADUAL_GAMMA - th0) * (1 - math.exp(-cfg.GRADUAL_BETA * (t - t0)))
            else:                                               # no attacker -> decay
                self.theta_start.pop(r, None)
                self.theta[r] *= math.exp(-cfg.GRADUAL_BETA)
                if self.theta[r] < 1e-4:
                    self.theta[r] = 0.0
            self.att_cpu[r] = self.theta[r] * self.cap_cpu[r]   # hidden CPU load (CB-DRL attacks CPU only)

    # ---------------- one simulation run ----------------
    def run(self):
        mob = Mobility(self.net)
        mob.start()
        while mob.t < cfg.SIM_DURATION_S:                       # one loop = 1 second
            cars = mob.step()                                   # cars move
            t = mob.t
            self.update_attackers(cars)                         # new cars: attacker or not?
            attackers = [c for c in cars if self.is_attacker[c]]

            # 1) finished normal SFCs and finished attack requests give resources back
            still = []
            for s in self.running:
                if t >= s["end_s"]:
                    self.release(s["req"], s["nodes"])
                else:
                    still.append(s)
            self.running = still
            still = []
            for a in self.att_running:
                if t >= a["end_s"]:
                    self.att_cpu[a["node"]] -= a["cpu"]
                    self.att_mem[a["node"]] -= a["mem"]
                else:
                    still.append(a)
            self.att_running = still

            # 2) attack hits the RSUs (orchestrator does not see this)
            if self.scenario == "C_gradual":                    # C: CB-DRL theta(t) CPU occupancy
                self.update_gradual(t, cars, attackers)
            elif self.scenario == "D_jam":                      # D: standing attackers in the jam zone
                for req in self.att_gen.jam_requests(t, self.net):
                    self.admit_attack(req)
            else:                                               # A / B: attack requests
                for req in self.att_gen.attack_requests(t, cars, attackers, self.scenario):
                    self.admit_attack(req)

            self.update_flood(t, cars, attackers)               # radio flood packets at every RSU
            if self.reassoc_on():                               # S3: cars leave flagged RSUs if another RSU is in range
                self.reassociate_running(cars)
            self.update_ingress()                               # normal packets at every RSU

            # 2b) Step 6: every 2 s EVERY RSU reports (regular attack check + recovery check of flagged RSUs)
            if self.det is not None and t % cfg.REPORT_INTERVAL_S == 0:
                self.det.check(t, periodic=True)
                self.after_check()                              # Step 9: migrate away from newly flagged RSUs

            # 3) new normal requests (only from honest cars) are placed by greedy
            for req in self.gen.normal_requests(t, cars, exclude=set(attackers)):
                if self.det is not None:                        # Step 6: check all RSUs BEFORE placing
                    self.det.check(t, periodic=False)
                    self.after_check()                          # Step 9
                    if self.reassoc_on():                       # S3: re-associate running SFCs after new flags
                        self.reassociate_running(cars)
                        self.update_ingress()
                    if self.reassoc_on() and req["entry"] in self.det.flagged:   # new request from a flagged RSU
                        new = self.better_entry(req["car_id"], cars)
                        if new is not None:
                            req["entry"] = new; self.reassociations += 1
                rec = {"req": req, "nodes": None, "end_s": t + req["hold_s"], "dropped": False,
                       "lat_sum": 0.0, "lat_n": 0, "down_s": 0, "over_s": 0}   # statistics over its lifetime
                e = req["entry"]                                # is the car's RSU queue overflowing?
                load = (self.ingress_pps[e] + self.flood_pps[e]) if e != cfg.CLOUD_ID else 0.0
                if load >= cfg.RSU_INGRESS_PPS and self.access_rng.random() < 1 - cfg.RSU_INGRESS_PPS / load:
                    rec["dropped"] = True                       # request lost in the flooded RSU queue
                    self.dropped += 1
                else:
                    rec["nodes"] = self.place(req)
                    if rec["nodes"] is not None:
                        self.running.append(rec)
                        if e != cfg.CLOUD_ID:
                            self.ingress_pps[e] += req["pkt_rate_pps"]   # its packets now load the RSU too
                self.log.append(rec)

            # 4) every running SFC: latency THIS second (attack may slow it down)
            lats, down = [], 0
            for s in self.running:
                e = s["req"]["entry"]                           # was this SFC touched by the attack this second?
                if (e != cfg.CLOUD_ID and self.flood_pps[e] > 0) or any(
                        n != cfg.CLOUD_ID and self.att_cpu[n] > 0 for n in s["nodes"]):
                    s["hit"] = True
                L = self.latency_ms(s["req"], s["nodes"])
                if math.isfinite(L):
                    s["lat_sum"] += L; s["lat_n"] += 1; lats.append(L)
                    if L > cfg.SERVICE_DEADLINE_MS:
                        s["over_s"] += 1                        # slower than the 100 ms service limit this second
                else:
                    s["down_s"] += 1; down += 1                 # service stopped this second
            self.lat_timeline.append((t, float(np.mean(lats)) if lats else 0.0, down))

            # 5) record RSU loads (known and hidden) this second
            rs = self.net.rsus
            self.util_timeline.append([t] + [self.used_cpu[r] / self.cap_cpu[r] for r in rs])
            self.att_timeline.append([t] + [self.att_cpu[r] / self.cap_cpu[r] for r in rs])
            if self.det is not None:
                self.det.tick(t)                                # scoring of detection (ground truth)
            self.reserve_timeline.append((t, len(self.reserve_zone())))   # Step 7: RSUs with an active reserve
        mob.close()
        return self.summary()

    # ---------------- results ----------------
    def summary(self):
        acc = [r for r in self.log if r["nodes"] is not None]                   # accepted SFCs
        def avg_lat(lst):                                                       # mean of each SFC's mean latency
            v = [r["lat_sum"] / r["lat_n"] for r in lst if r["lat_n"] > 0]
            return float(np.mean(v)) if v else 0.0
        def pct(lst, cond):                                                     # % of a list that meets a condition
            return sum(cond(r) for r in lst) / len(lst) * 100 if lst else 0.0
        safety = [r for r in acc if r["req"]["safety"]]
        nonsafe = [r for r in acc if not r["req"]["safety"]]
        all_vnfs = [n for r in acc for n in r["nodes"]]
        failed = lambda r: r["dropped"] or r["nodes"] is None or r["down_s"] > 0 or r["over_s"] > 0   # service failed
        win_all = [r for r in self.log if cfg.ATTACK_START_S <= r["req"]["arrival_s"] < cfg.ATTACK_END_S]
        act = [r for r in self.log if r["req"]["arrival_s"] < cfg.ATTACK_END_S and r["end_s"] > cfg.ATTACK_START_S]
        win = [r for r in acc if cfg.ATTACK_START_S <= r["req"]["arrival_s"] < cfg.ATTACK_END_S]   # SFCs arriving during the attack window
        win_s = [r for r in win if r["req"]["safety"]]                          # ... of which safety SFCs
        util = np.array([row[1:] for row in self.util_timeline])               # known load, seconds x RSUs
        att = np.array([row[1:] for row in self.att_timeline])                 # hidden load, seconds x RSUs
        out = {
            "scheme": self.scheme, "scenario": self.scenario, "seed": self.seed, "attacker_share": self.attacker_share,
            "requests": len(self.log),
            "accepted_pct": pct(self.log, lambda r: r["nodes"] is not None),
            "disrupted_pct": pct(acc, lambda r: r["down_s"] > 0),               # SFCs that stopped working at least 1 s
            "safety_disrupted_pct": pct(safety, lambda r: r["down_s"] > 0),
            "avg_latency_ms": avg_lat(acc),
            "safety_latency_ms": avg_lat(safety),
            "nonsafety_latency_ms": avg_lat(nonsafe),
            "window_failed_pct": pct(win_all, failed),                          # dropped, stopped, or ever > 100 ms
            "failed_pct": pct(self.log, failed),                                # same, whole hour
            "window_dropped_pct": pct(win_all, lambda r: r["dropped"]),         # lost in a flooded RSU queue
            "reassociations": self.reassociations,                              # S3: entry moved to a healthy RSU
            # ---- absolute counts for SFCs ACTIVE during the attack window (arrived before its end, ended after its start)
            "win_active_sfcs": len(act),
            "win_hit_sfcs": sum(r.get("hit", False) for r in act),              # touched by attack load or flood
            "win_failed_sfcs": sum(failed(r) for r in act),                     # dropped, stopped, or > 100 ms
            "win_dropped_sfcs": sum(r["dropped"] for r in act),
            "win_cloud_sfcs": sum(r["nodes"] is not None and cfg.CLOUD_ID in r["nodes"] for r in act),
            "win_edge_sfcs": sum(r["nodes"] is not None and cfg.CLOUD_ID not in r["nodes"] for r in act),
            "win_migrated_sfcs": sum("mig_ms" in r for r in act),
            "window_latency_ms": avg_lat(win),                                  # SFCs that arrived during the attack window
            "window_safety_latency_ms": avg_lat(win_s),
            "window_disrupted_pct": pct(win, lambda r: r["down_s"] > 0),
            "safety_at_edge_pct": pct(safety, lambda r: cfg.CLOUD_ID not in r["nodes"]),
            "nonsafety_at_edge_pct": pct(nonsafe, lambda r: cfg.CLOUD_ID not in r["nodes"]),
            "vnfs_on_cloud_pct": all_vnfs.count(cfg.CLOUD_ID) / len(all_vnfs) * 100 if all_vnfs else 0.0,
            "rsu_util_avg_pct": float(util.mean() * 100),
            "attack_sent": self.att_sent,
            "attack_admitted": self.att_admitted,
            "attack_cpu_avg_pct": float(att.mean() * 100),                      # hidden CPU load, average over RSUs and time
            "rsus_attacked": int((att.max(axis=0) > 0.01).sum()),                  # RSUs that received any attack load
            "window_safety_at_edge_pct": pct(win_s, lambda r: cfg.CLOUD_ID not in r["nodes"]),
            "window_at_edge_pct": pct(win, lambda r: cfg.CLOUD_ID not in r["nodes"]),
            "scaled_out_vnfs_pct": (sum(n not in (r["req"]["entry"], cfg.CLOUD_ID) for r in acc for n in r["nodes"])
                                    / len(all_vnfs) * 100) if all_vnfs else 0.0,   # VNFs on a neighbour RSU
            "window_running_latency_ms": float(np.mean([l for t, l, d in self.lat_timeline
                                                         if cfg.ATTACK_START_S <= t < cfg.ATTACK_END_S and l > 0])),
                                                                                # ALL running SFCs during the attack (incl. older ones)
            "window_disrupted_sfc_s": int(sum(d for t, l, d in self.lat_timeline
                                              if cfg.ATTACK_START_S <= t < cfg.ATTACK_END_S)),   # SFC-seconds with service stopped
            "migrations": self.migrations,                                      # Step 9: VNFs moved off flagged RSUs
            "migrations_to_cloud": self.migrations_to_cloud,
            "migration_failed": self.migration_failed,
            "migrated_sfcs": sum("mig_ms" in r for r in acc),
            "reserve_skips": self.reserve_skips,                                # non-safety VNFs refused by a reserve
            "att_fake_into_reserve": self.att_fake_into_reserve,                # fake-safety attack requests inside a reserve
            "avg_reserve_rsus_in_window": float(np.mean([z for t, z in self.reserve_timeline
                                                         if cfg.ATTACK_START_S <= t < cfg.ATTACK_END_S])),
        }
        if self.det is not None:                                                # Step 6: add detection results
            out.update(self.det.summary())
        else:                                                                   # no detector -> same columns, left empty
            out.update({k: float("nan") for k in DET_KEYS})
        return out
