# =====================================================================
# requests_gen.py  -  makes SFC requests (normal ones now, attack ones in Step 5)
# ---------------------------------------------------------------------
# Library used by Step 3 and later steps:
#     vnf_cpu, vnf_mem = load_alibaba_vnfs()          # real Alibaba container sizes
#     gen = RequestGenerator(seed, vnf_cpu, vnf_mem)
#     new = gen.normal_requests(t, cars)              # list of new requests in second t
# One request = one SFC = an ordered list of VNFs, each needing CPU + memory
# on some node for the request's holding time.
# =====================================================================

import numpy as np                 # random numbers (Poisson, uniform, choice)
import pandas as pd                # read the big Alibaba csv quickly
import config as cfg               # our settings

PKT_MIN, PKT_MAX = 1, 100          # packets per second of one SFC [old CB-DRL step4, kept for the M/M/1 delay model]


def load_alibaba_vnfs():
    """Return two arrays with the CPU (cores) and memory of real Alibaba containers."""
    cols = ["container_id", "machine_id", "time_stamp", "app_du",     # container_meta.csv has no header row,
            "status", "cpu_request", "cpu_limit", "mem_size"]         # so we give the column names ourselves
    df = pd.read_csv(cfg.ALIBABA_CONTAINER_FILE, header=None, names=cols)   # ~370,000 rows
    df = df.drop_duplicates("container_id", keep="last")              # one row per container (file repeats them over time)
    df = df[(df.cpu_request > 0) & (df.mem_size > 0)]                 # remove empty / broken rows
    cpu = (df.cpu_request / 100).to_numpy()                           # Alibaba writes 400 for 4 cores -> divide by 100
    mem = df.mem_size.to_numpy()                                      # memory in the same units as RSU memory (100 per RSU)
    return cpu, mem                                                   # two numpy arrays of equal length


class RequestGenerator:                                               # creates requests with its own random generator
    def __init__(self, seed, vnf_cpu, vnf_mem, net):
        self.rng = np.random.default_rng(seed)                        # separate random stream -> same requests for the same seed
        self.vnf_cpu = vnf_cpu                                        # pool of real CPU demands
        self.vnf_mem = vnf_mem                                        # pool of real memory demands
        self.net = net                                                # network (to find the entry RSU)
        self.next_id = 0                                              # running request number

    def _build(self, t, car, x, y, rsu, is_attack=False):
        """Build ONE request dictionary. rsu = car's nearest RSU in range (None = only cloud)."""
        r = self.rng                                                  # short name
        n = int(r.integers(cfg.SFC_LEN_MIN, cfg.SFC_LEN_MAX + 1))     # chain length 2..6 (SPAVM)
        types = r.choice(cfg.NUM_VNF_TYPES, size=n, replace=False)    # n DIFFERENT VNF types out of 20
        rows = r.integers(0, len(self.vnf_cpu), size=n)               # n random real Alibaba containers
        req = {
            "req_id": self.next_id,                                   # unique number
            "arrival_s": t,                                           # second it arrives
            "car_id": car,                                            # which car asked
            "x": round(x, 1), "y": round(y, 1),                       # car position when asking
            "entry": rsu if rsu is not None else cfg.CLOUD_ID,        # entry node: nearest RSU, or cloud if none in range
            "chain": [f"VNF{k}" for k in types],                      # e.g. ['VNF7', 'VNF2', 'VNF15']
            "cpu": [float(self.vnf_cpu[i]) for i in rows],            # CPU cores needed by each VNF
            "mem": [float(self.vnf_mem[i]) for i in rows],            # memory needed by each VNF
            "pkt_rate_pps": int(r.integers(PKT_MIN, PKT_MAX + 1)),    # packets per second (for processing delay later)
            "hold_s": int(r.integers(cfg.HOLD_MIN_S, cfg.HOLD_MAX_S + 1)),   # how long the SFC keeps its resources
            "safety": bool(r.random() < (cfg.ATTACK_FAKE_SAFETY_SHARE if is_attack else cfg.SAFETY_SHARE)),
                                                                      # normal: 20% safety;  attack: 50% FALSELY say safety
            "is_attack": is_attack,                                   # False for normal requests
        }
        if is_attack:                                                 # an attack request is bigger and stays longer
            req["req_id"] = f"A{self.next_id}"                        # attack ids start with 'A' (A0, A1, ...)
            req["cpu"] = [c * cfg.ATTACK_SIZE_FACTOR for c in req["cpu"]]   # 2x CPU
            req["mem"] = [m * cfg.ATTACK_SIZE_FACTOR for m in req["mem"]]   # 2x memory
            req["hold_s"] = int(req["hold_s"] * cfg.ATTACK_HOLD_FACTOR)     # 3x holding time
        self.next_id += 1                                             # next request gets the next number
        return req

    def normal_requests(self, t, cars, exclude=()):
        """New normal requests in second t.  cars = {car: (x, y, rsu)};  exclude = cars that are attackers."""
        k = int(self.rng.poisson(cfg.LAMBDA_NORMAL * cfg.SUMO_STEP_S))   # how many arrive this second (Poisson, mostly 0 or 1)
        normal_cars = [c for c in cars if c not in exclude]           # only honest cars send normal requests
        out = []                                                      # list to return
        for _ in range(k):                                            # make k requests
            if not normal_cars:                                       # no car on the road yet (very start)
                break
            car = normal_cars[int(self.rng.integers(len(normal_cars)))]   # pick a random honest car
            x, y, rsu = cars[car]                                     # where it is and which RSU covers it
            out.append(self._build(t, car, x, y, rsu))                # build the request
        return out

    def attack_requests(self, t, cars, attackers, scenario="A_wide"):
        """New attack requests in second t. Each attacker car inside an RSU range sends Poisson(LAMBDA_ATTACK)
        requests DIRECTLY to its RSU (the orchestrator never sees them)."""
        out = []                                                      # list to return
        if not (cfg.ATTACK_START_S <= t < cfg.ATTACK_END_S):          # outside the DDoS campaign window -> no attack
            return out
        for car in attackers:                                         # every attacker car ...
            if car not in cars:                                       # ... that is still on the road
                continue
            x, y, rsu = cars[car]                                     # position + attached RSU
            if rsu is None:                                           # no RSU in range -> cannot attack anything
                continue
            if scenario == "B_targeted" and rsu not in cfg.TARGET_RSUS:   # B: attack only the chosen target RSUs
                continue
            lam = cfg.LAMBDA_ATTACK_LIGHT if scenario == "A_light" else cfg.LAMBDA_ATTACK   # A_light = lighter attacker
            k = int(self.rng.poisson(lam * cfg.SUMO_STEP_S))          # how many attack requests this second
            for _ in range(k):
                out.append(self._build(t, car, x, y, rsu, is_attack=True))   # target = the car's own RSU
        return out

    def jam_requests(self, t, net):
        """Scenario D: in the attack window, JAM_ATTACKERS_PER_RSU standing attackers flood every RSU of the jam zone
        (JAM_CENTER + RSUs within JAM_RADIUS_HOPS). Same rate and size as the other attack requests."""
        out = []
        if not (cfg.ATTACK_START_S <= t < cfg.ATTACK_END_S):
            return out
        zone = [cfg.JAM_CENTER] + [b for b, h, d in net.neighbours_within(cfg.JAM_CENTER, cfg.JAM_RADIUS_HOPS)]
        for rsu in zone:
            r = net.rsus[rsu]
            for k in range(cfg.JAM_ATTACKERS_PER_RSU):               # each standing attacker
                for _ in range(int(self.rng.poisson(cfg.LAMBDA_ATTACK * cfg.SUMO_STEP_S))):
                    out.append(self._build(t, f"jam_{rsu}_{k}", r["x"], r["y"], rsu, is_attack=True))
        return out
